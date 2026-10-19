// Sign-in. Production: City SSO (Microsoft Entra ID, OpenID Connect, code flow
// with PKCE). The access token goes to the gateway, which checks it and the
// user's groups on every call. Dev: pick a sample user (only when DEV_LOGIN=true).
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

export function ssoEnabled(): boolean {
	return Boolean(env.ENTRA_TENANT_ID && env.ENTRA_CLIENT_ID && env.ENTRA_CLIENT_SECRET);
}

function authority(): string {
	return `https://login.microsoftonline.com/${env.ENTRA_TENANT_ID}/v2.0`;
}

function b64url(buf: Buffer): string {
	return buf.toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export function startSso(origin: string): { url: string; cookie: string } {
	const state = b64url(randomBytes(16));
	const verifier = b64url(randomBytes(32));
	const challenge = b64url(createHash('sha256').update(verifier).digest());
	const params = new URLSearchParams({
		client_id: env.ENTRA_CLIENT_ID!,
		response_type: 'code',
		redirect_uri: `${origin}/auth/callback`,
		response_mode: 'query',
		scope: `openid profile email offline_access ${env.ENTRA_API_SCOPE ?? ''}`.trim(),
		state,
		code_challenge: challenge,
		code_challenge_method: 'S256'
	});
	return {
		url: `${authority().replace('/v2.0', '')}/oauth2/v2.0/authorize?${params}`,
		cookie: JSON.stringify({ state, verifier })
	};
}

export async function finishSso(
	origin: string,
	code: string,
	verifier: string
): Promise<{ accessToken: string; name: string; id: string }> {
	const body = new URLSearchParams({
		client_id: env.ENTRA_CLIENT_ID!,
		client_secret: env.ENTRA_CLIENT_SECRET!,
		grant_type: 'authorization_code',
		code,
		redirect_uri: `${origin}/auth/callback`,
		code_verifier: verifier
	});
	const res = await fetch(`${authority().replace('/v2.0', '')}/oauth2/v2.0/token`, {
		method: 'POST',
		headers: { 'content-type': 'application/x-www-form-urlencoded' },
		body
	});
	if (!res.ok) throw new Error(`Sign-in failed (${res.status})`);
	const tok = (await res.json()) as { access_token: string; id_token: string };
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
