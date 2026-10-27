import { afterEach, describe, expect, it, vi } from 'vitest';

const sdk = vi.hoisted(() => ({
  getGoogleConnection: vi.fn(),
  startGoogleConnectionConsent: vi.fn(),
  disconnectGoogleConnection: vi.fn(),
}));

vi.mock('@api-generated', () => sdk);

import {
  beginGoogleConnectionConsent,
  disconnectGoogleConnection,
  fetchGoogleConnection,
} from '../../src/shared/api/google-connection';

afterEach(() => {
  vi.clearAllMocks();
  vi.useRealTimers();
});

describe('Google connection API', () => {
  it('strictly validates connection status and uses same-origin credentials', async () => {
    sdk.getGoogleConnection.mockResolvedValue({
      data: { status: 'connected', unexpected: 'token' },
    });

    await expect(
      fetchGoogleConnection(new AbortController().signal),
    ).rejects.toThrow();
  });

  it('sends CSRF on same-origin consent and disconnect requests', async () => {
    sdk.startGoogleConnectionConsent.mockResolvedValue({
      data: {
        authorization_url:
          'https://accounts.google.com/o/oauth2/v2/auth?client_id=test',
      },
    });
    sdk.disconnectGoogleConnection.mockResolvedValue({
      data: {
        status: 'disconnected',
        revoke_outcome: 'confirmed',
        reconnect_blocked: false,
        revoke_recorded_at: null,
      },
    });
    const signal = new AbortController().signal;

    await beginGoogleConnectionConsent('csrf-value', signal);
    await disconnectGoogleConnection('csrf-value', signal);

    const consentOptions = sdk.startGoogleConnectionConsent.mock
      .calls[0]?.[0] as
      | {
          baseUrl: string;
          credentials: string;
          headers: { 'X-CSRF-Token': string };
          signal: AbortSignal;
          throwOnError: boolean;
        }
      | undefined;
    const disconnectOptions = sdk.disconnectGoogleConnection.mock
      .calls[0]?.[0] as
      | {
          baseUrl: string;
          credentials: string;
          headers: { 'X-CSRF-Token': string };
          signal: AbortSignal;
          throwOnError: boolean;
        }
      | undefined;
    expect(consentOptions).toMatchObject({
      baseUrl: window.location.origin,
      credentials: 'same-origin',
      headers: { 'X-CSRF-Token': 'csrf-value' },
      throwOnError: true,
    });
    expect(consentOptions?.signal).toBeInstanceOf(AbortSignal);
    expect(disconnectOptions).toMatchObject({
      baseUrl: window.location.origin,
      credentials: 'same-origin',
      headers: { 'X-CSRF-Token': 'csrf-value' },
      throwOnError: true,
    });
    expect(disconnectOptions?.signal).toBeInstanceOf(AbortSignal);
  });

  it('reports a disconnect deadline as a visible network error', async () => {
    vi.useFakeTimers();
    sdk.disconnectGoogleConnection.mockImplementation(
      ({ signal }: { signal: AbortSignal }) =>
        new Promise((_, reject) => {
          signal.addEventListener(
            'abort',
            () => reject(new Error('request aborted')),
            { once: true },
          );
        }),
    );

    const result = disconnectGoogleConnection(
      'csrf-value',
      new AbortController().signal,
    );
    const expectation = expect(result).rejects.toMatchObject({
      code: 'network_error',
    });
    await vi.advanceTimersByTimeAsync(12_000);
    await expectation;
  });

  it('forwards caller cancellation and preserves its reason', async () => {
    let requestSignal: AbortSignal | undefined;
    sdk.getGoogleConnection.mockImplementation(
      ({ signal }: { signal: AbortSignal }) =>
        new Promise((_, reject) => {
          requestSignal = signal;
          signal.addEventListener(
            'abort',
            () => reject(signal.reason as Error),
            {
              once: true,
            },
          );
        }),
    );

    const controller = new AbortController();
    const reason = new DOMException('caller cancelled', 'AbortError');
    const result = fetchGoogleConnection(controller.signal);
    const expectation = expect(result).rejects.toBe(reason);
    controller.abort(reason);
    await expectation;

    expect(requestSignal?.aborted).toBe(true);
    expect(requestSignal?.reason).toBe(reason);
  });

  it.each([
    'https://attacker.example/',
    'https://attacker@accounts.google.com/o/oauth2/v2/auth',
    'https://accounts.google.com:444/o/oauth2/v2/auth',
    'https://accounts.google.com/not-the-oauth-endpoint',
  ])('rejects an unsafe authorization destination: %s', async (url) => {
    sdk.startGoogleConnectionConsent.mockResolvedValue({
      data: { authorization_url: url },
    });

    await expect(
      beginGoogleConnectionConsent('csrf-value', new AbortController().signal),
    ).rejects.toMatchObject({ code: 'network_error' });
  });
});
