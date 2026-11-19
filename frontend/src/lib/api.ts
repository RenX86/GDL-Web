import type {
	ClearSessionResponse,
	DownloadDTO,
	DownloadFilesResponse,
	DownloadTool,
	EnginesStatusResponse,
	FormatsResponse,
	SessionInfo,
} from './types';

export class ApiError extends Error {
	status: number;

	constructor(message: string, status: number) {
		super(message);
		this.name = 'ApiError';
		this.status = status;
	}
}

let csrfToken: string | null = null;
let sessionPromise: Promise<SessionInfo> | null = null;

export function getCsrfToken(): string | null {
	return csrfToken;
}

export function setCsrfToken(token: string | null): void {
	csrfToken = token;
}

function createTimeoutSignal(timeoutMs: number): AbortSignal | undefined {
	if (typeof AbortSignal !== 'undefined' && typeof AbortSignal.timeout === 'function') {
		return AbortSignal.timeout(timeoutMs);
	}
	return undefined;
}

async function parseErrorMessage(response: Response): Promise<string> {
	const fallback = response.statusText || `Request failed (${response.status})`;
	const contentType = response.headers.get('content-type') ?? '';
	if (!contentType.includes('application/json')) {
		return fallback;
	}
	try {
		const payload: unknown = await response.json();
		if (payload && typeof payload === 'object') {
			const record = payload as Record<string, unknown>;
			if (typeof record.detail === 'string' && record.detail.trim()) return record.detail;
			if (typeof record.message === 'string' && record.message.trim()) return record.message;
			if (typeof record.error === 'string' && record.error.trim()) return record.error;
			if (Array.isArray(record.detail) && record.detail.length > 0) {
				const first = record.detail[0] as Record<string, unknown> | undefined;
				if (first && typeof first.msg === 'string') return first.msg;
			}
		}
	} catch {
		// Fall through to status text
	}
	return fallback;
}

async function ensureCsrfToken(): Promise<string> {
	if (csrfToken) return csrfToken;
	const session = await fetchSession();
	return session.csrf_token;
}

async function apiRequest<T>(
	path: string,
	options: {
		method?: 'GET' | 'POST' | 'DELETE';
		body?: unknown;
		timeoutMs?: number;
		requiresCsrf?: boolean;
	} = {}
): Promise<T> {
	const { method = 'GET', body, timeoutMs = 30_000, requiresCsrf = method !== 'GET' } = options;

	const headers: Record<string, string> = {
		Accept: 'application/json',
	};

	if (body !== undefined) {
		headers['Content-Type'] = 'application/json';
	}

	if (requiresCsrf) {
		headers['X-CSRF-Token'] = await ensureCsrfToken();
	}

	const response = await fetch(path, {
		method,
		headers,
		body: body !== undefined ? JSON.stringify(body) : undefined,
		credentials: 'same-origin',
		signal: createTimeoutSignal(timeoutMs),
	});

	if (!response.ok) {
		const message = await parseErrorMessage(response);
		throw new ApiError(message, response.status);
	}

	return (await response.json()) as T;
}

export async function fetchSession(): Promise<SessionInfo> {
	if (!sessionPromise) {
		sessionPromise = apiRequest<SessionInfo>('/api/session', {
			method: 'GET',
			requiresCsrf: false,
		})
			.then((data) => {
				csrfToken = data.csrf_token;
				return data;
			})
			.finally(() => {
				sessionPromise = null;
			});
	}
	return sessionPromise;
}

export async function fetchDownloads(): Promise<DownloadDTO[]> {
	const data = await apiRequest<{ downloads: DownloadDTO[] }>('/api/downloads', {
		method: 'GET',
	});
	return Array.isArray(data.downloads) ? data.downloads : [];
}

export async function startDownload(params: {
	url: string;
	tool: DownloadTool;
	cookies?: string | null;
	format_id?: string | null;
}): Promise<DownloadDTO> {
	return apiRequest<DownloadDTO>('/api/downloads', {
		method: 'POST',
		body: {
			url: params.url,
			tool: params.tool,
			cookies: params.cookies ?? null,
			format_id: params.format_id ?? null,
		},
	});
}

export async function cancelDownload(downloadId: string): Promise<DownloadDTO> {
	return apiRequest<DownloadDTO>(`/api/downloads/${encodeURIComponent(downloadId)}/cancel`, {
		method: 'POST',
	});
}

export async function deleteDownload(downloadId: string): Promise<{ deleted: boolean; id: string }> {
	return apiRequest<{ deleted: boolean; id: string }>(
		`/api/downloads/${encodeURIComponent(downloadId)}`,
		{
			method: 'DELETE',
		}
	);
}

export async function clearSession(): Promise<ClearSessionResponse> {
	const result = await apiRequest<ClearSessionResponse>('/api/session/clear', {
		method: 'POST',
	});
	if (result.csrf_token) {
		csrfToken = result.csrf_token;
	}
	return result;
}

export async function fetchFormats(params: {
	url: string;
	cookies?: string | null;
}): Promise<FormatsResponse> {
	return apiRequest<FormatsResponse>('/api/formats', {
		method: 'POST',
		body: {
			url: params.url,
			cookies: params.cookies ?? null,
		},
		timeoutMs: 60_000,
	});
}

export async function fetchDownloadFiles(downloadId: string): Promise<DownloadFilesResponse> {
	return apiRequest<DownloadFilesResponse>(
		`/api/downloads/${encodeURIComponent(downloadId)}/files`,
		{
			method: 'GET',
		}
	);
}

export async function fetchEnginesStatus(): Promise<EnginesStatusResponse> {
	return apiRequest<EnginesStatusResponse>('/api/system/engines', {
		method: 'GET',
	});
}

export function buildFileUrl(downloadId: string, relPath: string, preview = false): string {
	const encodedPath = relPath
		.replace(/\\/g, '/')
		.split('/')
		.filter((segment) => segment.length > 0)
		.map((segment) => encodeURIComponent(segment))
		.join('/');
	const base = `/api/downloads/${encodeURIComponent(downloadId)}/files/${encodedPath}`;
	return preview ? `${base}?preview=true` : base;
}

export function buildZipUrl(downloadId: string): string {
	return `/api/downloads/${encodeURIComponent(downloadId)}/zip`;
}
