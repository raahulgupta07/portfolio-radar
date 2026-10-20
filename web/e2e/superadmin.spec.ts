// Superadmin sign-in. Runs when the gateway has a superadmin and the test knows its password:
//   E2E_SUPERADMIN_USER=superadmin E2E_SUPERADMIN_PASSWORD=... npx playwright test superadmin
import { expect, test } from '@playwright/test';

const user = process.env.E2E_SUPERADMIN_USER;
const password = process.env.E2E_SUPERADMIN_PASSWORD;
test.skip(!user || !password, 'needs E2E_SUPERADMIN_USER and E2E_SUPERADMIN_PASSWORD');

test('superadmin signs in with a password and reaches Admin; a wrong password is refused', async ({ page }) => {
	await page.goto('/login');
	const form = page.locator('form[action="?/local"]');
	if (!(await form.isVisible())) await page.getByText('Superadmin sign-in').click();
	await form.getByLabel('Name').fill(user!);
	await form.getByLabel('Password').fill('not the password');
	await form.getByRole('button', { name: 'Sign in as superadmin' }).click();
	await expect(page.getByRole('alert')).toContainText('Wrong name or password');

	await page.locator('form[action="?/local"]').getByLabel('Name').fill(user!);
	await page.locator('form[action="?/local"]').getByLabel('Password').fill(password!);
	await page.getByRole('button', { name: 'Sign in as superadmin' }).click();
	await expect(page.getByRole('heading', { name: 'Portfolio Overview' })).toBeVisible();
	await page.goto('/admin/people');
	await expect(page.getByRole('heading', { name: 'People' })).toBeVisible();
	// Not an approver: approvals stay with named people.
	await page.goto('/radar');
	await expect(page.getByRole('button', { name: /^Approve/ })).toHaveCount(0);
});
