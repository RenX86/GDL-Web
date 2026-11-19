<script lang="ts">
	import Icons from './Icons.svelte';
	import { ApiError, fetchFormats, startDownload } from '../lib/api';
	import { downloadsStore } from '../lib/downloads.svelte';
	import { toastStore } from '../lib/toasts.svelte';
	import type { DownloadTool, FormatsResponse, SessionLimits } from '../lib/types';

	interface Props {
		limits: SessionLimits | null;
		onFormatsLoaded: (payload: {
			url: string;
			cookies: string | null;
			formats: FormatsResponse;
		}) => void;
		onRequestClearSession: () => void;
	}

	let { limits, onFormatsLoaded, onRequestClearSession }: Props = $props();

	let tool = $state<DownloadTool>('gallery-dl');
	let url = $state('');
	let cookieInputEl = $state<HTMLInputElement | null>(null);
	let selectedCookieFile = $state<File | null>(null);
	let submitting = $state(false);
	let fetchingFormats = $state(false);

	async function readSelectedCookies(): Promise<string | null> {
		if (!selectedCookieFile) return null;
		return await selectedCookieFile.text();
	}

	function handleCookieChange(event: Event) {
		const target = event.currentTarget as HTMLInputElement;
		selectedCookieFile = target.files && target.files.length > 0 ? target.files[0] : null;
	}

	export function resetFormInputs() {
		url = '';
		selectedCookieFile = null;
		if (cookieInputEl) {
			cookieInputEl.value = '';
		}
	}

	async function handleSubmit(event: SubmitEvent) {
		event.preventDefault();
		const trimmed = url.trim();
		if (!trimmed) {
			toastStore.push('Input Required', 'Please enter a valid media URL.', 'warning');
			return;
		}

		submitting = true;
		try {
			const cookiesContent = await readSelectedCookies();
			const created = await startDownload({
				url: trimmed,
				tool,
				cookies: cookiesContent,
			});
			downloadsStore.upsert(created);
			resetFormInputs();
			toastStore.push('Download Queued', 'Your download has been started.', 'success');
			if (downloadsStore.filter === 'completed' || downloadsStore.filter === 'failed') {
				downloadsStore.setFilter('all');
			}
		} catch (error) {
			const msg =
				error instanceof ApiError
					? error.message
					: error instanceof Error
						? error.message
						: 'Could not start download.';
			toastStore.push('Download Failed', msg, 'error');
		} finally {
			submitting = false;
		}
	}

	async function handleFetchFormats() {
		const trimmed = url.trim();
		if (!trimmed) {
			toastStore.push('Input Required', 'Enter a video URL before fetching formats.', 'warning');
			return;
		}

		fetchingFormats = true;
		try {
			const cookiesContent = await readSelectedCookies();
			const formats = await fetchFormats({
				url: trimmed,
				cookies: cookiesContent,
			});
			onFormatsLoaded({
				url: trimmed,
				cookies: cookiesContent,
				formats,
			});
		} catch (error) {
			const msg =
				error instanceof ApiError
					? error.message
					: error instanceof Error
						? error.message
						: 'Could not fetch available formats.';
			toastStore.push('Format Lookup Failed', msg, 'error');
		} finally {
			fetchingFormats = false;
		}
	}

	const ttlMinutes = $derived(
		limits && limits.download_ttl_seconds > 0
			? Math.round(limits.download_ttl_seconds / 60)
			: null
	);
</script>

<section class="card" aria-labelledby="new-download-heading">
	<div class="card-header">
		<h2 id="new-download-heading" class="card-title">
			<Icons name="download" size={18} />
			<span>New Download</span>
		</h2>
	</div>

	<div class="card-body">
		<form class="form-stack" onsubmit={handleSubmit}>
			<fieldset class="form-fieldset">
				<legend>Download Type</legend>
				<div class="segmented-group">
					<div class="segmented-option">
						<input
							type="radio"
							id="toolGallery"
							name="downloadTool"
							value="gallery-dl"
							bind:group={tool}
						/>
						<label for="toolGallery">
							<Icons name="images" size={16} />
							<span>Gallery</span>
						</label>
					</div>

					<div class="segmented-option">
						<input
							type="radio"
							id="toolVideo"
							name="downloadTool"
							value="yt-dlp"
							bind:group={tool}
						/>
						<label for="toolVideo">
							<Icons name="video" size={16} />
							<span>Video</span>
						</label>
					</div>
				</div>
			</fieldset>

			<div class="form-group">
				<label for="mediaUrl" class="form-label">Media URL</label>
				<input
					id="mediaUrl"
					name="mediaUrl"
					type="url"
					class="input-control"
					bind:value={url}
					placeholder="https://example.com/gallery-or-video"
					required
					autocorrect="off"
					autocapitalize="none"
					spellcheck="false"
					aria-describedby="mediaUrlHelp"
				/>
				<p id="mediaUrlHelp" class="form-help">
					Paste an HTTP or HTTPS URL for a supported gallery or video.
				</p>
			</div>

			<div class="form-group">
				<label for="cookieFile" class="form-label">Cookies (Optional)</label>
				<input
					bind:this={cookieInputEl}
					id="cookieFile"
					name="cookieFile"
					type="file"
					class="input-control"
					accept=".txt"
					onchange={handleCookieChange}
					aria-describedby="cookieFileHelp"
				/>
				<p id="cookieFileHelp" class="form-help">
					Upload a Netscape format cookies.txt file if authentication is required.
				</p>
			</div>

			<div class="form-stack">
				<div class="button-row">
					{#if tool === 'yt-dlp'}
						<button
							type="button"
							class="btn"
							onclick={handleFetchFormats}
							disabled={fetchingFormats || submitting}
						>
							{#if fetchingFormats}
								<span class="spinner" aria-hidden="true"></span>
								<span>Fetching…</span>
							{:else}
								<Icons name="sliders" size={16} />
								<span>Formats</span>
							{/if}
						</button>
					{/if}

					<button
						type="submit"
						class="btn btn-primary btn-grow"
						disabled={submitting || fetchingFormats}
					>
						{#if submitting}
							<span class="spinner" aria-hidden="true"></span>
							<span>Starting…</span>
						{:else}
							<Icons name="download" size={16} />
							<span>Start Download</span>
						{/if}
					</button>
				</div>

				<button
					type="button"
					class="btn btn-outline-danger btn-block"
					onclick={onRequestClearSession}
				>
					<Icons name="trash" size={16} />
					<span>Clear Session</span>
				</button>
			</div>

			{#if limits}
				<div class="limits-note" aria-label="Session limits">
					<span>Max concurrent: <strong>{limits.max_concurrent_per_session}</strong></span>
					<span>Max file: <strong>{limits.max_filesize_mb} MB</strong></span>
					{#if ttlMinutes !== null}
						<span>Retention: <strong>{ttlMinutes} min</strong></span>
					{/if}
				</div>
			{/if}
		</form>
	</div>
</section>
