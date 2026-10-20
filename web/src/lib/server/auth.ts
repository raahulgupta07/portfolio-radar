// Sign-in. Production: City SSO with OpenID Connect (code flow with PKCE), through
// Microsoft Entra ID or Keycloak (Keycloak can check passwords against LDAP). The
// access token goes to the gateway, which checks it and the person's groups on every
// call. Dev: pick a sample user (only when DEV_LOGIN=true).
import { createHash, randomBytes } from 'node:crypto';
import { env } from '$env/dynamic/private';

export const SESSION_COOKIE = 'pr_session';
export const USER_COOKIE = 'pr_user';
export const OIDC_COOKIE = 'pr_oidc';

export type DevUser = { token: string; name: string; label: string; roles: string[] };

export function devLoginEnabled(): boolean {
	return env.DEV_LOGIN === 'true';
}

export function devUsers(): DevUser[] {
	if (!devLoginEnabled()) return [];
	try {
		return JSON.parse(env.DEV_USERS || '[]');
	} catch {
		return [];
	}
}

/** City SSO through OpenID Connect: Microsoft Entra ID, or Keycloak (which can sign people in against LDAP). */
type Sso = {
	provider: 'entra' | 'keycloak';
	clientId: string;
	clientSecret: string;
	scope: string;
	authorize: string; // browser goes here (public address)
	token: string; // the server calls this (internal address if set)
	logout: (back: string) => string;
};

export function sso(): Sso | null {
	if (env.OIDC_ISSUER && env.OIDC_CLIENT_ID && env.OIDC_CLIENT_SECRET) {
		const pub = env.OIDC_ISSUER.replace(/\/$/, '');
		// Inside Docker the server may reach Keycloak at another address than the browser does.
		const internal = (env.OIDC_INTERNAL_ISSUER || pub).replace(/\/$/, '');
		const clientId = env.OIDC_CLIENT_ID;
		return {
			provider: 'keycloak',
			clientId,
			clientSecret: env.OIDC_CLIENT_SECRET,
			scope: `openid profile email ${env.OIDC_SCOPE ?? ''}`.trim(),
			authorize: `${pub}/protocol/openid-connect/auth`,
			token: `${internal}/protocol/openid-connect/token`,
			logout: (back) =>
				`${pub}/protocol/openid-connect/logout?client_id=${encodeURIComponent(clientId)}&post_logout_redirect_uri=${encodeURIComponent(back)}`
		};
	}
	if (env.ENTRA_TENANT_ID && env.ENTRA_CLIENT_ID && env.ENTRA_CLIENT_SECRET) {
		const base = `https://login.microsoftonline.com/${env.ENTRA_TENANT_ID}/oauth2/v2.0`;
		return {
			provider: 'entra',
			clientId: env.ENTRA_CLIENT_ID,
			clientSecret: env.ENTRA_CLIENT_SECRET,
			scope: `openid profile email offline_access ${env.ENTRA_API_SCOPE ?? ''}`.trim(),
			authorize: `${base}/authorize`,
			token: `${base}/token`,
			logout: (back) => `${base}/logout?post_logout_redirect_uri=${encodeURIComponent(back)}`
		};
	}
	return null;
}

export function ssoEnabled(): boolean {
	return sso() !== null;
}

/** The sign-in button's text, e.g. "Sign in with City SSO". */
export function ssoLabel(): string {
	return env.SSO_LABEL || 'Sign in with City SSO';
}

function b64url(buf: Buffer): string {
	return buf.toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export function startSso(origin: string): { url: string; cookie: string } {
	const cfg = sso()!;
	const state = b64url(randomBytes(16));
	const verifier = b64url(randomBytes(32));
	const challenge = b64url(createHash('sha256').update(verifier).digest());
	const params = new URLSearchParams({
		client_id: cfg.clientId,
		response_type: 'code',
		redirect_uri: `${origin}/auth/callback`,
		response_mode: 'query',
		scope: cfg.scope,
		state,
		code_challenge: challenge,
		code_challenge_method: 'S256'
	});
	return { url: `${cfg.authorize}?${params}`, cookie: JSON.stringify({ state, verifier }) };
}

export async function finishSso(
	origin: string,
	code: string,
	verifier: string
): Promise<{ accessToken: string; name: string; id: string }> {
	const cfg = sso()!;
	const body = new URLSearchParams({
		client_id: cfg.clientId,
		client_secret: cfg.clientSecret,
		grant_type: 'authorization_code',
		code,
		redirect_uri: `${origin}/auth/callback`,
		code_verifier: verifier
	});
	const res = await fetch(cfg.token, {
		method: 'POST',
		headers: { 'content-type': 'application/x-www-form-urlencoded' },
		body
	});
	if (!res.ok) throw new Error(`Sign-in failed (${res.status})`);
	const tok = (await res.json()) as { access_token: string; id_token: string };
	// Display name only. Who the person is and what they may do comes from the gateway (whoami).
	const claims = JSON.parse(Buffer.from(tok.id_token.split('.')[1], 'base64url').toString());
	return {
		accessToken: tok.access_token,
		name: claims.name ?? claims.preferred_username ?? 'User',
		id: claims.preferred_username ?? claims.oid
	};
}

export function initials(name: string): string {
	return name
		.split(/[\s.@_-]+/)
		.filter((p) => /^\p{L}/u.test(p)) // skip "(sample)" and other non-words
		.slice(0, 2)
		.map((p) => p[0]!.toUpperCase())
		.join('') || '?';
}
