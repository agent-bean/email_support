import { act, cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from '../../src/app/App';

vi.mock('../../src/shared/api/access', () => ({
  isAccessApiError: (value: unknown) =>
    typeof value === 'object' && value !== null && 'code' in value,
  fetchOwnerSession: vi
    .fn()
    .mockRejectedValue(
      Object.assign(new Error('signed out'), { code: 'auth_required' }),
    ),
  beginOwnerLogin: vi.fn(),
  logoutOwnerSession: vi.fn(),
  clearOwnerAccessMemory: vi.fn(),
  navigateToAuthorization: vi.fn(),
}));

vi.mock('../../src/shared/api/google-connection', () => ({
  fetchGoogleConnection: vi.fn(),
  beginGoogleConnectionConsent: vi.fn(),
  disconnectGoogleConnection: vi.fn(),
  navigateToGoogleAuthorization: vi.fn(),
  isGoogleConnectionApiError: (value: unknown) =>
    typeof value === 'object' && value !== null && 'code' in value,
}));

import { fetchOwnerSession } from '../../src/shared/api/access';
import { fetchGoogleConnection } from '../../src/shared/api/google-connection';

vi.mock('../../src/shared/api/access', () => ({
  isAccessApiError: (value: unknown) =>
    typeof value === 'object' && value !== null && 'code' in value,
  fetchOwnerSession: vi
    .fn()
    .mockRejectedValue(
      Object.assign(new Error('signed out'), { code: 'auth_required' }),
    ),
  beginOwnerLogin: vi.fn(),
  logoutOwnerSession: vi.fn(),
  clearOwnerAccessMemory: vi.fn(),
}));

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

    expect(
      (await screen.findByText('Checking service health…')).textContent,
    ).toBe('Checking service health…');

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

  it('keeps Google connection status hidden for a signed-out browser', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({ status: 'ok' })),
    );
    renderApp();

    expect(
      await screen.findByText(/signed out or your session expired/i),
    ).toBeTruthy();
    expect(
      screen.queryByRole('heading', { name: 'Google Workspace connection' }),
    ).toBeNull();
    expect(fetchGoogleConnection).not.toHaveBeenCalled();
  });

  it('mounts Google connection status for an authenticated owner', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({ status: 'ok' })),
    );
    vi.mocked(fetchOwnerSession).mockResolvedValueOnce({
      authenticated: true,
      csrf_token: 's'.repeat(40),
      expires_at: '2026-10-27T00:00:00Z',
    });
    vi.mocked(fetchGoogleConnection).mockResolvedValueOnce({
      status: 'disconnected',
    });
    renderApp();

    expect(
      await screen.findByRole('heading', {
        name: 'Google Workspace connection',
      }),
    ).toBeTruthy();
    expect(fetchGoogleConnection).toHaveBeenCalledWith(expect.any(AbortSignal));
  });
});
