import {
  disconnectGoogleConnection as disconnectGoogleConnectionRequest,
  getGoogleConnection,
  startGoogleConnectionConsent,
  type GoogleConnectionErrorCode,
  type GoogleConnectionResponse,
  type GoogleDisconnectResponse,
} from '@api-generated';
import {
  zGoogleConnectionErrorCode,
  zGoogleConnectionResponse,
  zGoogleDisconnectResponse,
} from '@api-generated/zod.gen';
import * as z from 'zod';

const REQUEST_DEADLINE_MS = 5_000;
const strictConnection = z.strictObject(zGoogleConnectionResponse.shape);
const strictDisconnect = z.strictObject(zGoogleDisconnectResponse.shape);
const strictConnectionError = z.strictObject({
  code: zGoogleConnectionErrorCode,
  message: z.string(),
});
const strictErrorCode = z.enum([
  'partial_scope',
  'consent_denied',
  'identity_mismatch',
  'session_expired',
  'invalid_callback',
  'refresh_invalid',
  'provider_unavailable',
  'refresh_busy',
  'credentials_unavailable',
  'revocation_pending',
  'auth_required',
]);

export class GoogleConnectionApiError extends Error {
  constructor(
    readonly code:
      GoogleConnectionErrorCode | 'auth_required' | 'network_error',
  ) {
    super(code);
    this.name = 'GoogleConnectionApiError';
  }
}

export function isGoogleConnectionApiError(
  value: unknown,
): value is GoogleConnectionApiError {
  return (
    value instanceof GoogleConnectionApiError ||
    (typeof value === 'object' &&
      value !== null &&
      'code' in value &&
      strictErrorCode.safeParse(value.code).success)
  );
}

async function withRequest<T>(
  signal: AbortSignal,
  request: (requestSignal: AbortSignal) => Promise<T>,
): Promise<T> {
  const controller = new AbortController();
  const forwardAbort = () => controller.abort(signal.reason);
  if (signal.aborted) forwardAbort();
  else signal.addEventListener('abort', forwardAbort, { once: true });
  const timeout = window.setTimeout(
    () =>
      controller.abort(
        new DOMException(
          'Google connection request timed out.',
          'TimeoutError',
        ),
      ),
    REQUEST_DEADLINE_MS,
  );
  try {
    return await request(controller.signal);
  } catch (error) {
    const detail =
      typeof error === 'object' && error !== null && 'detail' in error
        ? (error as { detail?: unknown }).detail
        : undefined;
    const googleError = strictConnectionError.safeParse(detail);
    if (googleError.success) {
      throw new GoogleConnectionApiError(googleError.data.code);
    }
    if (typeof detail === 'object' && detail !== null && 'code' in detail) {
      const accessError = strictErrorCode.safeParse(detail.code);
      if (accessError.success && accessError.data === 'auth_required') {
        throw new GoogleConnectionApiError('auth_required');
      }
    }
    if (controller.signal.aborted) throw controller.signal.reason ?? error;
    throw new GoogleConnectionApiError('network_error');
  } finally {
    window.clearTimeout(timeout);
    signal.removeEventListener('abort', forwardAbort);
  }
}

export function fetchGoogleConnection(
  signal: AbortSignal,
): Promise<GoogleConnectionResponse> {
  return withRequest(signal, async (requestSignal) => {
    const { data } = await getGoogleConnection({
      baseUrl: window.location.origin,
      credentials: 'same-origin',
      signal: requestSignal,
      throwOnError: true,
      responseValidator: (value) => strictConnection.parseAsync(value),
    });
    return strictConnection.parse(data) as GoogleConnectionResponse;
  });
}

export function beginGoogleConnectionConsent(
  csrfToken: string,
  signal: AbortSignal,
): Promise<string> {
  return withRequest(signal, async (requestSignal) => {
    const { data } = await startGoogleConnectionConsent({
      baseUrl: window.location.origin,
      credentials: 'same-origin',
      signal: requestSignal,
      headers: { 'X-CSRF-Token': csrfToken },
      throwOnError: true,
    });
    return validateGoogleAuthorizationUrl(data.authorization_url);
  });
}

export function disconnectGoogleConnection(
  csrfToken: string,
  signal: AbortSignal,
): Promise<GoogleDisconnectResponse> {
  return withRequest(signal, async (requestSignal) => {
    const { data } = await disconnectGoogleConnectionRequest({
      baseUrl: window.location.origin,
      credentials: 'same-origin',
      signal: requestSignal,
      headers: { 'X-CSRF-Token': csrfToken },
      throwOnError: true,
      responseValidator: (value) => strictDisconnect.parseAsync(value),
    });
    return strictDisconnect.parse(data) as GoogleDisconnectResponse;
  });
}

function validateGoogleAuthorizationUrl(value: string): string {
  const authorizationUrl = new URL(value);
  if (
    authorizationUrl.origin !== 'https://accounts.google.com' ||
    authorizationUrl.pathname !== '/o/oauth2/v2/auth' ||
    authorizationUrl.username !== '' ||
    authorizationUrl.password !== '' ||
    authorizationUrl.hash !== ''
  ) {
    throw new GoogleConnectionApiError('network_error');
  }
  return authorizationUrl.href;
}

export function navigateToGoogleAuthorization(value: string): void {
  window.location.assign(validateGoogleAuthorizationUrl(value));
}
