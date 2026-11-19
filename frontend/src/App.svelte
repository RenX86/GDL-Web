<script lang="ts">
	import { onMount } from 'svelte';
	import Navbar from './components/Navbar.svelte';
	import DownloadForm from './components/DownloadForm.svelte';
	import SystemStatusCard from './components/SystemStatusCard.svelte';
	import ActivityList from './components/ActivityList.svelte';
	import FilesDialog from './components/FilesDialog.svelte';
	import MediaPreviewDialog from './components/MediaPreviewDialog.svelte';
	import FormatSelectDialog from './components/FormatSelectDialog.svelte';
	import ConfirmDialog from './components/ConfirmDialog.svelte';
	import IspBlockDialog from './components/IspBlockDialog.svelte';
	import ToastStack from './components/ToastStack.svelte';
	import {
		ApiError,
		cancelDownload,
		clearSession,
		deleteDownload,
		fetchSession,
		startDownload,
	} from './lib/api';
	import { downloadsStore } from './lib/downloads.svelte';
	import { themeStore } from './lib/theme.svelte';
	import { toastStore } from './lib/toasts.svelte';
	import type {
		DownloadDTO,
		FormatsResponse,
		MediaPreviewTarget,
		SessionLimits,
	} from './lib/types';

	let limits = $state<SessionLimits | null>(null);
	let downloadFormRef = $state<DownloadForm | null>(null);
	let mediaPreviewRef = $state<MediaPreviewDialog | null>(null);

	let filesDownload = $state<DownloadDTO | null>(null);
	let previewMedia = $state<MediaPreviewTarget | null>(null);
	let formatPayload = $state<{
		url: string;
		cookies: string | null;
		formats: FormatsResponse;
	} | null>(null);
	let startingCustomFormat = $state(false);

	let confirmState = $state<
		{ kind: 'delete'; download: DownloadDTO } | { kind: 'clear' } | null
	>(null);
	let confirmBusy = $state(false);

	let cancellingIds = $state<Set<string>>(new Set());
	let disconnectSse: (() => void) | null = null;

	const anyModalOpen = $derived(
		Boolean(
			filesDownload ||
				previewMedia ||
				formatPayload ||
				confirmState ||
				downloadsStore.ispBlockDownloadId
		)
	);

	function reconnectSse() {
		disconnectSse?.();
		disconnectSse = downloadsStore.connect();
	}

	onMount(() => {
		const detachTheme = themeStore.attachListeners();
		let disposed = false;

		fetchSession()
			.then((session) => {
				if (disposed) return;
				limits = session.limits;
				reconnectSse();
			})
			.catch(() => {
				if (disposed) return;
				reconnectSse();
			});

		return () => {
			disposed = true;
			detachTheme();
			disconnectSse?.();
			disconnectSse = null;
		};
	});

	async function handleCancelDownload(download: DownloadDTO) {
		const next = new Set(cancellingIds);
		next.add(download.id);
		cancellingIds = next;

		try {
			const updated = await cancelDownload(download.id);
			downloadsStore.upsert(updated);
			toastStore.push('Download Cancelled', 'The download has been cancelled.', 'info');
		} catch (error) {
			const msg =
				error instanceof ApiError ? error.message : 'Could not cancel this download.';
			toastStore.push('Cancel Failed', msg, 'error');
		} finally {
			const updated = new Set(cancellingIds);
			updated.delete(download.id);
			cancellingIds = updated;
		}
	}

	async function handleConfirmCustomFormat(formatId: string) {
		if (!formatPayload) return;
		startingCustomFormat = true;
		try {
			const created = await startDownload({
				url: formatPayload.url,
				tool: 'yt-dlp',
				cookies: formatPayload.cookies,
				format_id: formatId,
			});
			downloadsStore.upsert(created);
			formatPayload = null;
			downloadFormRef?.resetFormInputs();
			toastStore.push('Download Queued', 'Custom format download started.', 'success');
			if (downloadsStore.filter === 'completed' || downloadsStore.filter === 'failed') {
				downloadsStore.setFilter('all');
			}
		} catch (error) {
			const msg =
				error instanceof ApiError ? error.message : 'Could not start custom download.';
			toastStore.push('Download Failed', msg, 'error');
		} finally {
			startingCustomFormat = false;
		}
	}

	async function handleConfirmDestructive() {
		if (!confirmState) return;
		confirmBusy = true;

		try {
			if (confirmState.kind === 'delete') {
				const targetId = confirmState.download.id;
				if (filesDownload?.id === targetId) {
					filesDownload = null;
					previewMedia = null;
				}
				await deleteDownload(targetId);
				downloadsStore.remove(targetId);
				confirmState = null;
				toastStore.push('Deleted', 'Download removed from your session.', 'success');
			} else {
				mediaPreviewRef?.stopPlayback();
				previewMedia = null;
				filesDownload = null;

				await clearSession();
				downloadsStore.clear();
				confirmState = null;
				reconnectSse();
				toastStore.push(
					'Session Cleared',
					'All downloads and files have been removed.',
					'success'
				);
			}
		} catch (error) {
			const msg =
				error instanceof ApiError ? error.message : 'The operation could not be completed.';
			toastStore.push('Action Failed', msg, 'error');
		} finally {
			confirmBusy = false;
		}
	}
</script>

<Navbar />

<main id="main-content" class="page-container">
	<div class="main-grid">
		<aside class="sidebar-stack" aria-label="Download controls and system info">
			<DownloadForm
				bind:this={downloadFormRef}
				{limits}
				onFormatsLoaded={(payload) => (formatPayload = payload)}
				onRequestClearSession={() => (confirmState = { kind: 'clear' })}
			/>
			<SystemStatusCard />
		</aside>

		<ActivityList
			{cancellingIds}
			onViewFiles={(download) => (filesDownload = download)}
			onCancel={handleCancelDownload}
			onRequestDelete={(download) => (confirmState = { kind: 'delete', download })}
		/>
	</div>
</main>

<FilesDialog
	download={filesDownload}
	onClose={() => (filesDownload = null)}
	onPreviewMedia={(target) => (previewMedia = target)}
/>

<MediaPreviewDialog
	bind:this={mediaPreviewRef}
	media={previewMedia}
	onClose={() => (previewMedia = null)}
/>

<FormatSelectDialog
	formats={formatPayload?.formats ?? null}
	busy={startingCustomFormat}
	onClose={() => (formatPayload = null)}
	onConfirm={handleConfirmCustomFormat}
/>

<ConfirmDialog
	open={confirmState !== null}
	title={confirmState?.kind === 'clear' ? 'Clear Session' : 'Delete Download'}
	message={confirmState?.kind === 'clear'
		? 'Are you sure you want to clear your entire session?'
		: 'Are you sure you want to delete this download?'}
	detail={confirmState?.kind === 'clear'
		? 'This permanently removes all download history and downloaded files from your session.'
		: confirmState?.kind === 'delete'
			? `Files and history for ${confirmState.download.url} will be permanently deleted.`
			: ''}
	confirmLabel={confirmState?.kind === 'clear' ? 'Yes, Clear Everything' : 'Delete Download'}
	busy={confirmBusy}
	onCancel={() => {
		if (!confirmBusy) confirmState = null;
	}}
	onConfirm={handleConfirmDestructive}
/>

<IspBlockDialog
	open={downloadsStore.ispBlockDownloadId !== null}
	onClose={() => downloadsStore.dismissIspBlock()}
/>

<ToastStack suppressed={anyModalOpen} />
