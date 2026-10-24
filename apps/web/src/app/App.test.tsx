import { act, cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';

function jsonResponse(payload: unknown): Response {
  const body = JSON.stringify(payload);
  if (body === undefined) {
    throw new Error('The test response payload must be JSON serializable.');
  }

  return new Response(body, {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

function renderApp() {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('App health state', () => {
  it('shows a textual loading state while the request is pending', async () => {
    let resolveResponse: ((response: Response) => void) | undefined;
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(
        () =>
          new Promise<Response>((resolve) => {
            resolveResponse = resolve;
          }),
      ),
    );

    renderApp();

    expect((await screen.findByRole('status')).textContent).toBe(
      'Checking service health…',
    );

    const resolve = resolveResponse;
    if (!resolve) {
      throw new Error('The API request did not start.');
    }
    await act(async () => {
      resolve(jsonResponse({ status: 'ok' }));
      await Promise.resolve();
    });
  });

  it('shows healthy only after the generated contract validates', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({ status: 'ok' })),
    );

    renderApp();

    expect((await screen.findByText('API is healthy.')).textContent).toBe(
      'API is healthy.',
    );
  });

  it('shows an actionable error for a malformed successful response', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(jsonResponse({ status: 'degraded' })),
    );

    renderApp();

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('Check that the API is running');
    expect(screen.queryByText('API is healthy.')).toBeNull();
  });
});
