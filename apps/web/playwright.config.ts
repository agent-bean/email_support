import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: '*-smoke.spec.ts',
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  expect: { timeout: 5_000 },
  reporter: 'list',
  use: {
    baseURL: process.env.SMOKE_BASE_URL ?? 'http://127.0.0.1:5173',
    actionTimeout: 10_000,
    navigationTimeout: 10_000,
  },
});
