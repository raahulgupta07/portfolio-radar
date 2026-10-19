import { execSync } from 'node:child_process';
import { resolve } from 'node:path';

// Fresh demo data for every run: python -m app.adapter demo --reset (dev only).
export default function globalSetup() {
	const cmd = process.env.E2E_RESET_CMD ?? 'cd ../backend && . .venv/bin/activate && python -m app.adapter demo --reset';
	execSync(cmd, { stdio: 'ignore', shell: '/bin/bash', cwd: resolve('.') });
}
