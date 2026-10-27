"""Connection-pinned, bounded fetches for invocation-approved public sources."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import re
import ssl
import time
from collections.abc import Callable
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import SplitResult, urlsplit, urlunsplit
from uuid import UUID, uuid4

import dns.asyncresolver
import httpx2

from email_support.integrations.provider_http import ProviderCallError
from email_support.models.research import FetchResult, ProviderErrorCategory


class Resolver(Protocol):
    async def resolve_name(self, name: str, **kwargs: object) -> object: ...


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self._ignored_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._ignored_depth += 1
        if tag.lower() == "title":
            self._in_title = True
        if tag.lower() in {"p", "div", "br", "li", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if (
            tag.lower() in {"script", "style", "noscript", "svg"}
            and self._ignored_depth
        ):
            self._ignored_depth -= 1
        if tag.lower() == "title":
            self._in_title = False
        if tag.lower() in {"p", "div", "li", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        if self._in_title:
            self.title_parts.append(data)
        self.parts.append(data)


ClientFactory = Callable[..., httpx2.AsyncClient]


class WebFetcher:
    def __init__(
        self,
        *,
        max_bytes: int = 524_288,
        timeout_seconds: float = 12.0,
        resolver: Resolver | None = None,
        client_factory: ClientFactory = httpx2.AsyncClient,
    ) -> None:
        if max_bytes < 1 or timeout_seconds <= 0:
            raise ValueError("fetch limits must be positive")
        self._max_bytes = max_bytes
        self._timeout_seconds = timeout_seconds
        self._resolver = resolver or dns.asyncresolver.Resolver()
        self._client_factory = client_factory

    async def fetch(self, url: str, *, source_id: UUID | None = None) -> FetchResult:
        deadline = time.monotonic() + self._timeout_seconds
        try:
            parsed = validate_fetch_url(url)
        except ValueError:
            raise ProviderCallError(ProviderErrorCategory.INVALID_REQUEST) from None
        host = parsed.hostname
        if host is None:
            raise ProviderCallError(ProviderErrorCategory.INVALID_REQUEST)
        addresses = await self._resolve(host)
        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds <= 0:
            raise ProviderCallError(ProviderErrorCategory.FETCH_UNAVAILABLE)
        literal_url = _replace_host(parsed, addresses[0])
        tls = ssl.create_default_context()
        limits = httpx2.Limits(max_connections=1, max_keepalive_connections=0)
        try:
            async with asyncio.timeout(remaining_seconds):
                async with self._client_factory(
                    verify=tls,
                    trust_env=False,
                    follow_redirects=False,
                    http2=False,
                    limits=limits,
                ) as client:
                    async with client.stream(
                        "GET",
                        literal_url,
                        headers={
                            "Host": host,
                            "Accept": "text/html, application/xhtml+xml, text/plain",
                            "Accept-Encoding": "identity",
                        },
                        extensions={"sni_hostname": host},
                    ) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            raise ProviderCallError(
                                ProviderErrorCategory.FETCH_UNAVAILABLE
                            )
                        if response.status_code != 200:
                            raise ProviderCallError(
                                ProviderErrorCategory.FETCH_UNAVAILABLE
                            )
                        content_type = (
                            response.headers.get("content-type", "")
                            .split(";", 1)[0]
                            .strip()
                            .lower()
                        )
                        if content_type not in {
                            "text/html",
                            "application/xhtml+xml",
                            "text/plain",
                        }:
                            raise ProviderCallError(
                                ProviderErrorCategory.FETCH_UNAVAILABLE
                            )
                        encoding = (
                            response.headers.get("content-encoding", "identity")
                            .strip()
                            .lower()
                        )
                        if encoding not in {"", "identity"}:
                            raise ProviderCallError(
                                ProviderErrorCategory.FETCH_UNAVAILABLE
                            )
                        content_length = response.headers.get("content-length")
                        if content_length is not None:
                            try:
                                declared_length = int(content_length)
                            except ValueError:
                                raise ProviderCallError(
                                    ProviderErrorCategory.MALFORMED_RESPONSE
                                ) from None
                            if declared_length < 0:
                                raise ProviderCallError(
                                    ProviderErrorCategory.MALFORMED_RESPONSE
                                )
                            if declared_length > self._max_bytes:
                                raise ProviderCallError(
                                    ProviderErrorCategory.FETCH_UNAVAILABLE
                                )
                        body = bytearray()
                        async for chunk in response.aiter_raw():
                            body.extend(chunk)
                            if len(body) > self._max_bytes:
                                raise ProviderCallError(
                                    ProviderErrorCategory.FETCH_UNAVAILABLE
                                )
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            raise ProviderCallError(ProviderErrorCategory.FETCH_UNAVAILABLE) from None
        except httpx2.RequestError:
            raise ProviderCallError(ProviderErrorCategory.FETCH_UNAVAILABLE) from None
        charset = _charset(response.headers.get("content-type", ""))
        decoded = bytes(body).decode(charset, errors="replace")
        title = host
        if content_type in {"text/html", "application/xhtml+xml"}:
            extractor = _TextExtractor()
            extractor.feed(decoded)
            title = " ".join(" ".join(extractor.title_parts).split()) or host
            decoded = " ".join(" ".join(extractor.parts).split())
        else:
            decoded = " ".join(decoded.split())
        text = decoded[:50_000]
        if not text:
            raise ProviderCallError(ProviderErrorCategory.FETCH_UNAVAILABLE)
        return FetchResult.model_validate(
            {
                "source_id": source_id or uuid4(),
                "url": url,
                "title": title[:300],
                "text": text,
                "content_type": content_type,
                "content_sha256": hashlib.sha256(bytes(body)).hexdigest(),
            }
        )

    async def _resolve(
        self, host: str
    ) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                answers = await self._resolver.resolve_name(
                    host,
                    family=0,
                    lifetime=self._timeout_seconds,
                    search=False,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            raise ProviderCallError(ProviderErrorCategory.FETCH_UNAVAILABLE) from None
        raw_addresses = getattr(answers, "addresses", None)
        if not isinstance(raw_addresses, list) or not raw_addresses:
            raise ProviderCallError(ProviderErrorCategory.FETCH_UNAVAILABLE)
        addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
        for raw in raw_addresses:
            try:
                address = ipaddress.ip_address(raw)
                validate_public_address(address)
                addresses.append(address)
            except ValueError:
                raise ProviderCallError(ProviderErrorCategory.INVALID_REQUEST) from None
        if len(set(addresses)) != len(addresses):
            addresses = list(dict.fromkeys(addresses))
        return addresses


def validate_fetch_url(value: str) -> SplitResult:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("source URL must use HTTPS and include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("source URL cannot include credentials")
    if parsed.fragment:
        raise ValueError("source URL cannot include a fragment")
    try:
        port = parsed.port
    except ValueError:
        raise ValueError("source URL has an invalid port") from None
    if port not in {None, 443}:
        raise ValueError("source URL must use HTTPS port 443")
    host = parsed.hostname.rstrip(".")
    if not host or len(host) > 253 or re.search(r"[^a-zA-Z0-9.-]", host):
        raise ValueError("source URL has an invalid hostname")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("source URL must use a DNS hostname")
    try:
        host.encode("idna")
    except UnicodeError:
        raise ValueError("source URL has an invalid hostname") from None
    return parsed._replace(netloc=host + (":443" if port == 443 else ""))


def validate_public_address(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> None:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        raise ValueError("mapped IPv6 addresses are not accepted")
    if address.is_multicast or address.is_reserved or not address.is_global:
        raise ValueError("source address is not globally routable")


def _replace_host(
    parsed: SplitResult, address: ipaddress.IPv4Address | ipaddress.IPv6Address
) -> str:
    hostname = f"[{address.compressed}]" if address.version == 6 else address.compressed
    port = parsed.port
    netloc = f"{hostname}:{port}" if port is not None else hostname
    return urlunsplit((parsed.scheme, netloc, parsed.path or "/", parsed.query, ""))


def _charset(content_type: str) -> str:
    match = re.search(r"charset\s*=\s*[\"']?([^;\"']+)", content_type, re.IGNORECASE)
    charset = match.group(1).strip() if match else "utf-8"
    try:
        "".encode(charset)
    except LookupError:
        return "utf-8"
    return charset
