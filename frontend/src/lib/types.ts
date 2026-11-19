export type DownloadTool = 'gallery-dl' | 'yt-dlp';

export type NormalizedStatus = 'queued' | 'downloading' | 'completed' | 'failed' | 'cancelled';

export type DownloadFilter = 'all' | 'active' | 'completed' | 'failed';

export type PreviewKind = 'image' | 'video' | 'audio' | 'none';

export interface SessionLimits {
	max_concurrent_per_session: number;
	max_filesize_mb: number;
	max_downloads_per_job: number;
	download_ttl_seconds: number;
}

export interface SessionInfo {
	session_id: string;
	csrf_token: string;
	limits: SessionLimits;
}

export interface ClearSessionResponse {
	cleared: boolean;
	session_id: string;
	csrf_token: string;
}

export interface DownloadDTO {
	id: string;
	url: string;
	tool?: DownloadTool;
	status: string;
	progress: number;
	start_time?: string | null;
	end_time?: string | null;
	created_at?: string | null;
	message?: string | null;
	error?: string | null;
	files_downloaded?: number;
	total_files?: number;
	isp_block?: boolean;
	format_id?: string | null;
}

export interface DownloadFileDTO {
	name: string;
	rel_path: string;
	size_bytes: number;
	mime_type: string;
	preview_kind: PreviewKind;
}

export interface DownloadFilesResponse {
	download_id: string;
	files: DownloadFileDTO[];
	total_files: number;
}

export interface FormatOption {
	format_id: string;
	label?: string;
	ext?: string;
	resolution?: string | null;
	filesize?: number | null;
	fps?: number | null;
	vcodec?: string | null;
	acodec?: string | null;
	note?: string | null;
}

export interface FormatsResponse {
	title: string;
	thumbnail?: string | null;
	combined: FormatOption[];
	video: FormatOption[];
	audio: FormatOption[];
}

export interface EnginesStatusResponse {
	gallery_dl: string | null;
	yt_dlp: string | null;
	ffmpeg: string | null;
	runtime_updates_enabled: boolean;
}

export type SSEEvent =
	| { type: 'initial'; data: DownloadDTO[] }
	| { type: 'update'; data: DownloadDTO }
	| { type: 'delete'; data: { id: string } }
	| { type: 'clear'; data: Record<string, never> };

export type ToastKind = 'info' | 'success' | 'warning' | 'error';

export interface ToastItem {
	id: string;
	title: string;
	message: string;
	kind: ToastKind;
	durationMs: number;
}

export interface MediaPreviewTarget {
	kind: Exclude<PreviewKind, 'none'>;
	url: string;
	downloadUrl: string;
	name: string;
	mimeType: string;
}

export function normalizeStatus(status: string | undefined | null): NormalizedStatus {
	const value = (status ?? 'pending').toLowerCase().trim();
	if (value === 'completed' || value === 'finished') return 'completed';
	if (value === 'failed' || value === 'error') return 'failed';
	if (value === 'cancelled' || value === 'canceled') return 'cancelled';
	if (
		value === 'starting' ||
		value === 'downloading' ||
		value === 'processing' ||
		value === 'in_progress' ||
		value === 'retrying'
	) {
		return 'downloading';
	}
	return 'queued';
}

export function isIndeterminateStatus(status: string | undefined | null, progress: number): boolean {
	const raw = (status ?? 'pending').toLowerCase().trim();
	if (raw === 'pending' || raw === 'queued' || raw === 'starting') return true;
	const normalized = normalizeStatus(status);
	return normalized === 'downloading' && progress <= 0;
}

export function formatBytes(bytes: number | undefined | null): string {
	if (bytes === undefined || bytes === null || !Number.isFinite(bytes) || bytes < 0) return '';
	if (bytes === 0) return '0 B';
	const units = ['B', 'KB', 'MB', 'GB', 'TB'];
	const idx = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
	const val = bytes / 1024 ** idx;
	return `${val >= 10 || idx === 0 ? val.toFixed(0) : val.toFixed(1)} ${units[idx]}`;
}

export function formatOptionLabel(option: FormatOption): string {
	if (option.label && option.label.trim().length > 0) return option.label;
	const parts: string[] = [];
	if (option.resolution) parts.push(option.resolution);
	if (option.ext) parts.push(option.ext.toUpperCase());
	if (option.fps) parts.push(`${option.fps}fps`);
	if (option.filesize) parts.push(formatBytes(option.filesize));
	if (option.note) parts.push(option.note);
	if (parts.length === 0) return option.format_id;
	return `${parts.join(' · ')} (${option.format_id})`;
}
