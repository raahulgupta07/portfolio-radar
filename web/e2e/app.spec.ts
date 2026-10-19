import { expect, test, type Page } from '@playwright/test';

async function signIn(page: Page, token: string) {
	await page.goto('/login');
	await page.click(`button[value="${token}"]`);
	await page.waitForURL('/');
}

test('sign-in is required', async ({ page }) => {
	await page.goto('/projects');
	await expect(page).toHaveURL(/\/login\?next=%2Fprojects/);
});

test('overview shows health, sources and Radar from MCP', async ({ page }) => {
	await signIn(page, 'dev-viewer');
	await expect(page.getByRole('heading', { name: 'Portfolio Overview' })).toBeVisible();
	const health = page.getByLabel('Portfolio health');
	await expect(health).toContainText('On track');
	await expect(health).toContainText('Off track');
	await expect(page.getByLabel('Data sources')).toContainText('Stale');
	await expect(page.getByLabel('Radar findings')).toContainText('POS03 milestone 4 days overdue');
	// Viewers get no Admin menu and no edit controls for project data.
	await expect(page.getByRole('link', { name: 'Admin and agent rules' })).toHaveCount(0);
	await page.getByRole('button', { name: 'Off track', exact: true }).click();
	await expect(page.locator('tbody tr')).toHaveCount(1);
});

test('project detail links to the source tool to edit', async ({ page }) => {
	await signIn(page, 'dev-viewer');
	await page.goto('/projects/CHL-DP-POS03');
	await expect(page.getByRole('heading', { name: 'POS Integration' })).toBeVisible();
	await expect(page.getByRole('link', { name: 'Open in JIRA to edit' })).toBeVisible();
	await expect(page.getByText('Vendor contract delayed')).toBeVisible();
});

test('one-pager PDFs for a project and the portfolio', async ({ page }) => {
	await signIn(page, 'dev-viewer');
	await page.goto('/projects/CHL-DP-POS03');
	const href = await page.getByRole('link', { name: 'One-pager PDF of this project' }).getAttribute('href');
	for (const url of [href!, '/export/portfolio.pdf']) {
		const r = await page.request.get(url);
		expect(r.status()).toBe(200);
		expect(r.headers()['content-type']).toBe('application/pdf');
		expect((await r.body()).subarray(0, 4).toString()).toBe('%PDF');
	}
	expect((await page.request.get('/projects/NOPE-1/one-pager.pdf')).status()).toBe(404);
});

test('viewer cannot approve; approver approves the digest', async ({ page }) => {
	await signIn(page, 'dev-viewer');
	await page.goto('/radar');
	await expect(page.getByRole('button', { name: 'Approve digest' })).toHaveCount(0);
	await page.context().clearCookies();

	await signIn(page, 'dev-approver');
	await page.goto('/radar');
	await expect(page.getByText('WAITING FOR YOU', { exact: true })).toBeVisible();
	await page.getByRole('button', { name: 'Approve digest' }).click();
	await expect(page.getByText(/Approved by pmo@cityholdings.dev/)).toBeVisible();
});

test('a question gets an answer with evidence', async ({ page }) => {
	await signIn(page, 'dev-viewer');
	await page.goto('/radar');
	await page.getByLabel('Message Radar').fill('How is POS03?');
	await page.getByRole('button', { name: 'Send' }).click();
	await expect(page.getByText('How is POS03?', { exact: true })).toBeVisible();
	// The worker answers through MCP; the page checks every 2 seconds.
	await expect(page.getByText(/Evidence: JIRA · CHL-DP-POS03/)).toBeVisible({ timeout: 20_000 });
});

test('admin sees the tool registry and audit log', async ({ page }) => {
	await signIn(page, 'dev-admin');
	await page.goto('/admin/tools');
	await expect(page.getByRole('heading', { name: 'MCP tools', exact: true })).toBeVisible();
	await expect(page.getByText('/portfolio/mcp', { exact: true })).toBeVisible();
	await page.goto('/admin/activity');
	await expect(page.getByRole('heading', { name: 'Activity' })).toBeVisible();
});

test('admin sets up a source from Connections; the token is never shown again', async ({ page }) => {
	await signIn(page, 'dev-admin');
	await page.goto('/admin/connections');
	await expect(page.getByText('City MCP Gateway · running')).toBeVisible();
	await page.goto('/admin/connections/openproject', { waitUntil: 'networkidle' });
	await page.fill('input[name=base_url]', 'https://openproject.city.local');
	await page.fill('input[name=token]', 'e2e-secret-value');
	await page.getByRole('button', { name: 'Save connection' }).click();
	await expect(page.getByText(/token is in the secret store as kv:\/\/openproject-read-token/)).toBeVisible();
	await expect(page.locator('input[name=token]')).toHaveValue('');
	expect(await page.content()).not.toContain('e2e-secret-value');
	await page.getByRole('button', { name: 'Run the check' }).click();
	await expect(page.getByText('Projects found')).toBeVisible();
});

test('viewers cannot open Connections', async ({ page }) => {
	await signIn(page, 'dev-viewer');
	const r = await page.goto('/admin/connections');
	expect(r?.status()).toBe(403);
});
