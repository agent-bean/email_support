import type { ReactNode } from 'react';
import { isAuthApiError } from '../../shared/api/auth';
import { useAuth } from './use-auth';

export function AuthPanel({
  ownerContent,
}: {
  ownerContent?: (csrfToken: string) => ReactNode;
}) {
  const { session, login, logout, signInHint } = useAuth();
  const failure = isAuthApiError(session.error)
    ? session.error.code
    : undefined;
  const callbackHint = signInHint;

  return (
    <section aria-labelledby="auth-heading">
      <h2 id="auth-heading">Owner access</h2>
      {session.isPending && (
        <p role="status" aria-label="Checking owner access">
          Checking owner access…
        </p>
      )}
      {session.isSuccess && (
        <>
          <p role="status">Signed in to owner access.</p>
          {ownerContent?.(session.data.csrf_token)}
          <button
            type="button"
            disabled={logout.isPending}
            onClick={() =>
              logout.mutate({
                csrfToken: session.data.csrf_token,
                signal: new AbortController().signal,
              })
            }
          >
            {logout.isPending ? 'Signing out…' : 'Sign out'}
          </button>
          {logout.isError && (
            <p role="alert">
              Sign-out could not be confirmed. Refreshing the session state.
            </p>
          )}
        </>
      )}
      {failure === 'auth_required' && (
        <div>
          <p role="status">
            {callbackHint === 'rejected'
              ? 'That Google account is not the configured owner. Choose the owner account and try again.'
              : callbackHint === 'restart'
                ? 'The sign-in request expired. Start again.'
                : callbackHint === 'unavailable'
                  ? 'Google sign-in did not finish. Check the provider response and try again.'
                  : 'You are signed out or your session expired. Sign in to continue.'}
          </p>
          <button
            type="button"
            disabled={login.isPending}
            onClick={() =>
              login.mutate({ signal: new AbortController().signal })
            }
          >
            {login.isPending
              ? 'Signing in…'
              : callbackHint === 'rejected'
                ? 'Try the owner account'
                : 'Sign in with Google'}
          </button>
        </div>
      )}
      {failure === 'auth_unavailable' && (
        <div>
          <p role="alert" aria-label="Sign-in unavailable">
            Sign-in is unavailable. Configure the local owner runtime or check
            that its service is running, then retry.
          </p>
          <button type="button" onClick={() => void session.refetch()}>
            Retry owner access
          </button>
        </div>
      )}
      {failure === 'network_error' && (
        <div>
          <p role="alert">
            Could not check owner access. Check the API connection and retry.
          </p>
          <button type="button" onClick={() => void session.refetch()}>
            Retry owner access
          </button>
        </div>
      )}
      {(failure === 'csrf_rejected' ||
        failure === 'login_rejected' ||
        failure === 'login_restart') && (
        <p role="alert">
          {failure === 'login_restart'
            ? 'The sign-in request expired. Start again.'
            : failure === 'login_rejected'
              ? 'That Google account is not the configured owner.'
              : 'The sign-in request could not be verified. Reload and try again.'}
        </p>
      )}
      {login.isError && (
        <p role="alert">
          Google sign-in could not start. Check the service and try again.
        </p>
      )}
    </section>
  );
}
