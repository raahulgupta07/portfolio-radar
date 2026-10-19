import { error, fail } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import { callTool, clearCache, McpToolError } from '$lib/server/mcp';

type Any = Record<string, any>;

export const load: PageServerLoad = async ({ locals, url }) => {
	try {
		const conv = await callTool<Any>(locals.token!, 'radar', 'get_conversation', {}, { cache: false });
		return { conv, about: url.searchParams.get('about') };
	} catch (e) {
		if (e instanceof McpToolError) error(403, e.message);
		error(503, 'Radar is not reachable right now. Try again in a minute.');
	}
};

async function act(token: string, tool: string, args: Any) {
	try {
		await callTool(token, 'radar', tool, args, { cache: false });
		clearCache();
		return { ok: true };
	} catch (e) {
		return fail(400, { ok: false, message: e instanceof McpToolError ? e.message : 'Radar is not reachable.' });
	}
}

export const actions: Actions = {
	ask: async ({ locals, request }) => {
		const text = String((await request.formData()).get('text') ?? '').trim();
		if (!text) return fail(400, { ok: false, message: 'Type a question first.' });
		return act(locals.token!, 'ask_radar', { text });
	},
	answer: async ({ locals, request }) => {
		const f = await request.formData();
		return act(locals.token!, 'answer_ask', { message_id: Number(f.get('message_id')), answer: String(f.get('answer')) });
	},
	decide: async ({ locals, request }) => {
		const f = await request.formData();
		const body = f.get('body');
		return act(locals.token!, 'decide_approval', {
			approval_id: Number(f.get('approval_id')),
			decision: String(f.get('decision')),
			...(body != null && String(body).trim() ? { body: String(body) } : {})
		});
	},
	remember: async ({ locals, request }) => {
		const text = String((await request.formData()).get('text') ?? '').trim();
		return act(locals.token!, 'remember', { text });
	},
	forget: async ({ locals, request }) => act(locals.token!, 'forget', { id: Number((await request.formData()).get('id')) })
};
