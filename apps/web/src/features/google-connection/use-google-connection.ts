import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  beginGoogleConnectionConsent,
  disconnectGoogleConnection,
  fetchGoogleConnection,
} from '../../shared/api/google-connection';

export const googleConnectionKey = ['owner-data', 'google-connection'] as const;

export function useGoogleConnection(csrfToken: string) {
  const queryClient = useQueryClient();
  const connection = useQuery({
    queryKey: googleConnectionKey,
    queryFn: ({ signal }) => fetchGoogleConnection(signal),
    retry: false,
  });
  const consent = useMutation({
    mutationFn: ({ signal }: { signal: AbortSignal }) =>
      beginGoogleConnectionConsent(csrfToken, signal),
  });
  const disconnect = useMutation({
    mutationFn: ({ signal }: { signal: AbortSignal }) =>
      disconnectGoogleConnection(csrfToken, signal),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: googleConnectionKey });
    },
  });

  return { connection, consent, disconnect };
}
