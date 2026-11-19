<script lang="ts">
	import Icons from './Icons.svelte';
	import { ApiError, buildFileUrl, buildZipUrl, fetchDownloadFiles } from '../lib/api';
	import { attachLightDismiss } from '../lib/dialog';
	import {
		formatBytes,
		type DownloadDTO,
		type DownloadFileDTO,
		type MediaPreviewTarget,
	} from '../lib/types';

	interface Props {
		download: DownloadDTO | null;
		onClose: () => void;
		onPreviewMedia: (target: MediaPreviewTarget) => void;
	}

	let { download, onClose, onPreviewMedia }: Props = $props();

	let dialogEl = $state<HTMLDialogElement | null>(null);
	let files = $state<DownloadFileDTO[]>([]);
	let loading = $state(false);
	let errorMessage = $state<string | null>(null);

	const supportsNativeVideoLazy =
		typeof HTMLMediaElement !== 'undefined' &&
		Object.hasOwn(HTMLMediaElement.prototype, 'loading');

	function lazyVideo(node: HTMLVideoElement, src: string) {
		if (supportsNativeVideoLazy) {
			node.src = src;
			return {};
		}

		if (typeof IntersectionObserver === 'undefined') {
			node.src = src;
			return {};
		}

		let loaded = false;
		const observer = new IntersectionObserver(
			(entries) => {
				for (const entry of entries) {
					if (entry.isIntersecting && !loaded) {
						loaded = true;
						node.src = src;
						observer.disconnect();
						break;
					}
				}
			},
			{ rootMargin: '200px' }
		);

		observer.observe(node);

		return {
			destroy() {
				observer.disconnect();
				node.pause();
				node.removeAttribute('src');
			},
		};
	}

	$effect(() => {
		const el = dialogEl;
		if (!el) return;
		const detach = attachLightDismiss(el);
		return () => detach();
	});

	$effect(() => {
		const el = dialogEl;
		const current = download;
		if (!el) return;

		if (current) {
			if (!el.open && typeof el.showModal === 'function') {
				el.showModal();
			}
			let cancelled = false;
			loading = true;
			errorMessage = null;
			files = [];

			fetchDownloadFiles(current.id)
				.then((response) => {
					if (!cancelled) {
						files = response.files ?? [];
					}
				})
				.catch((error) => {
					if (!cancelled) {
						errorMessage =
							error instanceof ApiError
								? error.message
								: 'Could not load files for this download.';
					}
				})
				.finally(() => {
					if (!cancelled) {
						loading = false;
					}
				});

			return () => {
				cancelled = true;
			};
		} else if (el.open) {
			el.close();
		}
	});

	function handleClose() {
		if (dialogEl) {
			dialogEl.returnValue = '';
		}
		onClose();
	}

	function openPreview(file: DownloadFileDTO) {
		if (!download || file.preview_kind === 'none') return;
		onPreviewMedia({
			kind: file.preview_kind,
			url: buildFileUrl(download.id, file.rel_path, true),
			downloadUrl: buildFileUrl(download.id, file.rel_path, false),
			name: file.name,
			mimeType: file.mime_type,
		});
	}

	const dialogExtraAttrs = { closedby: 'any' } as Record<string, string>;
	const videoLazyAttrs = { loading: 'lazy' } as Record<string, string>;
</script>

<dialog
	bind:this={dialogEl}
	class="brutal-dialog dialog-lg"
	aria-labelledby="files-dialog-title"
	onclose={handleClose}
	{...dialogExtraAttrs}
>
	<div class="dialog-header">
		<h2 id="files-dialog-title" class="dialog-title">
			<Icons name="folder" size={18} />
			<span>Downloaded Files</span>
		</h2>
		<button
			type="button"
			class="btn btn-sm btn-icon"
			onclick={() => dialogEl?.close()}
			aria-label="Close downloaded files dialog"
		>
			<Icons name="close" size={16} />
		</button>
	</div>

	<div class="dialog-body dialog-body-flush">
		{#if loading}
			<div class="empty-state" style="border: 0;" role="status">
				<span class="spinner" aria-hidden="true"></span>
				<p>Loading files…</p>
			</div>
		{:else if errorMessage}
			<div class="dialog-body">
				<p>{errorMessage}</p>
			</div>
		{:else if files.length === 0}
			<div class="empty-state" style="border: 0;">
				<Icons name="inbox" size={32} />
				<p>No files found for this download.</p>
			</div>
		{:else if download}
			<div class="files-toolbar">
				<strong>{files.length} {files.length === 1 ? 'file' : 'files'}</strong>
				<a href={buildZipUrl(download.id)} class="btn btn-sm btn-primary">
					<Icons name="zip" size={15} />
					<span>Download All (ZIP)</span>
				</a>
			</div>

			<div class="file-grid">
				{#each files as file (file.rel_path)}
					{@const downloadUrl = buildFileUrl(download.id, file.rel_path, false)}
					{@const previewUrl = buildFileUrl(download.id, file.rel_path, true)}

					<div class="file-card">
						{#if file.preview_kind === 'image'}
							<button
								type="button"
								class="file-preview-trigger"
								onclick={() => openPreview(file)}
								aria-label={`Preview image ${file.name}`}
							>
								<img
									src={previewUrl}
									alt={file.name}
									class="file-thumbnail"
									loading="lazy"
									decoding="async"
									width="240"
									height="240"
								/>
							</button>
						{:else if file.preview_kind === 'video'}
							<button
								type="button"
								class="file-preview-trigger"
								onclick={() => openPreview(file)}
								aria-label={`Preview video ${file.name}`}
							>
								<video
									use:lazyVideo={`${previewUrl}#t=0.1`}
									class="file-thumbnail"
									preload="metadata"
									width="240"
									height="240"
									muted
									playsinline
									{...videoLazyAttrs}
								></video>
								<span class="video-play-badge" aria-hidden="true">
									<Icons name="play" size={36} />
								</span>
							</button>
						{:else if file.preview_kind === 'audio'}
							<button
								type="button"
								class="file-preview-trigger"
								onclick={() => openPreview(file)}
								aria-label={`Play audio ${file.name}`}
							>
								<Icons name="music" size={40} />
							</button>
						{:else}
							<div class="file-preview-static" aria-hidden="true">
								<Icons name="file" size={40} />
							</div>
						{/if}

						<div class="file-card-body">
							<span class="file-name" title={file.name}>{file.name}</span>
							<div class="file-card-meta">
								<span>{formatBytes(file.size_bytes)}</span>
								<a
									href={downloadUrl}
									download={file.name}
									class="btn btn-sm btn-icon"
									aria-label={`Download ${file.name}`}
								>
									<Icons name="download" size={14} />
								</a>
							</div>
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</div>

	<div class="dialog-footer">
		<button type="button" class="btn btn-sm" onclick={() => dialogEl?.close()}>Close</button>
	</div>
</dialog>
