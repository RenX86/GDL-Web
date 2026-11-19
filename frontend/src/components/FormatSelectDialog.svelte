<script lang="ts">
	import Icons from './Icons.svelte';
	import { attachLightDismiss } from '../lib/dialog';
	import { formatOptionLabel, type FormatsResponse } from '../lib/types';

	interface Props {
		formats: FormatsResponse | null;
		busy?: boolean;
		onClose: () => void;
		onConfirm: (formatId: string) => void;
	}

	let { formats, busy = false, onClose, onConfirm }: Props = $props();

	let dialogEl = $state<HTMLDialogElement | null>(null);
	let activeTab = $state<'combined' | 'custom'>('combined');
	let selectedCombined = $state('');
	let selectedVideo = $state('');
	let selectedAudio = $state('');

	$effect(() => {
		const el = dialogEl;
		if (!el) return;
		const detach = attachLightDismiss(el);
		return () => detach();
	});

	$effect(() => {
		const el = dialogEl;
		if (!el) return;

		if (formats) {
			selectedCombined = formats.combined[0]?.format_id ?? '';
			selectedVideo = formats.video[0]?.format_id ?? '';
			selectedAudio = formats.audio[0]?.format_id ?? '';
			activeTab = formats.combined.length > 0 ? 'combined' : 'custom';

			if (!el.open && typeof el.showModal === 'function') {
				el.showModal();
			}
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

	function handleTabKeydown(event: KeyboardEvent) {
		if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
			event.preventDefault();
			activeTab = activeTab === 'combined' ? 'custom' : 'combined';
		}
	}

	function handleConfirm() {
		let formatId = '';
		if (activeTab === 'combined') {
			formatId = selectedCombined;
		} else if (selectedVideo && selectedAudio) {
			formatId = `${selectedVideo}+${selectedAudio}`;
		} else {
			formatId = selectedVideo || selectedAudio;
		}

		if (!formatId) return;
		onConfirm(formatId);
	}

	const canSubmit = $derived(
		activeTab === 'combined'
			? selectedCombined.length > 0
			: selectedVideo.length > 0 || selectedAudio.length > 0
	);

	const dialogExtraAttrs = { closedby: 'any' } as Record<string, string>;
</script>

<dialog
	bind:this={dialogEl}
	class="brutal-dialog dialog-lg"
	aria-labelledby="format-dialog-title"
	onclose={handleClose}
	{...dialogExtraAttrs}
>
	<div class="dialog-header">
		<h2 id="format-dialog-title" class="dialog-title">
			<Icons name="sliders" size={18} />
			<span>Select Format</span>
		</h2>
		<button
			type="button"
			class="btn btn-sm btn-icon"
			onclick={() => dialogEl?.close()}
			aria-label="Close format selection dialog"
		>
			<Icons name="close" size={16} />
		</button>
	</div>

	<div class="dialog-body">
		{#if formats}
			<div class="format-summary">
				{#if formats.thumbnail}
					<img
						src={formats.thumbnail}
						alt=""
						class="format-thumb"
						width="112"
						height="64"
						decoding="async"
					/>
				{/if}
				<div>
					<h3 style="margin: 0; font-size: 1rem; font-weight: 800;">{formats.title}</h3>
				</div>
			</div>

			<div
				class="tab-list"
				role="tablist"
				aria-label="Format mode"
				tabindex="-1"
				onkeydown={handleTabKeydown}
			>
				<button
					type="button"
					id="tab-combined"
					class="tab-btn"
					role="tab"
					aria-selected={activeTab === 'combined'}
					aria-controls="panel-combined"
					onclick={() => (activeTab = 'combined')}
				>
					Pre-Combined (Easy)
				</button>
				<button
					type="button"
					id="tab-custom"
					class="tab-btn"
					role="tab"
					aria-selected={activeTab === 'custom'}
					aria-controls="panel-custom"
					onclick={() => (activeTab = 'custom')}
				>
					Custom (Video + Audio)
				</button>
			</div>

			{#if activeTab === 'combined'}
				<div id="panel-combined" role="tabpanel" aria-labelledby="tab-combined" class="form-group">
					<label for="combinedFormatSelect" class="form-label">Select Quality</label>
					<select
						id="combinedFormatSelect"
						class="select-control"
						bind:value={selectedCombined}
						disabled={formats.combined.length === 0}
					>
						{#if formats.combined.length === 0}
							<option value="">No pre-combined formats available</option>
						{:else}
							{#each formats.combined as option (option.format_id)}
								<option value={option.format_id}>{formatOptionLabel(option)}</option>
							{/each}
						{/if}
					</select>
				</div>
			{:else}
				<div id="panel-custom" role="tabpanel" aria-labelledby="tab-custom" class="form-stack">
					<div class="format-grid-2">
						<div class="form-group">
							<label for="videoFormatSelect" class="form-label">Video Track</label>
							<select
								id="videoFormatSelect"
								class="select-control"
								bind:value={selectedVideo}
								disabled={formats.video.length === 0}
							>
								{#if formats.video.length === 0}
									<option value="">No video tracks available</option>
								{:else}
									{#each formats.video as option (option.format_id)}
										<option value={option.format_id}>{formatOptionLabel(option)}</option>
									{/each}
								{/if}
							</select>
						</div>

						<div class="form-group">
							<label for="audioFormatSelect" class="form-label">Audio Track</label>
							<select
								id="audioFormatSelect"
								class="select-control"
								bind:value={selectedAudio}
								disabled={formats.audio.length === 0}
							>
								{#if formats.audio.length === 0}
									<option value="">No audio tracks available</option>
								{:else}
									{#each formats.audio as option (option.format_id)}
										<option value={option.format_id}>{formatOptionLabel(option)}</option>
									{/each}
								{/if}
							</select>
						</div>
					</div>

					<p class="form-help">
						Selected video and audio tracks will be merged automatically using FFmpeg.
					</p>
				</div>
			{/if}
		{/if}
	</div>

	<div class="dialog-footer">
		<button type="button" class="btn btn-sm" onclick={() => dialogEl?.close()} disabled={busy}>
			Cancel
		</button>
		<button
			type="button"
			class="btn btn-sm btn-primary"
			onclick={handleConfirm}
			disabled={!canSubmit || busy}
		>
			{#if busy}
				<span class="spinner" aria-hidden="true"></span>
				<span>Starting…</span>
			{:else}
				<Icons name="download" size={15} />
				<span>Download Selected</span>
			{/if}
		</button>
	</div>
</dialog>
