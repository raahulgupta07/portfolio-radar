// City SSO through Keycloak, checking passwords against LDAP. Runs only against the SSO stack:
//   docker compose -f docker-compose.yml -f docker-compose.sso.yml up -d
//   E2E_SSO=1 E2E_BASE_URL=http://localhost:3000 npx playwright test sso
import { expect, test, type Page } from '@playwright/test';

test.skip(!process.env.E2E_SSO, 'needs the Keycloak + LDAP stack (docker-compose.sso.yml)');

async function sso(page: Page, user: string, password: string) {
	await page.goto('/login');
	await page.getByRole('button', { name: /City SSO/ }).click();
	await page.waitForURL(/\/realms\/city\//);
	await page.fill('#username', user);
	await page.fill('#password', password);
	await page.click('#kc-login');
}

test('LDAP viewer signs in through Keycloak and cannot open Admin', async ({ page }) => {
	await sso(page, 'min', 'viewer-pass');
	await expect(page.getByRole('heading', { name: 'Portfolio Overview' })).toBeVisible();
	expect((await page.goto('/admin'))!.status()).toBe(403);
});

test('a wrong LDAP password is refused by Keycloak', async ({ page }) => {
	await sso(page, 'min', 'wrong');
	await expect(page.getByText('Invalid username or password')).toBeVisible();
});

test('admin from the LDAP admins group sees People; a blocked person is refused', async ({ browser }) => {
	const admin = await (await browser.newContext()).newPage();
	await sso(admin, 'rahul', 'admin-pass');
	await admin.goto('/admin/people?edit=' + encodeURIComponent('min.thu@city.local'));
	await admin.check('input[name=blocked]');
	await admin.getByRole('button', { name: 'Save' }).click();
	await expect(admin.getByText('is blocked')).toBeVisible();

	const min = await (await browser.newContext()).newPage();
	await sso(min, 'min', 'viewer-pass');
	await expect(min.getByText('cannot use Portfolio Radar')).toBeVisible();

	await admin.goto('/admin/people?edit=' + encodeURIComponent('min.thu@city.local'));
	await admin.uncheck('input[name=blocked]');
	await admin.getByRole('button', { name: 'Save' }).click();
	await expect(admin.getByText('saved')).toBeVisible();
});
