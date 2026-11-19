import type { ToastItem, ToastKind } from './types';

let nextToastId = 0;

function createId(): string {
	nextToastId += 1;
	return `toast-${Date.now()}-${nextToastId}`;
}

export function createToastStore() {
	let toasts = $state<ToastItem[]>([]);
	let politeAnnouncement = $state('');
	let assertiveAnnouncement = $state('');

	function announce(text: string, kind: ToastKind): void {
		const isAssertive = kind === 'error' || kind === 'warning';
		const doc =
			typeof document !== 'undefined'
				? (document as Document & {
						ariaNotify?: (message: string, options?: { priority?: 'normal' | 'high' }) => void;
					})
				: null;

		if (doc && typeof doc.ariaNotify === 'function') {
			doc.ariaNotify(text, { priority: isAssertive ? 'high' : 'normal' });
			return;
		}

		// Fallback to pre-mounted live regions (toggle whitespace to re-trigger identical consecutive messages)
		if (isAssertive) {
			assertiveAnnouncement = assertiveAnnouncement === text ? `${text}\u00A0` : text;
		} else {
			politeAnnouncement = politeAnnouncement === text ? `${text}\u00A0` : text;
		}
	}

	function push(
		title: string,
		message: string,
		kind: ToastKind = 'info',
		durationMs = kind === 'error' ? 7000 : 4500
	): string {
		const id = createId();
		const item: ToastItem = { id, title, message, kind, durationMs };
		toasts = [...toasts.slice(-4), item];
		announce(`${title}: ${message}`, kind);
		return id;
	}

	function dismiss(id: string): void {
		toasts = toasts.filter((t) => t.id !== id);
	}

	function clear(): void {
		toasts = [];
	}

	return {
		get toasts() {
			return toasts;
		},
		get politeAnnouncement() {
			return politeAnnouncement;
		},
		get assertiveAnnouncement() {
			return assertiveAnnouncement;
		},
		push,
		dismiss,
		clear,
	};
}

export const toastStore = createToastStore();
