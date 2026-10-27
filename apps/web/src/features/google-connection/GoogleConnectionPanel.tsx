import { useEffect, useState } from 'react';
import type { GoogleConnectionErrorCode } from '@api-generated';
import {
  isGoogleConnectionApiError,
  navigateToGoogleAuthorization,
} from '../../shared/api/google-connection';
import { useGoogleConnection } from './use-google-connection';

const CALLBACK_HINTS = [
  'connected',
  'reconnect_required',
  'consent_denied',
  'identity_mismatch',
  'invalid_callback',
  'session_expired',
  'unavailable',
] as const;

function callbackMessage(hint: string | undefined): string | undefined {
  switch (hint) {
    case 'connected':
      return 'Google Workspace permissions were saved.';
    case 'reconnect_required':
      return 'Google did not grant every required permission. Review the missing scopes and reconnect.';
    case 'consent_denied':
      return 'Google consent was denied. You can connect again when ready.';
    case 'identity_mismatch':
      return 'Choose the configured owner Google account and try again.';
    case 'invalid_callback':
      return 'The Google connection request expired or could not be verified. Start again.';
    case 'session_expired':
      return 'Your owner session expired. Sign in again before connecting Google.';
    case 'unavailable':
      return 'Google could not complete the connection. Check the local runtime and retry.';
    default:
      return undefined;
  }
}

function errorMessage(
  code: GoogleConnectionErrorCode | 'auth_required' | 'network_error',
) {
  switch (code) {
    case 'partial_scope':
      return 'Google did not grant every required permission. Reconnect to approve the missing scopes.';
    case 'consent_denied':
      return 'Google consent was denied.';
    case 'identity_mismatch':
      return 'Select the configured owner Google account.';
    case 'session_expired':
    case 'auth_required':
      return 'Your owner session expired. Sign in again, then retry.';
    case 'invalid_callback':
      return 'The Google connection request could not be verified. Start again.';
    case 'refresh_invalid':
      return 'Google rejected the saved credentials. Reconnect the account.';
    case 'provider_unavailable':
      return 'Google is unavailable. Retry after the provider recovers.';
    case 'refresh_busy':
      return 'Google credentials are being refreshed. Retry shortly.';
    case 'credentials_unavailable':
      return 'Saved Google credentials cannot be decrypted. Check the local encryption key and reconnect.';
    case 'revocation_pending':
      return 'Google may still have access. Resolve revocation before reconnecting.';
    case 'network_error':
      return 'Could not reach the Google connection service. Check the API and retry.';
  }
}

export function GoogleConnectionPanel({ csrfToken }: { csrfToken: string }) {
  const [callbackHint] = useState<string | undefined>(() => {
    const value = new URLSearchParams(window.location.search).get('google');
    return CALLBACK_HINTS.includes(value as (typeof CALLBACK_HINTS)[number])
      ? (value ?? undefined)
      : undefined;
  });
  const { connection, consent, disconnect } = useGoogleConnection(csrfToken);
  const status = connection.data;
  const connectError = isGoogleConnectionApiError(connection.error)
    ? connection.error.code
    : undefined;
  const consentError = isGoogleConnectionApiError(consent.error)
    ? consent.error.code
    : undefined;
  const disconnectError = isGoogleConnectionApiError(disconnect.error)
    ? disconnect.error.code
    : undefined;
  const hint = callbackMessage(callbackHint);

  useEffect(() => {
    if (!callbackHint) return;
    window.history.replaceState(
      {},
      '',
      `${window.location.pathname}${window.location.hash}`,
    );
  }, [callbackHint]);

  const reconnectBlocked = status?.reconnect_blocked ?? false;
  const needsReconnect =
    status?.status === 'reconnect_required' ||
    status?.error === 'credentials_unavailable' ||
    status?.error === 'refresh_invalid';

  return (
    <section aria-labelledby="google-connection-heading">
      <h2 id="google-connection-heading">Google Workspace connection</h2>
      {hint && <p role="status">{hint}</p>}
      {connection.isPending && (
        <p role="status" aria-label="Checking Google connection">
          Checking Google connection…
        </p>
      )}
      {connection.isError && (
        <div>
          <p role="alert">{errorMessage(connectError ?? 'network_error')}</p>
          <button type="button" onClick={() => void connection.refetch()}>
            Retry Google connection status
          </button>
        </div>
      )}
      {connection.isSuccess && status && (
        <>
          {status.status === 'connected' && !needsReconnect && (
            <p role="status">Google Workspace is connected.</p>
          )}
          {status.status === 'disconnected' && (
            <p role="status">Google Workspace is disconnected.</p>
          )}
          {needsReconnect && (
            <p role="status">Google Workspace needs to reconnect.</p>
          )}
          {status.granted_scopes && status.granted_scopes.length > 0 && (
            <p>Granted scopes: {status.granted_scopes.join(', ')}</p>
          )}
          {status.missing_scopes && status.missing_scopes.length > 0 && (
            <p>Missing permissions: {status.missing_scopes.join(', ')}</p>
          )}
          {status.error && <p role="alert">{errorMessage(status.error)}</p>}
          {status.revoke_outcome === 'unknown' && (
            <p role="alert">
              Google revocation is unconfirmed. Remove this app's access in your{' '}
              <a
                href="https://myaccount.google.com/permissions"
                target="_blank"
                rel="noreferrer"
              >
                Google Account permissions
              </a>
              .
            </p>
          )}
          {status.status === 'connected' && !needsReconnect && (
            <>
              <p>
                Disconnect may remove all permissions for this app and other
                clients in the same Google Cloud project.
              </p>
              <button
                type="button"
                disabled={disconnect.isPending}
                onClick={() =>
                  disconnect.mutate({ signal: new AbortController().signal })
                }
              >
                {disconnect.isPending ? 'Disconnecting…' : 'Disconnect Google'}
              </button>
            </>
          )}
          {status.status !== 'connected' || needsReconnect ? (
            <button
              type="button"
              disabled={consent.isPending || reconnectBlocked}
              onClick={() =>
                consent.mutate(
                  { signal: new AbortController().signal },
                  {
                    onSuccess: navigateToGoogleAuthorization,
                  },
                )
              }
            >
              {consent.isPending
                ? 'Opening Google…'
                : needsReconnect
                  ? 'Reconnect Google'
                  : 'Connect Google'}
            </button>
          ) : null}
          {disconnectError && (
            <p role="alert">{errorMessage(disconnectError)}</p>
          )}
          {consentError && <p role="alert">{errorMessage(consentError)}</p>}
          {reconnectBlocked && (
            <p role="alert">
              Reconnect is disabled until the existing Google revoke is
              resolved.
            </p>
          )}
        </>
      )}
    </section>
  );
}
