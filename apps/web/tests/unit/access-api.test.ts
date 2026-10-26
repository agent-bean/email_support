import { afterEach, describe, expect, it, vi } from 'vitest';

const sdk = vi.hoisted(() => ({
  getOwnerSession: vi.fn(),
  getAccessPreauth: vi.fn(),
  startGoogleLogin: vi.fn(),
  logoutOwner: vi.fn(),
}));

vi.mock('@api-generated', () => sdk);

import {
  beginOwnerLogin,
  fetchOwnerSession,
  logoutOwnerSession,
} from '../../src/shared/api/access';

afterEach(() => {
  vi.clearAllMocks();
  vi.useRealTimers();
});

describe('owner access API', () => {
  it('validates the generated session contract strictly', async () => {
    sdk.getOwnerSession.mockResolvedValue({
      data: {
        csrf_token: 'x'.repeat(40),
        expires_at: '2026-10-27T00:00:00Z',
        unexpected: 'secret',
      },
    });
    await expect(
      fetchOwnerSession(new AbortController().signal),
    ).rejects.toThrow();
  });

  it('uses same-origin credentials and forwards cancellation', async () => {
    sdk.getOwnerSession.mockResolvedValue({
      data: {
        authenticated: true,
        csrf_token: 'x'.repeat(40),
        expires_at: '2026-10-27T00:00:00Z',
      },
    });
    const controller = new AbortController();
    await fetchOwnerSession(controller.signal);
    expect(sdk.getOwnerSession).toHaveBeenCalledWith(
      expect.objectContaining({
        credentials: 'same-origin',
        baseUrl: window.location.origin,
      }),
    );
    const options = sdk.getOwnerSession.mock.calls[0]?.[0] as
      { signal?: AbortSignal } | undefined;
    expect(options?.signal).toBeInstanceOf(AbortSignal);
  });

  it('uses in-memory preauth CSRF for login and sends same-origin credentials', async () => {
    sdk.getAccessPreauth.mockResolvedValue({
      data: { csrf_token: 'p'.repeat(40) },
    });
    sdk.startGoogleLogin.mockResolvedValue({
      data: {
        authorization_url:
          'https://accounts.google.com/o/oauth2/auth?state=opaque',
      },
    });
    await beginOwnerLogin(new AbortController().signal);
    expect(sdk.startGoogleLogin).toHaveBeenCalledWith(
      expect.objectContaining({
        credentials: 'same-origin',
        headers: { 'X-CSRF-Token': 'p'.repeat(40) },
      }),
    );
  });

  it('sends the session CSRF token for logout', async () => {
    sdk.getOwnerSession.mockResolvedValue({
      data: {
        authenticated: true,
        csrf_token: 's'.repeat(40),
        expires_at: '2026-10-27T00:00:00Z',
      },
    });
    sdk.logoutOwner.mockResolvedValue({ data: undefined });
    await logoutOwnerSession('s'.repeat(40), new AbortController().signal);
    expect(sdk.logoutOwner).toHaveBeenCalledWith(
      expect.objectContaining({
        credentials: 'same-origin',
        headers: { 'X-CSRF-Token': 's'.repeat(40) },
      }),
    );
  });

  it('propagates caller cancellation and clears the request deadline', async () => {
    const clearTimeout = vi.spyOn(window, 'clearTimeout');
    let requestSignal: AbortSignal | undefined;
    sdk.getOwnerSession.mockImplementation(
      ({ signal }: { signal: AbortSignal }) => {
        requestSignal = signal;
        return new Promise((_resolve, reject) =>
          signal.addEventListener(
            'abort',
            () =>
              reject(
                signal.reason instanceof Error
                  ? signal.reason
                  : new Error('request aborted'),
              ),
            { once: true },
          ),
        );
      },
    );
    const caller = new AbortController();
    const request = fetchOwnerSession(caller.signal);
    caller.abort(new DOMException('Canceled by caller.', 'AbortError'));
    await expect(request).rejects.toMatchObject({ name: 'AbortError' });
    expect(requestSignal?.aborted).toBe(true);
    expect(clearTimeout).toHaveBeenCalled();
  });

  it('aborts a request at its deadline and cleans up the timer', async () => {
    vi.useFakeTimers();
    const clearTimeout = vi.spyOn(window, 'clearTimeout');
    sdk.getOwnerSession.mockImplementation(
      ({ signal }: { signal: AbortSignal }) =>
        new Promise((_resolve, reject) =>
          signal.addEventListener(
            'abort',
            () =>
              reject(
                signal.reason instanceof Error
                  ? signal.reason
                  : new Error('request aborted'),
              ),
            { once: true },
          ),
        ),
    );
    const request = fetchOwnerSession(new AbortController().signal);
    const rejected = expect(request).rejects.toMatchObject({
      name: 'TimeoutError',
    });
    await vi.advanceTimersByTimeAsync(5_000);
    await rejected;
    expect(clearTimeout).toHaveBeenCalled();
  });
});
