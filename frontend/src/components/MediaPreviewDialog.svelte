<script lang="ts">
	import Icons from './Icons.svelte';
	import { attachLightDismiss } from '../lib/dialog';
	import type { MediaPreviewTarget } from '../lib/types';

	interface Props {
		media: MediaPreviewTarget | null;
		onClose: () => void;
	}

	let { media, onClose }: Props = $props();

	let dialogEl = $state<HTMLDialogElement | null>(null);
	let videoEl = $state<HTMLVideoElement | null>(null);
	let audioEl = $state<HTMLAudioElement | null>(null);

	function prefersReducedMotion(): boolean {
		return (
			typeof window !== 'undefined' &&
			typeof window.matchMedia === 'function' &&
			window.matchMedia('(prefers-reduced-motion: reduce)').matches
		);
	}

	export function stopPlayback() {
		if (videoEl) {
			videoEl.pause();
			videoEl.removeAttribute('src');
			videoEl.load();
		}
		if (audioEl) {
			audioEl.pause();
			audioEl.removeAttribute('src');
			audioEl.load();
		}
	}

	$effect(() => {
		const el = dialogEl;
		if (!el) return;
		const detach = attachLightDismiss(el);
		return () => detach();
	});

	$effect(() => {
		const el = dialogEl;
		if (!el) return;
		if (media) {
			if (!el.open && typeof el.showModal === 'function') {
				el.showModal();
			}
			if (media.kind === 'video' && videoEl && !prefersReducedMotion()) {
				void videoEl.play().catch(() => {
					// Ignore autoplay policy rejections
				});
			}
		} else if (el.open) {
			stopPlayback();
			el.close();
		}
	});

	function handleClose() {
		stopPlayback();
		if (dialogEl) {
			dialogEl.returnValue = '';
		}
		onClose();
	}

	const dialogExtraAttrs = { closedby: 'any' } as Record<string, string>;
</script>

<dialog
	bind:this={dialogEl}
	class="brutal-dialog dialog-xl"
	aria-labelledby="media-preview-title"
	onclose={handleClose}
	{...dialogExtraAttrs}
>
	<div class="dialog-header">
		<h2 id="media-preview-title" class="dialog-title">
			<Icons name={media?.kind === 'video' ? 'video' : media?.kind === 'audio' ? 'music' : 'images'} size={18} />
			<span>{media?.name ?? 'Media Preview'}</span>
		</h2>
		<button
			type="button"
			class="btn btn-sm btn-icon"
			onclick={() => dialogEl?.close()}
			aria-label="Close media preview"
		>
			<Icons name="close" size={16} />
		</button>
	</div>

	<div class="dialog-body dialog-body-flush">
		{#if media}
			<div class="media-preview-stage">
				{#if media.kind === 'image'}
					<img
						src={media.url}
						alt={media.name}
						class="media-preview-img"
						decoding="async"
					/>
				{:else if media.kind === 'video'}
					<!-- svelte-ignore a11y_media_has_caption -->
					<video
						bind:this={videoEl}
						src={media.url}
						class="media-preview-video"
						controls
						playsinline
					>
						Your browser does not support video playback.
					</video>
				{:else if media.kind === 'audio'}
					<audio bind:this={audioEl} src={media.url} class="media-preview-audio" controls>
						Your browser does not support audio playback.
					</audio>
				{/if}
			</div>
		{/if}
	</div>

	<div class="dialog-footer">
		{#if media}
			<a href={media.downloadUrl} download={media.name} class="btn btn-sm btn-primary">
				<Icons name="download" size={15} />
				<span>Download File</span>
			</a>
		{/if}
		<button type="button" class="btn btn-sm" onclick={() => dialogEl?.close()}>Close</button>
	</div>
</dialog>
