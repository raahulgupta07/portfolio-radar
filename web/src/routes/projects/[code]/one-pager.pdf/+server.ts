import type { RequestHandler } from './$types';
import { pdfResponse } from '$lib/server/pdf';

export const GET: RequestHandler = ({ locals, params }) => pdfResponse(locals.token!, 'get_project_pdf', { code: params.code });
