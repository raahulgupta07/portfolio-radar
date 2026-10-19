import type { RequestHandler } from './$types';
import { pdfResponse } from '$lib/server/pdf';

export const GET: RequestHandler = ({ locals }) => pdfResponse(locals.token!, 'get_overview_pdf');
