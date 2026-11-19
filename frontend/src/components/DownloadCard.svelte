<script lang="ts">
	import Icons from './Icons.svelte';
	import { buildZipUrl } from '../lib/api';
	import {
		isIndeterminateStatus,
		normalizeStatus,
		type DownloadDTO,
		type NormalizedStatus,
	} from '../lib/types';

	interface Props {
		download: DownloadDTO;
		cancelling?: boolean;
		onViewFiles: (download: DownloadDTO) => void;
		onCancel: (download: DownloadDTO) => void;
		onRequestDelete: (download: DownloadDTO) => void;
	}

	let {
		download,
		cancelling = false,
		onViewFiles,
		onCancel,
		onRequestDelete,
	}: Props = $props();

	const status = $derived<NormalizedStatus>(normalizeStatus(download.status));
	const rawProgress = $derived(
		Number.isFinite(download.progress) ? Math.round(download.progress) : 0
	);
	const clampedProgress = $derived(Math.min(100, Math.max(0, rawProgress)));
	const indeterminate = $derived(isIndeterminateStatus(download.status, clampedProgress));
	const displayMessage = $derived((download.message || download.error || '').trim());

	const fileCountText = $derived.by(() => {
		const downloaded = download.files_downloaded ?? 0;
		const total = download.total_files ?? 0;
		if (total > 0) return `${downloaded}/${total} files`;
		if (downloaded > 0) return `${downloaded} ${downloaded === 1 ? 'file' : 'files'}`;
		return '';
	});

	const statusLabel = $derived.by(() => {
		switch (status) {
			case 'queued':
				return 'Queued';
			case 'downloading':
				return 'In Progress';
			case 'completed':
				return 'Completed';
			case 'failed':
				return 'Failed';
			case 'cancelled':
				return 'Cancelled';
		}
	});

	const progressPercentLabel = $derived.by(() => {
		if (status === 'queued') return 'Queued';
		if (indeterminate) return 'Starting…';
		return `${clampedProgress}%`;
	});
</script>

<article class="card card-interactive" data-status={status}>
	<div class="card-body">
		<div class="download-card-top">
			<h3 class="download-url" title={download.url}>
				<Icons name="link" size={16} />
				<span class="download-url-text">{download.url}</span>
			</h3>

			<span class={`badge badge-${status}`}>
				{#if status === 'downloading'}
					<span class="pulse-dot" aria-hidden="true"></span>
				{/if}
				<span>{statusLabel}</span>
			</span>
		</div>

		<div class="download-meta-row">
			<span class="download-percent">{progressPercentLabel}</span>
			{#if fileCountText}
				<span class="download-files-count">{fileCountText}</span>
			{/if}
		</div>

		<div class="progress-shell">
			<progress
				class="brutal-progress"
				max="100"
				value={indeterminate ? undefined : clampedProgress}
				data-status={status}
				aria-label={`Download progress for ${download.url}`}
			></progress>
		</div>

		{#if displayMessage}
			<div class="download-message">
				<Icons name="terminal" size={15} />
				<span>{displayMessage}</span>
			</div>
		{/if}

		<div class="download-actions">
			{#if status === 'queued' || status === 'downloading'}
				<button
					type="button"
					class="btn btn-sm btn-outline-danger"
					disabled={cancelling}
					onclick={() => onCancel(download)}
					aria-label={`Cancel download for ${download.url}`}
				>
					{#if cancelling}
						<span class="spinner" aria-hidden="true"></span>
						<span>Cancelling…</span>
					{:else}
						<Icons name="x-circle" size={15} />
						<span>Cancel</span>
					{/if}
				</button>
			{:else if status === 'completed'}
				<button
					type="button"
					class="btn btn-sm btn-primary"
					onclick={() => onViewFiles(download)}
					aria-label={`View files for ${download.url}`}
				>
					<Icons name="folder" size={15} />
					<span>Files</span>
				</button>

				<a
					href={buildZipUrl(download.id)}
					class="btn btn-sm"
					aria-label={`Download ZIP archive for ${download.url}`}
				>
					<Icons name="zip" size={15} />
					<span>ZIP</span>
				</a>

				<button
					type="button"
					class="btn btn-sm btn-outline-danger btn-icon"
					onclick={() => onRequestDelete(download)}
					aria-label={`Delete download for ${download.url}`}
				>
					<Icons name="trash" size={15} />
				</button>
			{:else}
				<button
					type="button"
					class="btn btn-sm btn-outline-danger"
					onclick={() => onRequestDelete(download)}
					aria-label={`Delete download for ${download.url}`}
				>
					<Icons name="trash" size={15} />
					<span>Delete</span>
				</button>
			{/if}
		</div>
	</div>
</article>
