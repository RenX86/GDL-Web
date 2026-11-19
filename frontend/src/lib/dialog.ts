/**
 * Native <dialog> helpers following modern web platform best practices.
 * Uses native `closedby="any"` where supported, with a minimal pointerdown/pointerup
 * outside-click fallback for browsers without `HTMLDialogElement.prototype.closedBy`.
 */

export function supportsClosedBy(): boolean {
	return typeof HTMLDialogElement !== 'undefined' && 'closedBy' in HTMLDialogElement.prototype;
}

export function isAnyModalOpen(): boolean {
	if (typeof document === 'undefined') return false;
	try {
		return document.querySelector('dialog:modal') !== null;
	} catch {
		return document.querySelector('dialog[open]') !== null;
	}
}

export function attachLightDismiss(dialog: HTMLDialogElement): () => void {
	if (supportsClosedBy()) {
		return () => {};
	}

	let pointerStartedOutside = false;

	const isOutsideBounds = (event: PointerEvent): boolean => {
		if (event.target !== dialog) return false;
		const rect = dialog.getBoundingClientRect();
		if (rect.width === 0 && rect.height === 0) return true;
		return (
			event.clientX < rect.left ||
			event.clientX > rect.right ||
			event.clientY < rect.top ||
			event.clientY > rect.bottom
		);
	};

	const onPointerDown = (event: PointerEvent) => {
		pointerStartedOutside = event.button === 0 && isOutsideBounds(event);
	};

	const onPointerUp = (event: PointerEvent) => {
		if (pointerStartedOutside && isOutsideBounds(event) && dialog.open) {
			dialog.close('dismiss');
		}
		pointerStartedOutside = false;
	};

	dialog.addEventListener('pointerdown', onPointerDown);
	dialog.addEventListener('pointerup', onPointerUp);

	return () => {
		dialog.removeEventListener('pointerdown', onPointerDown);
		dialog.removeEventListener('pointerup', onPointerUp);
	};
}
