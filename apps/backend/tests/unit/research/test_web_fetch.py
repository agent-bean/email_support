from __future__ import annotations

import asyncio
import ipaddress
import ssl
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx2
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def _trusted_localhost_certificate(
    tmp_path: Path,
) -> tuple[ssl.SSLContext, ssl.SSLContext, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
        .sign(key, hashes.SHA256())
    )
    certificate_pem = certificate.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    certificate_path = tmp_path / "localhost-cert.pem"
    key_path = tmp_path / "localhost-key.pem"
    certificate_path.write_bytes(certificate_pem)
    key_path.write_bytes(key_pem)

    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(certificate_path, key_path)
    client_context = ssl.create_default_context(cadata=certificate_pem.decode())
    return server_context, client_context, certificate_pem.decode()


@pytest.mark.asyncio
async def test_httpx2_connects_to_literal_ip_with_original_host_and_verified_sni(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server_context, client_context, _certificate = _trusted_localhost_certificate(
        tmp_path
    )
    observed_sni: list[str | None] = []
    observed_peer_ips: list[str] = []
    observed_hosts: list[str] = []
    server_context.set_servername_callback(
        lambda _socket, name, _context: observed_sni.append(name)
    )

    async def handler(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        assert isinstance(peer, tuple)
        observed_peer_ips.append(str(peer[0]))
        headers = await reader.readuntil(b"\r\n\r\n")
        host_line = next(
            line for line in headers.split(b"\r\n") if line.lower().startswith(b"host:")
        )
        observed_hosts.append(host_line.decode().split(":", maxsplit=1)[1].strip())
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok"
        )
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handler, "127.0.0.1", 0, ssl=server_context)
    port = server.sockets[0].getsockname()[1]
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    try:
        async with server:
            async with httpx2.AsyncClient(
                verify=client_context,
                trust_env=False,
                follow_redirects=False,
                http2=False,
                limits=httpx2.Limits(max_keepalive_connections=0),
            ) as client:
                response = await client.get(
                    f"https://127.0.0.1:{port}/source",
                    headers={"Host": "localhost"},
                    extensions={"sni_hostname": "localhost"},
                )
        assert response.status_code == 200
        assert response.text == "ok"
        assert observed_peer_ips == ["127.0.0.1"]
        assert observed_hosts == ["localhost"]
        assert observed_sni == ["localhost"]
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.parametrize(
    "value",
    [
        "http://example.com/",
        "file:///etc/passwd",
        "https://user:password@example.com/",
        "https://example.com:8443/",
        "https://127.0.0.1/",
        "https://[::1]/",
        "https://example.com/#fragment",
    ],
)
def test_fetch_url_rejects_unsafe_syntax(value: str) -> None:
    from email_support.integrations.web_fetch import validate_fetch_url

    with pytest.raises(ValueError):
        validate_fetch_url(value)


@pytest.mark.parametrize(
    "value",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "::1",
        "fc00::1",
        "fe80::1",
        "224.0.0.1",
        "::ffff:127.0.0.1",
    ],
)
def test_fetch_rejects_non_public_ip_addresses(value: str) -> None:
    from email_support.integrations.web_fetch import validate_public_address

    with pytest.raises(ValueError):
        validate_public_address(ipaddress.ip_address(value))


class _FakeAnswers:
    def __init__(self, addresses: list[str]) -> None:
        self.addresses = addresses


class _FakeResolver:
    async def resolve_name(self, name: str, **kwargs: object) -> object:
        assert name == "public.example"
        assert kwargs["search"] is False
        return _FakeAnswers(["8.8.8.8", "2001:4860:4860::8888"])


@pytest.mark.asyncio
async def test_fetch_uses_vetted_literal_ip_and_rejects_redirects() -> None:
    from email_support.integrations.provider_http import ProviderCallError
    from email_support.integrations.web_fetch import WebFetcher
    from email_support.models.research import ProviderErrorCategory

    observed: list[httpx2.Request] = []

    async def handler(request: httpx2.Request) -> httpx2.Response:
        observed.append(request)
        return httpx2.Response(302, headers={"location": "http://169.254.169.254/"})

    def client_factory(**kwargs: Any) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(transport=httpx2.MockTransport(handler), **kwargs)

    fetcher = WebFetcher(resolver=_FakeResolver(), client_factory=client_factory)
    with pytest.raises(ProviderCallError) as error:
        await fetcher.fetch("https://public.example/story")
    assert error.value.category is ProviderErrorCategory.FETCH_UNAVAILABLE
    assert len(observed) == 1
    request = observed[0]
    assert request.url.host in {"8.8.8.8", "2001:4860:4860::8888"}
    assert request.headers["host"] == "public.example"
    assert request.extensions["sni_hostname"] == "public.example"


@pytest.mark.asyncio
async def test_fetch_rejects_mixed_dns_answers_before_connecting() -> None:
    from email_support.integrations.provider_http import ProviderCallError
    from email_support.integrations.web_fetch import WebFetcher
    from email_support.models.research import ProviderErrorCategory

    class MixedResolver:
        async def resolve_name(self, name: str, **_kwargs: object) -> object:
            assert name == "public.example"
            return _FakeAnswers(["8.8.8.8", "10.0.0.1"])

    async def handler(_request: httpx2.Request) -> httpx2.Response:
        pytest.fail("mixed DNS answers must be rejected before connecting")

    def client_factory(**kwargs: Any) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(transport=httpx2.MockTransport(handler), **kwargs)

    with pytest.raises(ProviderCallError) as error:
        await WebFetcher(resolver=MixedResolver(), client_factory=client_factory).fetch(
            "https://public.example/story"
        )
    assert error.value.category is ProviderErrorCategory.INVALID_REQUEST


@pytest.mark.asyncio
async def test_fetch_streams_with_size_limit_and_text_mime_only() -> None:
    from email_support.integrations.provider_http import ProviderCallError
    from email_support.integrations.web_fetch import WebFetcher
    from email_support.models.research import ProviderErrorCategory

    async def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            headers={"content-type": "application/pdf", "content-length": "20"},
            content=b"not a web page",
        )

    def client_factory(**kwargs: Any) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(transport=httpx2.MockTransport(handler), **kwargs)

    with pytest.raises(ProviderCallError) as error:
        await WebFetcher(
            resolver=_FakeResolver(), client_factory=client_factory, max_bytes=16
        ).fetch("https://public.example/story")
    assert error.value.category is ProviderErrorCategory.FETCH_UNAVAILABLE


@pytest.mark.asyncio
async def test_fetch_rejects_declared_and_streamed_oversize_bytes() -> None:
    from email_support.integrations.provider_http import ProviderCallError
    from email_support.integrations.web_fetch import WebFetcher
    from email_support.models.research import ProviderErrorCategory

    async def declared(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            headers={"content-type": "text/plain", "content-length": "20"},
            content=b"small",
        )

    def declared_client(**kwargs: Any) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(transport=httpx2.MockTransport(declared), **kwargs)

    with pytest.raises(ProviderCallError) as error:
        await WebFetcher(
            resolver=_FakeResolver(), client_factory=declared_client, max_bytes=10
        ).fetch("https://public.example/story")
    assert error.value.category is ProviderErrorCategory.FETCH_UNAVAILABLE

    class Chunks(httpx2.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b"123456"
            yield b"789012"

        async def aclose(self) -> None:
            return None

    async def streamed(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            headers={"content-type": "text/plain"},
            stream=Chunks(),
        )

    def streamed_client(**kwargs: Any) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(transport=httpx2.MockTransport(streamed), **kwargs)

    with pytest.raises(ProviderCallError) as error:
        await WebFetcher(
            resolver=_FakeResolver(), client_factory=streamed_client, max_bytes=10
        ).fetch("https://public.example/story")
    assert error.value.category is ProviderErrorCategory.FETCH_UNAVAILABLE


@pytest.mark.asyncio
async def test_fetch_cancellation_closes_the_response_stream() -> None:
    from email_support.integrations.web_fetch import WebFetcher

    started = asyncio.Event()
    never = asyncio.Event()

    class BlockingChunks(httpx2.AsyncByteStream):
        closed = False

        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b"first chunk"
            started.set()
            await never.wait()
            yield b"unreachable"

        async def aclose(self) -> None:
            self.closed = True

    stream = BlockingChunks()

    async def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            headers={"content-type": "text/plain"},
            stream=stream,
        )

    def client_factory(**kwargs: Any) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(transport=httpx2.MockTransport(handler), **kwargs)

    task = asyncio.create_task(
        WebFetcher(resolver=_FakeResolver(), client_factory=client_factory).fetch(
            "https://public.example/story"
        )
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stream.closed is True


@pytest.mark.asyncio
async def test_fetch_dns_uses_bounded_timeout_and_maps_failure_safely() -> None:
    from email_support.integrations.provider_http import ProviderCallError
    from email_support.integrations.web_fetch import WebFetcher
    from email_support.models.research import ProviderErrorCategory

    class TimedOutResolver:
        async def resolve_name(self, name: str, **kwargs: object) -> object:
            assert name == "public.example"
            assert kwargs["search"] is False
            assert kwargs["lifetime"] == 0.01
            await asyncio.sleep(1)
            return _FakeAnswers([])

    with pytest.raises(ProviderCallError) as error:
        await WebFetcher(resolver=TimedOutResolver(), timeout_seconds=0.01).fetch(
            "https://public.example/story"
        )
    assert error.value.category is ProviderErrorCategory.FETCH_UNAVAILABLE
