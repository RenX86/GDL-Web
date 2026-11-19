import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createThemeStore } from './theme.svelte';

function createMockMatchMedia(initialMatches: boolean) {
	let matches = initialMatches;
	const listeners = new Set<(event: MediaQueryListEvent) => void>();

	const mql = {
		get matches() {
			return matches;
		},
		media: '(prefers-color-scheme: dark)',
		onchange: null,
		addEventListener: vi.fn((type: string, cb: (event: MediaQueryListEvent) => void) => {
			if (type === 'change') listeners.add(cb);
		}),
		removeEventListener: vi.fn((type: string, cb: (event: MediaQueryListEvent) => void) => {
			if (type === 'change') listeners.delete(cb);
		}),
		addListener: vi.fn(),
		removeListener: vi.fn(),
		dispatchEvent: vi.fn(),
	};

	const setOsDark = (nextDark: boolean) => {
		matches = nextDark;
		const event = { matches: nextDark, media: mql.media } as MediaQueryListEvent;
		for (const listener of listeners) {
			listener(event);
		}
	};

	return { mql, setOsDark };
}

describe('system-aware theme store', () => {
	let cleanup: (() => void) | null = null;

	beforeEach(() => {
		localStorage.clear();
		const meta = document.createElement('meta');
		meta.setAttribute('name', 'color-scheme');
		meta.setAttribute('content', 'light dark');
		document.head.replaceChildren(meta);
	});

	afterEach(() => {
		cleanup?.();
		cleanup = null;
		vi.restoreAllMocks();
	});

	it('follows OS preference by default, stores opposite on toggle, and removes localStorage when toggling back', () => {
		const { mql } = createMockMatchMedia(false);
		vi.spyOn(window, 'matchMedia').mockReturnValue(mql as unknown as MediaQueryList);

		const store = createThemeStore();
		cleanup = store.attachListeners();

		const meta = () => document.querySelector('meta[name="color-scheme"]')?.getAttribute('content');

		expect(store.preference).toBe('system');
		expect(store.effectiveTheme).toBe('light');
		expect(localStorage.getItem('color-scheme')).toBeNull();
		expect(meta()).toBe('light dark');

		// Toggle away from light OS -> stores literal 'dark'
		store.toggle();
		expect(store.preference).toBe('dark');
		expect(store.effectiveTheme).toBe('dark');
		expect(localStorage.getItem('color-scheme')).toBe('dark');
		expect(meta()).toBe('dark');

		// Toggle back to match light OS -> removes localStorage entry and restores 'light dark'
		store.toggle();
		expect(store.preference).toBe('system');
		expect(store.effectiveTheme).toBe('light');
		expect(localStorage.getItem('color-scheme')).toBeNull();
		expect(meta()).toBe('light dark');
	});

	it('never retroactively removes a saved preference when OS theme changes', () => {
		const { mql, setOsDark } = createMockMatchMedia(false);
		vi.spyOn(window, 'matchMedia').mockReturnValue(mql as unknown as MediaQueryList);

		const store = createThemeStore();
		cleanup = store.attachListeners();

		// User explicitly picks dark while OS is light
		store.toggle();
		expect(localStorage.getItem('color-scheme')).toBe('dark');

		// Later, OS switches to dark: saved preference must NOT be retroactively removed
		setOsDark(true);
		expect(store.systemScheme).toBe('dark');
		expect(store.preference).toBe('dark');
		expect(localStorage.getItem('color-scheme')).toBe('dark');
		expect(
			document.querySelector('meta[name="color-scheme"]')?.getAttribute('content')
		).toBe('dark');
	});

	it('syncs color-scheme changes across tabs via storage events', () => {
		const { mql } = createMockMatchMedia(false);
		vi.spyOn(window, 'matchMedia').mockReturnValue(mql as unknown as MediaQueryList);

		const store = createThemeStore();
		cleanup = store.attachListeners();

		window.dispatchEvent(
			new StorageEvent('storage', { key: 'color-scheme', newValue: 'dark' })
		);
		expect(store.preference).toBe('dark');
		expect(store.effectiveTheme).toBe('dark');
		expect(
			document.querySelector('meta[name="color-scheme"]')?.getAttribute('content')
		).toBe('dark');

		window.dispatchEvent(
			new StorageEvent('storage', { key: 'color-scheme', newValue: null })
		);
		expect(store.preference).toBe('system');
		expect(store.effectiveTheme).toBe('light');
		expect(
			document.querySelector('meta[name="color-scheme"]')?.getAttribute('content')
		).toBe('light dark');
	});
});
