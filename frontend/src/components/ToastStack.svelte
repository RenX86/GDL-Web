<script lang="ts">
	import { onMount } from 'svelte';
	import Icons, { type IconName } from './Icons.svelte';
	import { isAnyModalOpen } from '../lib/dialog';
	import { toastStore } from '../lib/toasts.svelte';
	import type { ToastItem, ToastKind } from '../lib/types';

	interface Props {
		suppressed?: boolean;
	}

	let { suppressed = false }: Props = $props();

	let polyfillReady = $state(
		typeof HTMLElement !== 'undefined' && Object.hasOwn(HTMLElement.prototype, 'popover')
	);

	onMount(async () => {
		if (!polyfillReady) {
			try {
				await import('@oddbird/popover-polyfill');
			} catch {
				// Proceed with fallback styling if polyfill cannot load
			}
			polyfillReady = true;
		}
	});

	function iconForKind(kind: ToastKind): IconName {
		switch (kind) {
			case 'success':
				return 'check';
			case 'error':
				return 'x-circle';
			case 'warning':
				return 'alert';
			default:
				return 'info';
		}
	}

	function toastPopover(node: HTMLElement, params: { toast: ToastItem; hidden: boolean }) {
		let current = params;
		let timerId: ReturnType<typeof setTimeout> | null = null;
		let paused = false;

		const clearTimer = () => {
			if (timerId !== null) {
				clearTimeout(timerId);
				timerId = null;
			}
		};

		const startTimer = () => {
			clearTimer();
			if (paused || current.hidden) return;
			timerId = setTimeout(() => {
				toastStore.dismiss(current.toast.id);
			}, current.toast.durationMs);
		};

		const syncVisibility = () => {
			const shouldHide = current.hidden || isAnyModalOpen();
			try {
				if (shouldHide) {
					if (typeof node.hidePopover === 'function' && node.matches(':popover-open')) {
						node.hidePopover();
					}
				} else if (typeof node.showPopover === 'function') {
					node.showPopover();
				}
			} catch {
				// Ignore popover API errors in non-supporting test environments
			}
			if (shouldHide) {
				clearTimer();
			} else {
				startTimer();
			}
		};

		const onPause = () => {
			paused = true;
			clearTimer();
		};

		const onResume = () => {
			if (node.contains(document.activeElement)) return;
			paused = false;
			startTimer();
		};

		node.addEventListener('focusin', onPause);
		node.addEventListener('focusout', onResume);
		node.addEventListener('pointerenter', onPause);
		node.addEventListener('pointerleave', onResume);

		syncVisibility();

		return {
			update(next: { toast: ToastItem; hidden: boolean }) {
				current = next;
				syncVisibility();
			},
			destroy() {
				clearTimer();
				node.removeEventListener('focusin', onPause);
				node.removeEventListener('focusout', onResume);
				node.removeEventListener('pointerenter', onPause);
				node.removeEventListener('pointerleave', onResume);
				try {
					if (typeof node.hidePopover === 'function' && node.matches(':popover-open')) {
						node.hidePopover();
					}
				} catch {
					// Ignore
				}
			},
		};
	}
</script>

<!-- Pre-mounted screen reader live regions (fallback when document.ariaNotify is unavailable) -->
<div class="visually-hidden" aria-live="polite" aria-atomic="true">
	{toastStore.politeAnnouncement}
</div>
<div class="visually-hidden" aria-live="assertive" aria-atomic="true">
	{toastStore.assertiveAnnouncement}
</div>

<div role="region" aria-label="Notifications" class="toast-region">
	{#if polyfillReady}
		{#each toastStore.toasts as toast (toast.id)}
			<div
				class="toast-popover"
				popover="manual"
				use:toastPopover={{ toast, hidden: suppressed }}
			>
				<div class="toast-header" data-kind={toast.kind}>
					<span class="toast-header-title">
						<Icons name={iconForKind(toast.kind)} size={15} />
						<span>{toast.title}</span>
					</span>
					<button
						type="button"
						class="toast-close-btn"
						onclick={() => toastStore.dismiss(toast.id)}
						aria-label={`Dismiss notification: ${toast.title}`}
					>
						Close
					</button>
				</div>
				<div class="toast-body">{toast.message}</div>
			</div>
		{/each}
	{/if}
</div>
