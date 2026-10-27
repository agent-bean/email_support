import { expect, test } from '@playwright/test';

test('shows the owner auth surface without hiding public health', async ({
  page,
}) => {
  await page.goto('/');

  await expect(
    page.getByRole('heading', { name: 'Owner access' }),
  ).toBeVisible();
  await expect(
    page.getByText('API is healthy.', { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(
      /signed out or your session expired|sign-in is unavailable/i,
    ),
  ).toBeVisible();
});
