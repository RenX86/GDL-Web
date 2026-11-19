<script lang="ts">
	import Icons from './Icons.svelte';

	interface Props {
		open: boolean;
		title: string;
		message: string;
		detail?: string;
		confirmLabel: string;
		cancelLabel?: string;
		busy?: boolean;
		onCancel: () => void;
		onConfirm: () => void;
	}

	let {
		open,
		title,
		message,
		detail = '',
		confirmLabel,
		cancelLabel = 'Cancel',
		busy = false,
		onCancel,
		onConfirm,
	}: Props = $props();

	let dialogEl = $state<HTMLDialogElement | null>(null);

	$effect(() => {
		const el = dialogEl;
		if (!el) return;
		if (open) {
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
		if (open) {
			onCancel();
		}
	}
</script>

<dialog
	bind:this={dialogEl}
	class="brutal-dialog"
	aria-labelledby="confirm-dialog-title"
	aria-describedby="confirm-dialog-desc"
	onclose={handleClose}
>
	<div class="dialog-header dialog-header-danger">
		<h2 id="confirm-dialog-title" class="dialog-title">
			<Icons name="alert" size={18} />
			<span>{title}</span>
		</h2>
		<button
			type="button"
			class="btn btn-sm btn-icon"
			onclick={() => dialogEl?.close()}
			disabled={busy}
			aria-label="Close confirmation dialog"
		>
			<Icons name="close" size={16} />
		</button>
	</div>

	<div class="dialog-body" id="confirm-dialog-desc">
		<p style="font-weight: 800; margin-bottom: 0.5rem;">{message}</p>
		{#if detail}
			<p class="form-help" style="font-size: 0.9rem;">{detail}</p>
		{/if}
	</div>

	<div class="dialog-footer">
		<!-- svelte-ignore a11y_autofocus -->
		<button
			type="button"
			class="btn btn-sm"
			autofocus
			onclick={() => dialogEl?.close()}
			disabled={busy}
		>
			{cancelLabel}
		</button>
		<button type="button" class="btn btn-sm btn-danger" onclick={onConfirm} disabled={busy}>
			{#if busy}
				<span class="spinner" aria-hidden="true"></span>
				<span>Working…</span>
			{:else}
				<span>{confirmLabel}</span>
			{/if}
		</button>
	</div>
</dialog>
