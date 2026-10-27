"""Owner sign-in endpoints and protected session operations."""

import hmac
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Request,
    Response,
    Security,
)
from fastapi.responses import RedirectResponse
from fastapi.security import APIKeyCookie
from pydantic import HttpUrl, TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from email_support.config import AuthSettings
from email_support.integrations.google_oidc import exchange_code
from email_support.models.owner_auth import (
    LoginRequest,
    LoginResponse,
    OwnerAuthError,
    OwnerAuthErrorCode,
    OwnerSession,
    PreauthResponse,
)
from email_support.services.owner_auth import (
    begin_login,
    consume_login_callback,
    create_preauth,
    get_valid_session,
    issue_owner_session,
    logout_session,
)
from email_support.storage.postgres.persistence.database import (
    create_database_engine,
    create_session_factory,
    dispose_database_engine,
)

router = APIRouter(prefix="/api/auth", tags=["owner-auth"])
logger = logging.getLogger(__name__)
SESSION_TTL_SECONDS = 12 * 60 * 60
HTTP_URL_ADAPTER: TypeAdapter[HttpUrl] = TypeAdapter(HttpUrl)
OWNER_SESSION_COOKIE = APIKeyCookie(
    name="__Host-owner_session", scheme_name="OwnerSession", auto_error=False
)


@dataclass(slots=True)
class OwnerAuthRuntime:
    settings: AuthSettings | None
    sessions: async_sessionmaker[AsyncSession] | None
    configuration_error: str | None


@asynccontextmanager
async def owner_auth_runtime() -> AsyncIterator[OwnerAuthRuntime]:
    try:
        from email_support.config import load_auth_settings

        settings = load_auth_settings()
    except ValueError as exc:
        yield OwnerAuthRuntime(None, None, str(exc))
        return
    if settings is None:
        yield OwnerAuthRuntime(None, None, None)
        return
    engine = create_database_engine(settings.database_url)
    try:
        yield OwnerAuthRuntime(settings, create_session_factory(engine), None)
    finally:
        await dispose_database_engine(engine)


def require_owner_auth_runtime(request: Request) -> OwnerAuthRuntime:
    value = getattr(request.app.state, "owner_auth_runtime", None)
    if (
        not isinstance(value, OwnerAuthRuntime)
        or value.settings is None
        or value.sessions is None
    ):
        raise HTTPException(
            status_code=503,
            detail=OwnerAuthError(
                code=OwnerAuthErrorCode.AUTH_UNAVAILABLE,
                message="Owner sign-in is not configured.",
            ).model_dump(mode="json"),
        )
    return value


def cookie_names(settings: AuthSettings) -> tuple[str, str]:
    if settings.secure_cookie:
        return "__Host-owner_browser", "__Host-owner_session"
    return "owner_browser", "owner_session"


def set_cookie(
    response: Response, *, name: str, value: str, secure: bool, max_age: int
) -> None:
    response.set_cookie(
        name,
        value,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
        max_age=max_age,
    )


def _auth_redirect(
    settings: AuthSettings,
    outcome: Literal["restart", "unavailable", "rejected", "ok"],
) -> RedirectResponse:
    return RedirectResponse(f"{settings.web_origin}/?auth={outcome}", status_code=303)


def _safe_failure_category(error: Exception) -> str:
    provider_code = getattr(error, "error", None)
    if isinstance(provider_code, str) and provider_code in {
        "access_denied",
        "invalid_client",
        "invalid_grant",
        "invalid_request",
        "server_error",
        "temporarily_unavailable",
        "unauthorized_client",
    }:
        return provider_code
    return type(error).__name__


def clear_cookie(response: Response, name: str, secure: bool) -> None:
    response.delete_cookie(name, path="/", secure=secure, httponly=True, samesite="lax")


def expired_cookie_header(name: str, secure: bool) -> str:
    response = Response()
    clear_cookie(response, name, secure)
    return response.headers["set-cookie"]


def _cookie(
    request: Request, settings: AuthSettings, *, session: bool = False
) -> str | None:
    browser_name, session_name = cookie_names(settings)
    return request.cookies.get(session_name if session else browser_name)


async def protected_session(
    request: Request,
    owner_auth: Annotated[OwnerAuthRuntime, Depends(require_owner_auth_runtime)],
    _: Annotated[str | None, Security(OWNER_SESSION_COOKIE)],
) -> tuple[str, datetime, str]:
    assert owner_auth.settings is not None and owner_auth.sessions is not None
    token = _cookie(request, owner_auth.settings, session=True)
    try:
        result = await get_valid_session(owner_auth.sessions, token)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=OwnerAuthError(
                code=OwnerAuthErrorCode.AUTH_UNAVAILABLE,
                message="Owner session storage is unavailable.",
            ).model_dump(mode="json"),
        ) from exc
    if result is None:
        headers = None
        if token:
            _, session_name = cookie_names(owner_auth.settings)
            headers = {
                "Set-Cookie": expired_cookie_header(
                    session_name, owner_auth.settings.secure_cookie
                )
            }
        raise HTTPException(
            status_code=401,
            detail=OwnerAuthError(
                code=OwnerAuthErrorCode.AUTH_REQUIRED,
                message="Sign in to continue.",
            ).model_dump(mode="json"),
            headers=headers,
        )
    return result


@router.get(
    "/preauth",
    response_model=PreauthResponse,
    responses={503: {"model": OwnerAuthError}},
    operation_id="get_owner_auth_preauth",
)
async def preauth(request: Request, response: Response) -> PreauthResponse:
    owner_auth = require_owner_auth_runtime(request)
    assert owner_auth.settings is not None and owner_auth.sessions is not None
    try:
        browser_secret, csrf_secret = await create_preauth(
            owner_auth.sessions, _cookie(request, owner_auth.settings)
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=OwnerAuthError(
                code=OwnerAuthErrorCode.AUTH_UNAVAILABLE,
                message="Owner sign-in is unavailable.",
            ).model_dump(mode="json"),
        ) from exc
    browser_name, _ = cookie_names(owner_auth.settings)
    set_cookie(
        response,
        name=browser_name,
        value=browser_secret,
        secure=owner_auth.settings.secure_cookie,
        max_age=600,
    )
    response.headers["Cache-Control"] = "no-store"
    return PreauthResponse(csrf_token=csrf_secret)


@router.post(
    "/google/login",
    response_model=LoginResponse,
    responses={
        400: {"model": OwnerAuthError},
        503: {"model": OwnerAuthError},
    },
    operation_id="start_google_login",
)
async def start_google_login(
    request: Request,
    _payload: LoginRequest,
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> LoginResponse:
    owner_auth = require_owner_auth_runtime(request)
    assert owner_auth.settings is not None and owner_auth.sessions is not None
    if request.headers.get("origin") != owner_auth.settings.web_origin:
        raise HTTPException(
            status_code=400,
            detail=OwnerAuthError(
                code=OwnerAuthErrorCode.CSRF_REJECTED,
                message="Restart sign-in from this application.",
            ).model_dump(mode="json"),
        )
    content_type = request.headers.get("content-type", "").split(";", maxsplit=1)[0]
    if content_type != "application/json":
        raise HTTPException(status_code=415, detail="JSON content type is required")
    browser_secret = _cookie(request, owner_auth.settings)
    if not csrf_token or not browser_secret:
        authorization = None
    else:
        try:
            authorization = await begin_login(
                owner_auth.settings,
                owner_auth.sessions,
                browser_cookie=browser_secret,
                csrf_secret=csrf_token,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=OwnerAuthError(
                    code=OwnerAuthErrorCode.AUTH_UNAVAILABLE,
                    message="Owner sign-in is unavailable.",
                ).model_dump(mode="json"),
            ) from exc
    if authorization is None:
        raise HTTPException(
            status_code=400,
            detail=OwnerAuthError(
                code=OwnerAuthErrorCode.LOGIN_RESTART,
                message="Restart sign-in and try again.",
            ).model_dump(mode="json"),
        )
    return LoginResponse(
        authorization_url=HTTP_URL_ADAPTER.validate_python(authorization.url)
    )


@router.get(
    "/google/callback",
    include_in_schema=False,
    operation_id="complete_google_login",
)
async def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    owner_auth = require_owner_auth_runtime(request)
    assert owner_auth.settings is not None and owner_auth.sessions is not None
    browser_secret = _cookie(request, owner_auth.settings)
    if not browser_secret or not state:
        return _auth_redirect(owner_auth.settings, "restart")
    try:
        attempt = await consume_login_callback(
            owner_auth.sessions, browser_cookie=browser_secret, state=state
        )
    except Exception as exc:
        logger.warning(
            "Google login callback failed during attempt consumption (%s)",
            _safe_failure_category(exc),
        )
        return _auth_redirect(owner_auth.settings, "unavailable")
    if attempt is None:
        return _auth_redirect(owner_auth.settings, "restart")
    if error or not code or not attempt.nonce or not attempt.code_verifier:
        return _auth_redirect(owner_auth.settings, "rejected")
    failure_stage = "token exchange"
    try:
        identity = await exchange_code(
            code,
            client_id=owner_auth.settings.google_client_id,
            client_secret=owner_auth.settings.google_client_secret,
            callback_uri=owner_auth.settings.callback_uri,
            code_verifier=attempt.code_verifier,
            expected_nonce=attempt.nonce,
        )
        failure_stage = "session issuance"
        old_token = _cookie(request, owner_auth.settings, session=True)
        credentials = await issue_owner_session(
            owner_auth.sessions,
            identity=identity,
            owner_sub=owner_auth.settings.owner_sub,
            old_token=old_token,
        )
    except PermissionError:
        return _auth_redirect(owner_auth.settings, "rejected")
    except Exception as exc:
        logger.warning(
            "Google login callback failed during %s (%s)",
            failure_stage,
            _safe_failure_category(exc),
        )
        return _auth_redirect(owner_auth.settings, "unavailable")
    _, session_name = cookie_names(owner_auth.settings)
    response = _auth_redirect(owner_auth.settings, "ok")
    set_cookie(
        response,
        name=session_name,
        value=credentials.raw_token,
        secure=owner_auth.settings.secure_cookie,
        max_age=SESSION_TTL_SECONDS,
    )
    return response


@router.get(
    "/session",
    response_model=OwnerSession,
    responses={401: {"model": OwnerAuthError}, 503: {"model": OwnerAuthError}},
    operation_id="get_owner_session",
)
async def get_session(
    request: Request,
    response: Response,
    identity: tuple[str, datetime, str] = Depends(protected_session),
) -> OwnerSession:
    _, expires_at, csrf_secret = identity
    response.headers["Cache-Control"] = "no-store"
    return OwnerSession(expires_at=expires_at, csrf_token=csrf_secret)


@router.post(
    "/logout",
    status_code=204,
    responses={401: {"model": OwnerAuthError}, 403: {"model": OwnerAuthError}},
    operation_id="logout_owner",
)
async def logout(
    request: Request,
    response: Response,
    identity: tuple[str, datetime, str] = Depends(protected_session),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> Response:
    owner_auth = require_owner_auth_runtime(request)
    assert owner_auth.settings is not None and owner_auth.sessions is not None
    if request.headers.get("origin") != owner_auth.settings.web_origin:
        raise HTTPException(
            status_code=403,
            detail=OwnerAuthError(
                code=OwnerAuthErrorCode.CSRF_REJECTED,
                message="This request could not be verified.",
            ).model_dump(mode="json"),
        )
    _, session_name = cookie_names(owner_auth.settings)
    raw_token = _cookie(request, owner_auth.settings, session=True)
    # protected_session already validated the row; compare the synchronizer token.
    if not csrf_token or not hmac.compare_digest(csrf_token, identity[2]):
        raise HTTPException(
            status_code=403,
            detail=OwnerAuthError(
                code=OwnerAuthErrorCode.CSRF_REJECTED,
                message="This request could not be verified.",
            ).model_dump(mode="json"),
        )
    await logout_session(owner_auth.sessions, raw_token or "")
    clear_cookie(response, session_name, owner_auth.settings.secure_cookie)
    response.status_code = 204
    return response
