<script lang="ts">
	import Icons from './Icons.svelte';
	import { attachLightDismiss } from '../lib/dialog';

	interface Props {
		open: boolean;
		onClose: () => void;
	}

	let { open, onClose }: Props = $props();

	let dialogEl = $state<HTMLDialogElement | null>(null);

	$effect(() => {
		const el = dialogEl;
		if (!el) return;
		const detach = attachLightDismiss(el);
		return () => detach();
	});

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
			onClose();
		}
	}

	const dialogExtraAttrs = { closedby: 'any' } as Record<string, string>;
</script>

<dialog
	bind:this={dialogEl}
	class="brutal-dialog"
	aria-labelledby="isp-block-title"
	aria-describedby="isp-block-desc"
	onclose={handleClose}
	{...dialogExtraAttrs}
>
	<div class="dialog-header dialog-header-danger">
		<h2 id="isp-block-title" class="dialog-title">
			<Icons name="shield" size={18} />
			<span>Access Restricted</span>
		</h2>
		<button
			type="button"
			class="btn btn-sm btn-icon"
			onclick={() => dialogEl?.close()}
			aria-label="Close access restricted notice"
		>
			<Icons name="close" size={16} />
		</button>
	</div>

	<div class="dialog-body" id="isp-block-desc" style="text-align: center;">
		<div style="margin-bottom: 0.75rem; color: var(--color-danger);">
			<Icons name="shield" size={44} />
		</div>
		<h3 style="margin-bottom: 0.5rem; font-weight: 900;">Connection Blocked</h3>
		<p style="font-weight: 700; margin-bottom: 0.5rem;">
			Content appears unavailable due to network or ISP-level restrictions.
		</p>
		<p class="form-help" style="font-size: 0.88rem;">
			The connection was forcibly closed by the remote host. This typically indicates an ISP filter,
			DNS block, or regional restriction.
		</p>
	</div>

	<div class="dialog-footer" style="justify-content: center;">
		<button type="button" class="btn btn-sm btn-primary" onclick={() => dialogEl?.close()}>
			Understood
		</button>
	</div>
</dialog>
