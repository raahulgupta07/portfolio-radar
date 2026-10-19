// End-to-end tests against a running stack (gateway + web) with demo data.
// Start the stack, then: npm run test:e2e
// The tests reset the demo data first (dev only).
import { defineConfig } from '@playwright/test';

export default defineConfig({
	testDir: 'e2e',
	globalSetup: './e2e/global-setup.ts',
	workers: 1,
	use: {
		baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5173',
		launchOptions: process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}
	}
});
