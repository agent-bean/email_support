import { expect, test } from '@playwright/test';

test('keeps the Google connection panel behind owner sign-in', async ({
  page,
}) => {
  await page.goto('/');

  await expect(
    page.getByRole('heading', { name: 'Google Workspace connection' }),
  ).toBeHidden();
  await expect(
    page.getByText(
      /signed out or your session expired|sign-in is unavailable/i,
    ),
  ).toBeVisible();
});
