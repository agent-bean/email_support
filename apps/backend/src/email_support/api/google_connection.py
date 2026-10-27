"""Owner-only endpoints for separate Google Workspace consent and disconnect."""

import hmac
import secrets
from datetime import datetime
from typing import NoReturn

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import HttpUrl, TypeAdapter

from email_support.api.auth import (
    AuthRuntime,
    cookie_names,
    protected_session,
    require_auth_runtime,
    set_cookie,
)
from email_support.config import AuthSettings
from email_support.integrations.google_oidc import exchange_connection_code
from email_support.integrations.google_workspace import GoogleWorkspaceClient
from email_support.models.google_connection import (
    GoogleConnectionErrorCode,
    GoogleConnectionErrorResponse,
    GoogleConnectionFailure,
    GoogleConnectionResponse,
    GoogleConsentResponse,
    GoogleDisconnectResponse,
)
from email_support.services.google_connection import (
    begin_google_consent,
    consume_google_consent_attempt,
    disconnect_google_connection,
    finish_google_consent,
    get_google_connection_status,
    record_google_consent_failure,
)

router = APIRouter(prefix="/api/google/connection", tags=["google-connection"])
HTTP_URL_ADAPTER: TypeAdapter[HttpUrl] = TypeAdapter(HttpUrl)


def _session_token(request: Request, auth: AuthRuntime) -> str | None:
    assert auth.settings is not None
    _, name = cookie_names(auth.settings)
    return request.cookies.get(name)


def _browser_cookie(request: Request, auth: AuthRuntime) -> str | None:
    assert auth.settings is not None
    name, _ = cookie_names(auth.settings)
    return request.cookies.get(name)


def _require_configured_owner(
    auth: AuthRuntime, identity: tuple[str, datetime, str]
) -> None:
    assert auth.settings is not None
    if identity[0] != auth.settings.owner_sub:
        raise HTTPException(
            status_code=401,
            detail={"code": "auth_required", "message": "Sign in to continue."},
        )


def _require_origin_and_csrf(
    request: Request,
    auth: AuthRuntime,
    identity: tuple[str, datetime, str],
    csrf_token: str | None,
) -> None:
    assert auth.settings is not None
    if request.headers.get("origin") != auth.settings.web_origin:
        raise HTTPException(
            status_code=403,
            detail=GoogleConnectionErrorResponse(
                code=GoogleConnectionErrorCode.INVALID_CALLBACK,
                message="This request could not be verified.",
            ).model_dump(mode="json"),
        )
    if not csrf_token or not hmac.compare_digest(csrf_token, identity[2]):
        raise HTTPException(
            status_code=403,
            detail=GoogleConnectionErrorResponse(
                code=GoogleConnectionErrorCode.INVALID_CALLBACK,
                message="This request could not be verified.",
            ).model_dump(mode="json"),
        )


def _raise_failure(failure: GoogleConnectionFailure) -> NoReturn:
    code = failure.code
    status = (
        409
        if code is GoogleConnectionErrorCode.REVOCATION_PENDING
        else 401
        if code is GoogleConnectionErrorCode.SESSION_EXPIRED
        else 503
        if code
        in {
            GoogleConnectionErrorCode.PROVIDER_UNAVAILABLE,
            GoogleConnectionErrorCode.CREDENTIALS_UNAVAILABLE,
            GoogleConnectionErrorCode.REFRESH_BUSY,
        }
        else 400
    )
    messages = {
        GoogleConnectionErrorCode.PARTIAL_SCOPE: "Approve all requested permissions.",
        GoogleConnectionErrorCode.CONSENT_DENIED: "Google consent was denied.",
        GoogleConnectionErrorCode.IDENTITY_MISMATCH: "Select the configured owner.",
        GoogleConnectionErrorCode.SESSION_EXPIRED: "Sign in again.",
        GoogleConnectionErrorCode.INVALID_CALLBACK: "Restart the connection flow.",
        GoogleConnectionErrorCode.REFRESH_INVALID: "Reconnect the account.",
        GoogleConnectionErrorCode.PROVIDER_UNAVAILABLE: "Google is unavailable.",
        GoogleConnectionErrorCode.REFRESH_BUSY: "Refresh is still in progress.",
        GoogleConnectionErrorCode.CREDENTIALS_UNAVAILABLE: (
            "Credentials are unavailable."
        ),
        GoogleConnectionErrorCode.REVOCATION_PENDING: ("Resolve revoke first."),
    }
    raise HTTPException(
        status_code=status,
        detail=GoogleConnectionErrorResponse(
            code=code, message=messages[code]
        ).model_dump(mode="json"),
    )


def _connection_redirect(settings: AuthSettings, outcome: str) -> RedirectResponse:
    return RedirectResponse(f"{settings.web_origin}/?google={outcome}", status_code=303)


@router.get(
    "",
    response_model=GoogleConnectionResponse,
    responses={401: {}, 503: {}},
    operation_id="get_google_connection",
)
async def get_connection(
    request: Request,
    response: Response,
    identity: tuple[str, datetime, str] = Depends(protected_session),
) -> GoogleConnectionResponse:
    auth = require_auth_runtime(request)
    assert auth.settings is not None and auth.sessions is not None
    _require_configured_owner(auth, identity)
    response.headers["Cache-Control"] = "no-store"
    try:
        return await get_google_connection_status(
            auth.sessions, owner_sub=identity[0], settings=auth.settings
        )
    except Exception:
        raise HTTPException(
            status_code=503,
            detail=GoogleConnectionErrorResponse(
                code=GoogleConnectionErrorCode.PROVIDER_UNAVAILABLE,
                message="Google connection status is unavailable.",
            ).model_dump(mode="json"),
        ) from None


@router.post(
    "/consent",
    response_model=GoogleConsentResponse,
    responses={400: {}, 401: {}, 403: {}, 409: {}, 503: {}},
    operation_id="start_google_connection_consent",
)
async def consent(
    request: Request,
    response: Response,
    identity: tuple[str, datetime, str] = Depends(protected_session),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> GoogleConsentResponse:
    auth = require_auth_runtime(request)
    assert auth.settings is not None and auth.sessions is not None
    _require_origin_and_csrf(request, auth, identity, csrf_token)
    session_token = _session_token(request, auth)
    if not session_token:
        _raise_failure(GoogleConnectionFailure("session_expired"))
    browser_cookie = _browser_cookie(request, auth) or secrets.token_urlsafe(32)
    try:
        authorization = await begin_google_consent(
            auth.settings,
            auth.sessions,
            owner_sub=identity[0],
            owner_session_token=session_token,
            browser_cookie=browser_cookie,
        )
    except GoogleConnectionFailure as failure:
        _raise_failure(failure)
    browser_name, _ = cookie_names(auth.settings)
    set_cookie(
        response,
        name=browser_name,
        value=browser_cookie,
        secure=auth.settings.secure_cookie,
        max_age=600,
    )
    response.headers["Cache-Control"] = "no-store"
    return GoogleConsentResponse(
        authorization_url=HTTP_URL_ADAPTER.validate_python(authorization.url)
    )


@router.get(
    "/callback",
    include_in_schema=False,
    operation_id="complete_google_connection_consent",
)
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    auth = require_auth_runtime(request)
    assert auth.settings is not None and auth.sessions is not None
    session_token = _session_token(request, auth)
    browser_cookie = _browser_cookie(request, auth)
    if not session_token or not browser_cookie or not state or len(state) > 256:
        return _connection_redirect(auth.settings, "invalid_callback")
    try:
        attempt = await consume_google_consent_attempt(
            auth.sessions,
            settings=auth.settings,
            state=state,
            browser_cookie=browser_cookie,
            owner_session_token=session_token,
        )
    except Exception:
        return _connection_redirect(auth.settings, "unavailable")
    if attempt is None:
        return _connection_redirect(auth.settings, "invalid_callback")
    if error:
        await record_google_consent_failure(
            auth.sessions,
            settings=auth.settings,
            attempt=attempt,
            code=GoogleConnectionErrorCode.CONSENT_DENIED,
            owner_session_token=session_token,
        )
        return _connection_redirect(auth.settings, "consent_denied")
    if not code or len(code) > 2048:
        await record_google_consent_failure(
            auth.sessions,
            settings=auth.settings,
            attempt=attempt,
            code=GoogleConnectionErrorCode.INVALID_CALLBACK,
            owner_session_token=session_token,
        )
        return _connection_redirect(auth.settings, "invalid_callback")
    try:
        grant = await exchange_connection_code(
            code,
            client_id=auth.settings.google_client_id,
            client_secret=auth.settings.google_client_secret,
            callback_uri=auth.settings.google_connection_callback_uri,
            code_verifier=attempt.code_verifier,
            expected_nonce=attempt.nonce,
        )
        result = await finish_google_consent(
            auth.sessions,
            settings=auth.settings,
            attempt=attempt,
            owner_session_token=session_token,
            identity=grant.identity,
            token_bundle=grant.token_bundle,
            granted_scopes=grant.granted_scopes,
        )
    except GoogleConnectionFailure as failure:
        await record_google_consent_failure(
            auth.sessions,
            settings=auth.settings,
            attempt=attempt,
            code=failure.code,
            owner_session_token=session_token,
        )
        return _connection_redirect(auth.settings, "unavailable")
    except Exception:
        await record_google_consent_failure(
            auth.sessions,
            settings=auth.settings,
            attempt=attempt,
            code=GoogleConnectionErrorCode.PROVIDER_UNAVAILABLE,
            owner_session_token=session_token,
        )
        return _connection_redirect(auth.settings, "unavailable")
    if result is None:
        return _connection_redirect(auth.settings, "session_expired")
    status = await get_google_connection_status(
        auth.sessions,
        owner_sub=auth.settings.owner_sub,
        settings=auth.settings,
    )
    if status.error is GoogleConnectionErrorCode.IDENTITY_MISMATCH:
        return _connection_redirect(auth.settings, "identity_mismatch")
    return _connection_redirect(
        auth.settings,
        "connected" if result.value == "connected" else "reconnect_required",
    )


@router.post(
    "/disconnect",
    response_model=GoogleDisconnectResponse,
    responses={401: {}, 403: {}, 503: {}},
    operation_id="disconnect_google_connection",
)
async def disconnect(
    request: Request,
    response: Response,
    identity: tuple[str, datetime, str] = Depends(protected_session),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> GoogleDisconnectResponse:
    auth = require_auth_runtime(request)
    assert auth.settings is not None and auth.sessions is not None
    _require_origin_and_csrf(request, auth, identity, csrf_token)
    session_token = _session_token(request, auth)
    if not session_token:
        _raise_failure(GoogleConnectionFailure("session_expired"))
    try:
        result = await disconnect_google_connection(
            auth.sessions,
            settings=auth.settings,
            owner_session_token=session_token,
            workspace=GoogleWorkspaceClient(),
        )
    except GoogleConnectionFailure as failure:
        _raise_failure(failure)
    except Exception:
        _raise_failure(GoogleConnectionFailure("provider_unavailable"))
    response.headers["Cache-Control"] = "no-store"
    return result
