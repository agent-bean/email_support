import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchHealth } from './health';

function jsonResponse(payload: unknown, status = 200): Response {
  const body = JSON.stringify(payload);
  if (body === undefined) {
    throw new Error('The test response payload must be JSON serializable.');
  }

  return new Response(body, {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function isErrorLike(reason: unknown): reason is Error {
  return (
    reason instanceof Error ||
    (typeof reason === 'object' &&
      reason !== null &&
      'name' in reason &&
      typeof reason.name === 'string' &&
      'message' in reason &&
      typeof reason.message === 'string')
  );
}

function abortError(signal: AbortSignal): Error {
  return isErrorLike(signal.reason)
    ? signal.reason
    : new Error('The Fetch request was aborted.');
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('fetchHealth', () => {
  it('returns the response validated by the generated SDK', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(jsonResponse({ status: 'ok' }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchHealth(new AbortController().signal)).resolves.toEqual({
      status: 'ok',
    });

    const request = fetchMock.mock.calls[0]?.[0];
    expect(request).toBeInstanceOf(Request);
    if (!(request instanceof Request)) {
      throw new Error('The generated operation did not issue a Fetch Request.');
    }
    expect(new URL(request.url).pathname).toBe('/api/health');
    expect(request.method).toBe('GET');
  });

  it.each([{}, { status: 'degraded' }])(
    'rejects malformed response payloads: %j',
    async (payload) => {
      vi.stubGlobal(
        'fetch',
        vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(payload)),
      );

      await expect(
        fetchHealth(new AbortController().signal),
      ).rejects.toHaveProperty('name', 'ZodError');
    },
  );

  it('rejects non-success HTTP responses', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(jsonResponse({ detail: 'unavailable' }, 503)),
    );

    await expect(
      fetchHealth(new AbortController().signal),
    ).rejects.toBeTruthy();
  });

  it('rejects invalid JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(
        new Response('{', {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );

    await expect(
      fetchHealth(new AbortController().signal),
    ).rejects.toBeInstanceOf(SyntaxError);
  });

  it('surfaces network failures', async () => {
    const networkError = new TypeError('Network unavailable');
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockRejectedValue(networkError),
    );

    await expect(fetchHealth(new AbortController().signal)).rejects.toBe(
      networkError,
    );
  });

  it('forwards caller cancellation and preserves its reason', async () => {
    vi.useFakeTimers();
    const controller = new AbortController();
    const reason = new DOMException('Query cancelled', 'AbortError');
    let observedSignal: AbortSignal | undefined;
    let notifyFetchStarted: () => void = () => undefined;
    const fetchStarted = new Promise<void>((resolve) => {
      notifyFetchStarted = resolve;
    });

    const fetchMock = vi.fn<typeof fetch>((input) => {
      if (!(input instanceof Request)) {
        throw new TypeError('Expected the generated client to pass a Request.');
      }

      const signal = input.signal;
      observedSignal = signal;
      notifyFetchStarted();

      return new Promise<Response>((_resolve, reject) => {
        const rejectForAbort = () => reject(abortError(signal));
        if (signal.aborted) {
          rejectForAbort();
        } else {
          signal.addEventListener('abort', rejectForAbort, { once: true });
        }
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    const request = fetchHealth(controller.signal);
    await fetchStarted;
    controller.abort(reason);

    await expect(request).rejects.toBe(reason);
    expect(observedSignal?.aborted).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('honors an already-aborted caller signal', async () => {
    const controller = new AbortController();
    const reason = new DOMException('Query already cancelled', 'AbortError');
    controller.abort(reason);

    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>((input) => {
        if (!(input instanceof Request)) {
          throw new TypeError(
            'Expected the generated client to pass a Request.',
          );
        }
        return Promise.reject(abortError(input.signal));
      }),
    );

    await expect(fetchHealth(controller.signal)).rejects.toBe(reason);
  });

  it('aborts the generated request when its deadline expires', async () => {
    vi.useFakeTimers();
    let observedSignal: AbortSignal | undefined;
    let notifyFetchStarted: () => void = () => undefined;
    const fetchStarted = new Promise<void>((resolve) => {
      notifyFetchStarted = resolve;
    });
    const fetchMock = vi.fn<typeof fetch>((input) => {
      if (!(input instanceof Request)) {
        throw new TypeError('Expected the generated client to pass a Request.');
      }

      observedSignal = input.signal;
      notifyFetchStarted();
      return new Promise<Response>((_resolve, reject) => {
        input.signal.addEventListener(
          'abort',
          () => reject(abortError(input.signal)),
          { once: true },
        );
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    const request = fetchHealth(new AbortController().signal);
    await fetchStarted;
    const deadlineFailure = expect(request).rejects.toMatchObject({
      name: 'TimeoutError',
    });
    await vi.advanceTimersByTimeAsync(5_000);

    await deadlineFailure;
    expect(observedSignal?.aborted).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('cleans up the deadline timer and caller listener after success', async () => {
    vi.useFakeTimers();
    const controller = new AbortController();
    const removeListener = vi.spyOn(controller.signal, 'removeEventListener');
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({ status: 'ok' })),
    );

    await fetchHealth(controller.signal);

    expect(vi.getTimerCount()).toBe(0);
    expect(removeListener).toHaveBeenCalledWith('abort', expect.any(Function));
  });
});
