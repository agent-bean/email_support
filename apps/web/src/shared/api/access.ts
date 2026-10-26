import {
  getAccessPreauth,
  getOwnerSession,
  logoutOwner,
  startGoogleLogin,
  type AccessErrorCode,
  type OwnerSession,
} from '@api-generated';
import {
  zAccessError,
  zOwnerSession,
  zPreauthResponse,
  zLoginResponse,
} from '@api-generated/zod.gen';
import * as z from 'zod';

const REQUEST_DEADLINE_MS = 5_000;
const strictOwnerSession = z.strictObject(zOwnerSession.shape);
const strictPreauth = z.strictObject(zPreauthResponse.shape);
const strictLogin = z.strictObject(zLoginResponse.shape);
const strictAccessError = z.strictObject(zAccessError.shape);

export class AccessApiError extends Error {
  constructor(readonly code: AccessErrorCode | 'network_error') {
    super(code);
    this.name = 'AccessApiError';
  }
}

export function isAccessApiError(value: unknown): value is AccessApiError {
  return (
    value instanceof AccessApiError ||
    (typeof value === 'object' &&
      value !== null &&
      'code' in value &&
      (value.code === 'auth_unavailable' ||
        value.code === 'auth_required' ||
        value.code === 'csrf_rejected' ||
        value.code === 'login_rejected' ||
        value.code === 'login_restart' ||
        value.code === 'network_error'))
  );
}

let preauthCsrf: string | undefined;

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
        new DOMException('Access request timed out.', 'TimeoutError'),
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
    const parsed = strictAccessError.safeParse(detail);
    if (parsed.success) throw new AccessApiError(parsed.data.code);
    if (controller.signal.aborted) throw controller.signal.reason ?? error;
    throw new AccessApiError('network_error');
  } finally {
    window.clearTimeout(timeout);
    signal.removeEventListener('abort', forwardAbort);
  }
}

export function fetchOwnerSession(signal: AbortSignal): Promise<OwnerSession> {
  return withRequest(signal, async (requestSignal) => {
    const { data } = await getOwnerSession({
      baseUrl: window.location.origin,
      credentials: 'same-origin',
      signal: requestSignal,
      throwOnError: true,
      responseValidator: (data) => strictOwnerSession.parseAsync(data),
    });
    return strictOwnerSession.parse(data);
  });
}

export function beginOwnerLogin(signal: AbortSignal): Promise<string> {
  return withRequest(signal, async (requestSignal) => {
    const preauth = await getAccessPreauth({
      baseUrl: window.location.origin,
      credentials: 'same-origin',
      signal: requestSignal,
      throwOnError: true,
      responseValidator: (data) => strictPreauth.parseAsync(data),
    });
    const checkedPreauth = strictPreauth.parse(preauth.data);
    preauthCsrf = checkedPreauth.csrf_token;
    const login = await startGoogleLogin({
      baseUrl: window.location.origin,
      credentials: 'same-origin',
      signal: requestSignal,
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': preauthCsrf,
      },
      throwOnError: true,
      responseValidator: (data) => strictLogin.parseAsync(data),
    });
    const checkedLogin = strictLogin.parse(login.data);
    const destination = new URL(checkedLogin.authorization_url);
    if (
      destination.protocol !== 'https:' ||
      destination.hostname !== 'accounts.google.com'
    ) {
      throw new Error(
        'The identity provider returned an unsafe authorization destination.',
      );
    }
    return destination.href;
  });
}

export function clearOwnerAccessMemory(): void {
  preauthCsrf = undefined;
}

export function navigateToAuthorization(authorizationUrl: string): void {
  window.location.assign(authorizationUrl);
}

export function logoutOwnerSession(
  csrfToken: string,
  signal: AbortSignal,
): Promise<void> {
  clearOwnerAccessMemory();
  return withRequest(signal, async (requestSignal) => {
    await logoutOwner({
      baseUrl: window.location.origin,
      credentials: 'same-origin',
      signal: requestSignal,
      headers: { 'X-CSRF-Token': csrfToken },
      throwOnError: true,
    });
  });
}
