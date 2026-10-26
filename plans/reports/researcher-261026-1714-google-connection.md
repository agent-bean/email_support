# Google Gmail and Calendar connection security research

**Research conducted:** 2026-10-26 (Asia/Bangkok)
**Scope:** Issue #6 connection planning only; no repository code or production configuration changed.
**Constraints:** `--hard --tdd --yagni`; one configured owner Google identity; Gmail readonly/send, read-only primary and shared calendars; login remains separate from provider consent.

## Recommendation

Implement one Google OAuth authorization-code flow in the FastAPI backend, bound to the already authenticated owner by the verified Google OIDC `sub`. Keep application login independent: `/auth/google` authenticates the app; a distinct owner-only connect action requests Gmail/Calendar consent. Add `openid email` to the OAuth grant to obtain and validate the account subject; require exact `sub` equality with the configured owner. Do not infer identity from email alone.

Request this single minimal grant:

- `openid`, `email` for identity binding.
- `https://www.googleapis.com/auth/gmail.readonly` and `https://www.googleapis.com/auth/gmail.send` for Issue #6's read and future guarded send capability.
- `https://www.googleapis.com/auth/calendar.events.readonly` and `https://www.googleapis.com/auth/calendar.calendarlist.readonly` to enumerate calendars the owner can access (including secondary/shared calendars) and read their events.

Request `access_type=offline`, `include_granted_scopes=true`, `state`, `nonce`, and PKCE S256. Validate callback state, OIDC issuer/audience/expiry/nonce, exact subject, and the returned granted scope set before enabling any provider feature. Do not silently downgrade a required capability. A partial grant records only granted scopes, disables the corresponding feature, and reports which owner action is needed. Only re-prompt after the owner explicitly selects the disabled feature; use incremental consent if later scope expansion is needed. Google recommends narrow scopes, checking returned scopes, and handling denied scopes explicitly. [OAuth web-server flow](https://developers.google.com/identity/protocols/oauth2/web-server), [granular permissions](https://developers.google.com/identity/protocols/oauth2/resources/granular-permissions), [OAuth best practices](https://developers.google.com/identity/protocols/oauth2/resources/best-practices).

## Library and encryption choices

**Use Authlib 1.9.1 `AsyncOAuth2Client` with the existing `httpx2` dependency and call Gmail and Calendar REST endpoints directly.** Authlib 1.8 switched this integration to `httpx2`; its current install guide explicitly pairs Authlib with `httpx2`, and its async client supports authorization-code exchange and refresh. The backend already has `httpx2>=2.16.0`, so add Authlib as a direct dependency and lock it; avoid depending on Authlib’s deprecated fallback to `httpx`. Direct REST avoids introducing the synchronous `google-api-python-client` transport into async request/worker code. Authlib is a third-party dependency, so pin and review upgrades. [Authlib 1.9.1 HTTP client docs](https://docs.authlib.org/en/stable/oauth2/client/http/index.html), [installation requirements](https://docs.authlib.org/en/latest/basic/install.html), [changelog: httpx2 switch](https://docs.authlib.org/en/stable/upgrades/changelog.html), [Google server-side OAuth](https://developers.google.com/identity/protocols/oauth2/web-server).

Encrypt refresh tokens in the application boundary with **AES-256-GCM using Python `cryptography`**, and keep the key outside PostgreSQL in deployment secret configuration. Store key version alongside ciphertext for rotation. Bind ciphertext to immutable connection ID and provider using associated authenticated data. Persist one encrypted credential bundle containing the refresh token, cached access token, and access-token expiry. This is required for the cross-process refresh lease below: after waiting for the lease holder, another process must be able to read and reuse the newly refreshed access token instead of refreshing again. Encrypt the whole bundle with AES-GCM and AAD; expose tokens only in memory to the provider adapter. Fail closed if the key is missing, malformed, or cannot decrypt. Do not invent a home-grown cipher or put the key beside ciphertext in the database. This fits the architecture's rule that refresh tokens be encrypted and the key external to DB; a managed KMS can replace the deployment secret later if operational needs justify it. Google explicitly requires encrypted-at-rest tokens and secure client credentials. [Google OAuth policies](https://developers.google.com/identity/protocols/oauth2/policies), [OAuth best practices](https://developers.google.com/identity/protocols/oauth2/resources/best-practices), [cryptography AES-GCM documentation](https://cryptography.io/en/latest/hazmat/primitives/aead/#cryptography.hazmat.primitives.ciphers.aead.AESGCM).

## Storage contracts

Keep `provider_accounts` as the canonical owner/provider identity record. Add one `google_connections` row keyed by `provider_account_id` (unique FK, restricted delete) with:

- `google_sub` (unique, nonblank); email is display metadata, never the authorization key.
- `granted_scopes` as a validated string array; required feature checks compare exact scope identifiers.
- `credential_bundle_ciphertext`, `encryption_key_version`, and `connected_at`; the encrypted bundle contains refresh token, cached access token, and access-token expiry. Never add plaintext token columns.
- `status`: `connected | refresh_required | disconnecting | disconnected`; provider failures do not silently reset consent.
- `credential_version` integer for compare-and-swap; `refresh_lease_owner` UUID and `refresh_lease_until` nullable timestamp; `disconnect_requested_at` nullable timestamp.
- timestamps and `last_provider_error_code` from an allowlisted enum only (never provider response body/token).

Do not put OAuth response bodies, authorization codes, state/nonce, ID token, access token, refresh token, or calendar/event payload in logs. Store one-time state, nonce, and PKCE verifier server-side with short expiry, owner/session binding, and consume-once semantics. Use owner-scoped service methods; never expose raw token fields in Pydantic response contracts. Application models should follow existing frozen `PersistenceContract` patterns; SQLAlchemy schema/migration owns database constraints.

## Refresh/disconnect races with only API and worker processes

Do not rely on an in-memory `asyncio.Lock`: API and worker are separate processes. Claim a bounded PostgreSQL refresh lease using a conditional update (`connected`, lease absent/expired, expected `credential_version`) and commit that claim before making HTTP calls. The lease holder decrypts and refreshes outside the DB transaction, then writes only if the lease owner, credential version, and `status=connected` still match. On refresh response with no `refresh_token`, retain the existing refresh token in the encrypted bundle; never overwrite it with null. Encrypt the returned access token, expiry, and any replacement refresh token into one bundle and replace atomically. Google documents that refresh responses may omit the refresh token and that tokens should be saved securely and reused; [web-server refresh-token guidance](https://developers.google.com/identity/protocols/oauth2/web-server). On `invalid_grant`, mark `refresh_required`, disable provider calls, and require owner reconnect. On transient/network failure, release/expire the lease and preserve the existing token.

Other callers that fail to claim must wait briefly with a bounded deadline, then re-read/decrypt the credential bundle and reuse the refreshed access token if it remains valid beyond a small expiry skew; do not launch another refresh in parallel. If the holder fails, expires its lease, or returns a token already near expiry, a caller may claim a new lease and refresh. Use bounded retries and cancellation-safe cleanup. A refresh lease is coordination, not durable background work; add jobs only when Issue #7 synchronization exists.

Disconnect first atomically marks `disconnecting` and advances `credential_version`. This immediately blocks new provider calls and makes an in-flight refresh unable to commit. Send the stored refresh token to Google's revoke endpoint outside the DB transaction. Then purge ciphertext and mark `disconnected` whether revocation succeeds, times out, or returns an ambiguous error; report revocation as `confirmed`, `already_invalid`, or `unknown`, and never resume provider work from `unknown`. Keep only a non-secret audit status/time. A request already sent to Google cannot be recalled, so active provider operations must check connection state immediately before each external call and before committing results.

**Critical shared-project behavior:** Google documents that revoking a token removes all OAuth scopes previously granted to a project and invalidates issued access/refresh tokens for all clients registered in that project; propagation may take time. Disconnect therefore affects every same-project client for the same user's grant, not only this application client. Keep all clients that share the project in mind, show that consequence before owner-initiated disconnect, and do not claim immediate provider-side revocation. [Google web-server revocation](https://developers.google.com/identity/protocols/oauth2/web-server), [Google OAuth client guidance](https://developers.google.com/identity/protocols/oauth2/native-app).

## Development and operational constraints

- For an External consent screen in **Testing**, non-profile refresh tokens expire after seven days. Do not mistake this for a refresh race or production behavior; production smoke requires the Cloud OAuth app in the correct published state and approved scopes. [Google OAuth token lifetime](https://developers.google.com/identity/protocols/oauth2#expiration).
- Refresh tokens can become invalid after user revocation, six months unused, password changes for Gmail scopes, token limits, time-based access expiry, or admin policy. Treat `invalid_grant` as a reconnect state, not a retry loop. [Google OAuth refresh-token expiration](https://developers.google.com/identity/protocols/oauth2#expiration), [Google best practices](https://developers.google.com/identity/protocols/oauth2/resources/best-practices).
- `gmail.readonly` is a **restricted** scope and `gmail.send` is **sensitive** (not restricted) in Google’s current Gmail scope table. The former can require verification and a security assessment when restricted-scope data is stored/transmitted; the latter requires sensitive-scope verification. Calendar list/events readonly scopes are sensitive. Confirm project consent-screen publishing and verification requirements before any external owner test. [Gmail scope classifications](https://developers.google.com/workspace/gmail/api/auth/scopes), [OAuth consent-screen scope categories](https://developers.google.com/workspace/guides/configure-oauth-consent), [Calendar scopes](https://developers.google.com/workspace/calendar/api/auth).

## TDD acceptance matrix

| Layer | Given / when | Required assertion |
| --- | --- | --- |
| OAuth state | Callback state is missing, mismatched, expired, or replayed | Reject; no token exchange or persistence. |
| Owner binding | Valid callback resolves a Google `sub` different from configured owner | Reject and do not create/update connection. Same email with different `sub` also rejects. |
| OIDC validation | Invalid issuer/audience/nonce/expiry/signature | Reject before persisting scopes or token. |
| Scopes | Full grant | Persist exactly normalized granted scopes; connection features enabled. |
| Partial consent | Gmail or Calendar scope subset absent | Persist actual scope set; only dependent capability disabled; no API call using missing scope; re-prompt only on explicit feature intent. |
| Encryption | Persist token, then inspect SQL row/log capture | Encrypted credential bundle only in DB; key absent from DB; no tokens/codes/PII in logs; cached access token is encrypted with expiry. Wrong key/AAD/tag fails closed. |
| Reauthorization | Existing connection receives no `refresh_token` | Preserve old refresh token inside bundle. Returned access token/expiry update bundle; returned replacement refresh token atomically replaces old one. |
| Refresh single-flight | Concurrent API and worker refresh requests | Exactly one lease holder performs HTTP refresh; followers re-read/decrypt and reuse cached access token; token/version updates are atomic. |
| Refresh crash | Lease expires after holder crash | Another caller can claim after expiry; stale holder cannot commit. |
| Refresh versus disconnect | Disconnect advances version during refresh | Refresh result cannot restore token or connected status; later provider call is blocked. |
| Invalid refresh | Google returns `invalid_grant` | Set `refresh_required`; no repeated automatic attempt; owner reconnect path available. |
| Disconnect confirmed | Revoke returns success | Stop provider work first, then purge encrypted credential and mark disconnected. |
| Disconnect uncertain | Timeout, connection error, or ambiguous non-success | Locally purge and block all new provider work; report `unknown`, never claim confirmed provider revocation. |
| Project side effect | Disconnect UX/API contract | Explicitly disclose same-project grant revocation affects all clients/scopes for this user; do not assert instantaneous effect. |
| API boundary | Read-only mailbox/calendar operation | Only documented readonly endpoints called; scope guard prevents send operation outside authorized action path. |

## Live smoke acceptance (opt-in, minimal)

Using the configured owner account and a non-production Google Cloud project: complete separate app login then Google consent; validate subject equals configured owner; read only a minimal Gmail profile/message header and one event from a secondary/shared calendar; make **no send call**; disconnect; verify local ciphertext is purged, new provider calls fail locally, and Google grant status is checked manually after propagation. Record no OAuth credentials or message/calendar content in evidence. This smoke proves only the exercised read/consent/revoke path, not Issue #7 synchronization or Issue #15 sending.

## Scope boundary and next steps

**Needed for Issue #6:** login/consent separation, owner `sub` binding, minimal scopes and partial-grant behavior, offline authorization, encrypted refresh-token persistence, refresh single-flight/CAS, disconnect blocking/purge/uncertain reporting, focused unit+PostgreSQL concurrency tests, and the minimal live smoke above.

**Defer:** durable sync jobs/cursors, incremental mailbox/calendar ingestion, scheduling, retries/reconciliation for synchronization (Issue #7); send execution, approval-bound action records, uncertain-send reconciliation, and any Gmail write scope beyond `gmail.send` (Issue #15). Do not introduce a general credential vault, KMS integration, worker queue, multi-account model, or sync architecture for this connection issue.

**Unresolved questions:** none for this plan. The owner must still provision the OAuth project/client and external consent-screen publishing/verification status before the live smoke; this is an operational prerequisite, not an architectural choice.
