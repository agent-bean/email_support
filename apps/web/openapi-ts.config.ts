import { defineConfig } from '@hey-api/openapi-ts';

export default defineConfig({
  input: '../backend/openapi.json',
  output: 'src/shared/api/generated',
  plugins: [
    '@hey-api/typescript',
    {
      name: '@hey-api/sdk',
      validator: {
        response: 'zod',
      },
    },
    '@hey-api/client-fetch',
    'zod',
  ],
});
