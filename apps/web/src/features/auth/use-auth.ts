import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import {
  beginOwnerLogin,
  clearAuthMemory,
  fetchOwnerSession,
  isAuthApiError,
  navigateToAuthorization,
  logoutOwnerSession,
} from '../../shared/api/auth';

export const ownerSessionKey = ['owner-session'] as const;

export function useAuth() {
  const queryClient = useQueryClient();
  const [signInHint, setSignInHint] = useState<string | undefined>(() => {
    const hint = new URLSearchParams(window.location.search).get('auth');
    return ['rejected', 'restart', 'unavailable'].includes(hint ?? '')
      ? (hint ?? undefined)
      : undefined;
  });
  const session = useQuery({
    queryKey: ownerSessionKey,
    queryFn: ({ signal }) => fetchOwnerSession(signal),
    retry: false,
  });
  useEffect(() => {
    if (
      isAuthApiError(session.error) &&
      session.error.code === 'auth_required'
    ) {
      clearAuthMemory();
      queryClient.removeQueries({
        predicate: (query) => query.queryKey[0] === 'owner-data',
      });
    }
  }, [queryClient, session.error]);

  const login = useMutation({
    mutationFn: ({ signal }: { signal: AbortSignal }) =>
      beginOwnerLogin(signal),
    onSuccess: (authorizationUrl) => {
      setSignInHint(undefined);
      navigateToAuthorization(authorizationUrl);
    },
  });
  const logout = useMutation({
    mutationFn: ({
      csrfToken,
      signal,
    }: {
      csrfToken: string;
      signal: AbortSignal;
    }) => logoutOwnerSession(csrfToken, signal),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ownerSessionKey });
      queryClient.removeQueries({
        predicate: (query) => query.queryKey[0] === 'owner-data',
      });
    },
    onError: async () => {
      await queryClient.invalidateQueries({ queryKey: ownerSessionKey });
    },
  });

  return {
    session,
    login,
    logout,
    signInHint,
  };
}
