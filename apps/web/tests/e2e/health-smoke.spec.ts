import { expect, test } from '@playwright/test';

test('shows health returned by the actual API through the web proxy', async ({
  page,
}) => {
  const healthResponsePromise = page.waitForResponse((response) => {
    return new URL(response.url()).pathname === '/api/health';
  });

  await page.goto('/');

  const healthResponse = await healthResponsePromise;
  expect(healthResponse.status()).toBe(200);
  expect(new URL(healthResponse.url()).origin).toBe(new URL(page.url()).origin);
  expect(await healthResponse.json()).toEqual({ status: 'ok' });
  await expect(
    page.getByText('API is healthy.', { exact: true }),
  ).toBeVisible();
});
