import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from '../../src/app/App';

vi.mock('../../src/shared/api/owner-auth', () => ({
  isOwnerAuthApiError: (value: unknown) =>
    typeof value === 'object' && value !== null && 'code' in value,
  fetchOwnerSession: vi.fn(),
  beginOwnerLogin: vi.fn(),
  logoutOwnerSession: vi.fn(),
  clearOwnerAuthMemory: vi.fn(),
  navigateToAuthorization: vi.fn(),
}));

import { fetchOwnerSession } from '../../src/shared/api/owner-auth';

function installHealthyApi() {
  vi.stubGlobal(
    'fetch',
    vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ status: 'ok' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  );
}

function renderApp() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  window.history.replaceState({}, '', '/');
});

describe('owner auth panel', () => {
  it('keeps the health panel while session state loads', async () => {
    installHealthyApi();
    let rejectSession: ((reason: Error) => void) | undefined;
    vi.mocked(fetchOwnerSession).mockImplementation(
      () =>
        new Promise((_resolve, reject) => {
          rejectSession = reject;
        }),
    );
    renderApp();
    expect(await screen.findByText('Checking service health…')).toBeTruthy();
    expect(
      screen.getByRole('status', { name: /checking owner access/i }),
    ).toBeTruthy();
    rejectSession?.(
      Object.assign(new Error('no owner session'), { code: 'auth_required' }),
    );
    expect(
      await screen.findByText(/signed out or your session expired/i),
    ).toBeTruthy();
    expect(await screen.findByText('API is healthy.')).toBeTruthy();
  });

  it('shows actionable auth unavailable and retains health', async () => {
    installHealthyApi();
    vi.mocked(fetchOwnerSession).mockRejectedValue(
      Object.assign(new Error('unavailable'), { code: 'auth_unavailable' }),
    );
    renderApp();
    expect(
      await screen.findByRole('alert', { name: /sign-in unavailable/i }),
    ).toBeTruthy();
    expect(await screen.findByText('API is healthy.')).toBeTruthy();
  });

  it('retries owner access after the runtime becomes available', async () => {
    installHealthyApi();
    vi.mocked(fetchOwnerSession)
      .mockRejectedValueOnce(
        Object.assign(new Error('unavailable'), { code: 'auth_unavailable' }),
      )
      .mockResolvedValueOnce({
        authenticated: true,
        csrf_token: 's'.repeat(40),
        expires_at: '2026-10-27T00:00:00Z',
      });
    renderApp();
    fireEvent.click(
      await screen.findByRole('button', { name: 'Retry owner access' }),
    );
    expect(await screen.findByText('Signed in to owner access.')).toBeTruthy();
  });

  it('shows owner rejection from an allowlisted callback hint', async () => {
    installHealthyApi();
    window.history.replaceState({}, '', '/?auth=rejected');
    vi.mocked(fetchOwnerSession).mockRejectedValue(
      Object.assign(new Error('required'), { code: 'auth_required' }),
    );
    renderApp();
    expect(
      await screen.findByText(/google account is not the configured owner/i),
    ).toBeTruthy();
  });

  it('shows a retryable provider failure from the callback hint', async () => {
    installHealthyApi();
    window.history.replaceState({}, '', '/?auth=unavailable');
    vi.mocked(fetchOwnerSession).mockRejectedValue(
      Object.assign(new Error('required'), { code: 'auth_required' }),
    );
    renderApp();
    expect(
      await screen.findByText(/google sign-in did not finish/i),
    ).toBeTruthy();
    expect(
      screen.getByRole('button', { name: /sign in with google/i }),
    ).toBeTruthy();
  });

  it('starts login from the accessible sign-in button', async () => {
    installHealthyApi();
    vi.mocked(fetchOwnerSession).mockRejectedValue(
      Object.assign(new Error('required'), { code: 'auth_required' }),
    );
    const { beginOwnerLogin } = await import('../../src/shared/api/owner-auth');
    vi.mocked(beginOwnerLogin).mockResolvedValue(
      'https://accounts.google.com/o/oauth2/auth',
    );
    renderApp();
    fireEvent.click(
      await screen.findByRole('button', { name: 'Sign in with Google' }),
    );
    await waitFor(() =>
      expect(beginOwnerLogin).toHaveBeenCalledWith(expect.any(AbortSignal)),
    );
    const { navigateToAuthorization } =
      await import('../../src/shared/api/owner-auth');
    await waitFor(() =>
      expect(navigateToAuthorization).toHaveBeenCalledWith(
        'https://accounts.google.com/o/oauth2/auth',
      ),
    );
  });

  it('sends the in-memory session CSRF token when signing out', async () => {
    installHealthyApi();
    vi.mocked(fetchOwnerSession)
      .mockResolvedValueOnce({
        authenticated: true,
        csrf_token: 's'.repeat(40),
        expires_at: '2026-10-27T00:00:00Z',
      })
      .mockRejectedValueOnce(
        Object.assign(new Error('signed out'), { code: 'auth_required' }),
      );
    const { logoutOwnerSession } =
      await import('../../src/shared/api/owner-auth');
    vi.mocked(logoutOwnerSession).mockResolvedValue(undefined);
    renderApp();
    fireEvent.click(await screen.findByRole('button', { name: 'Sign out' }));
    await waitFor(() =>
      expect(logoutOwnerSession).toHaveBeenCalledWith(
        's'.repeat(40),
        expect.any(AbortSignal),
      ),
    );
    expect(
      await screen.findByText(/signed out or your session expired/i),
    ).toBeTruthy();
  });
});
