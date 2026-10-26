import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../src/shared/api/google-connection', () => ({
  isGoogleConnectionApiError: (value: unknown) =>
    typeof value === 'object' && value !== null && 'code' in value,
  fetchGoogleConnection: vi.fn(),
  beginGoogleConnectionConsent: vi.fn(),
  disconnectGoogleConnection: vi.fn(),
  navigateToGoogleAuthorization: vi.fn(),
}));

import {
  beginGoogleConnectionConsent,
  disconnectGoogleConnection,
  fetchGoogleConnection,
  navigateToGoogleAuthorization,
} from '../../src/shared/api/google-connection';
import { GoogleConnectionPanel } from '../../src/features/google-connection/GoogleConnectionPanel';

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <GoogleConnectionPanel csrfToken="session-csrf" />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  window.history.replaceState({}, '', '/');
});

describe('Google connection panel', () => {
  it('shows connected status and warns before local disconnect', async () => {
    vi.mocked(fetchGoogleConnection).mockResolvedValue({ status: 'connected' });
    vi.mocked(disconnectGoogleConnection).mockResolvedValue({
      status: 'disconnected',
      revoke_outcome: 'confirmed',
      reconnect_blocked: false,
    });
    renderPanel();

    expect(
      await screen.findByText(/google workspace is connected/i),
    ).toBeTruthy();
    expect(
      screen.getByText(/may remove all permissions for this app/i),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /disconnect google/i }));
    await waitFor(() =>
      expect(disconnectGoogleConnection).toHaveBeenCalledWith(
        'session-csrf',
        expect.any(AbortSignal),
      ),
    );
  });

  it('offers one connection action while disconnected', async () => {
    vi.mocked(fetchGoogleConnection).mockResolvedValue({
      status: 'disconnected',
    });
    vi.mocked(beginGoogleConnectionConsent).mockResolvedValue(
      'https://accounts.google.com/authorize',
    );
    renderPanel();

    fireEvent.click(
      await screen.findByRole('button', { name: 'Connect Google' }),
    );
    await waitFor(() =>
      expect(vi.mocked(navigateToGoogleAuthorization).mock.calls[0]?.[0]).toBe(
        'https://accounts.google.com/authorize',
      ),
    );
  });

  it('shows exact missing scopes and blocks reconnect during unresolved revoke', async () => {
    vi.mocked(fetchGoogleConnection).mockResolvedValue({
      status: 'reconnect_required',
      error: 'partial_scope',
      missing_scopes: [
        'https://www.googleapis.com/auth/calendar.events.readonly',
      ],
      reconnect_blocked: true,
      revoke_outcome: 'unknown',
    });
    renderPanel();

    expect(await screen.findByText(/calendar.events.readonly/i)).toBeTruthy();
    expect(
      screen
        .getByRole('button', { name: /reconnect google/i })
        .hasAttribute('disabled'),
    ).toBe(true);
    expect(
      screen.getByRole('link', { name: 'Google Account permissions' }),
    ).toBeTruthy();
  });

  it('shows a safe callback hint without trusting arbitrary query values', async () => {
    window.history.replaceState(
      {},
      '',
      '/?google=identity_mismatch&token=secret',
    );
    vi.mocked(fetchGoogleConnection).mockResolvedValue({
      status: 'disconnected',
    });
    renderPanel();

    expect(
      await screen.findByText(/configured owner google account/i),
    ).toBeTruthy();
    expect(window.location.search).toBe('');
  });
});
