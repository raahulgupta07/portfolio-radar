// PDF one-pagers (FR-16) are drawn by the gateway (portfolio.get_*_pdf) and sent here as base64.
import { error } from '@sveltejs/kit';
import { callTool, McpToolError } from '$lib/server/mcp';

type Pdf = { filename: string; content_base64: string };

export async function pdfResponse(token: string, tool: string, args: Record<string, unknown> = {}): Promise<Response> {
	let pdf: Pdf;
	try {
		// Not cached: each PDF says when it was made.
		pdf = await callTool<Pdf>(token, 'portfolio', tool, args, { cache: false });
	} catch (e) {
		if (e instanceof McpToolError) error(e.message.startsWith('No project') ? 404 : 403, e.message);
		error(503, 'The portfolio service is not reachable right now. Try again in a minute.');
	}
	const name = pdf.filename.replace(/[^A-Za-z0-9._-]/g, '_');
	return new Response(Buffer.from(pdf.content_base64, 'base64'), {
		headers: {
			'content-type': 'application/pdf',
			'content-disposition': `inline; filename="${name}"`,
			'cache-control': 'private, no-store'
		}
	});
}
