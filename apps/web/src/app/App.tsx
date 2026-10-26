import { useQuery } from '@tanstack/react-query';
import { fetchHealth } from '../shared/api/health';
import { AccessPanel } from '../features/access/AccessPanel';

export function App() {
  const healthQuery = useQuery({
    queryKey: ['health'],
    queryFn: ({ signal }) => fetchHealth(signal),
    retry: false,
  });

  return (
    <main>
      <h1>Email Support</h1>
      <AccessPanel />
      {healthQuery.isPending && <p role="status">Checking service health…</p>}
      {healthQuery.isError && (
        <p role="alert">
          Could not verify the API health. Check that the API is running and
          reload.
        </p>
      )}
      {healthQuery.isSuccess && <p role="status">API is healthy.</p>}
    </main>
  );
}
