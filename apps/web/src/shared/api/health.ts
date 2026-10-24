import { getHealth as getGeneratedHealth } from '@api-generated';
import type { HealthResponse } from '@api-generated';

const REQUEST_DEADLINE_MS = 5_000;

export async function fetchHealth(
  callerSignal: AbortSignal,
): Promise<HealthResponse> {
  const requestController = new AbortController();
  const forwardCallerAbort = () => requestController.abort(callerSignal.reason);

  if (callerSignal.aborted) {
    forwardCallerAbort();
  } else {
    callerSignal.addEventListener('abort', forwardCallerAbort, { once: true });
  }

  const deadlineReason = new DOMException(
    'The health request exceeded its 5 second deadline.',
    'TimeoutError',
  );
  const deadlineTimer = window.setTimeout(
    () => requestController.abort(deadlineReason),
    REQUEST_DEADLINE_MS,
  );

  try {
    const { data } = await getGeneratedHealth({
      baseUrl: window.location.origin,
      signal: requestController.signal,
      throwOnError: true,
    });
    return data;
  } finally {
    window.clearTimeout(deadlineTimer);
    callerSignal.removeEventListener('abort', forwardCallerAbort);
  }
}
