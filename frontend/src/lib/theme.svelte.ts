export type ColorScheme = 'light' | 'dark';
export type ThemePreference = 'system' | ColorScheme;

const STORAGE_KEY = 'color-scheme';

function readStoredPreference(): ThemePreference {
	try {
		const raw = localStorage.getItem(STORAGE_KEY);
		if (raw === 'light' || raw === 'dark') return raw;
	} catch {
		// Ignore storage access errors
	}
	return 'system';
}

function readSystemScheme(): ColorScheme {
	if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
		return 'light';
	}
	return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function syncMetaTag(preference: ThemePreference): void {
	if (typeof document === 'undefined') return;
	let meta = document.querySelector<HTMLMetaElement>('meta[name="color-scheme"]');
	if (!meta) {
		meta = document.createElement('meta');
		meta.setAttribute('name', 'color-scheme');
		document.head.appendChild(meta);
	}
	meta.setAttribute('content', preference === 'system' ? 'light dark' : preference);
}

export function createThemeStore() {
	const initialPreference = readStoredPreference();
	let preference = $state<ThemePreference>(initialPreference);
	let systemScheme = $state<ColorScheme>(readSystemScheme());

	const effectiveTheme = $derived<ColorScheme>(
		preference === 'system' ? systemScheme : preference
	);

	syncMetaTag(initialPreference);

	function applyPreference(next: ThemePreference): void {
		preference = next;
		try {
			if (next === 'system') {
				localStorage.removeItem(STORAGE_KEY);
			} else {
				localStorage.setItem(STORAGE_KEY, next);
			}
		} catch {
			// Ignore storage errors
		}
		syncMetaTag(next);
	}

	function toggle(): void {
		const currentEffective: ColorScheme = preference === 'system' ? systemScheme : preference;
		const target: ColorScheme = currentEffective === 'dark' ? 'light' : 'dark';
		// Following system preference by default: remove stored override when toggling back to match OS
		if (target === systemScheme) {
			applyPreference('system');
		} else {
			applyPreference(target);
		}
	}

	function attachListeners(): () => void {
		if (typeof window === 'undefined') return () => {};

		const mediaQuery =
			typeof window.matchMedia === 'function'
				? window.matchMedia('(prefers-color-scheme: dark)')
				: null;

		const onMediaChange = (event: MediaQueryListEvent) => {
			// Never retroactively remove localStorage override on OS theme changes
			systemScheme = event.matches ? 'dark' : 'light';
		};

		const onStorage = (event: StorageEvent) => {
			if (event.key !== null && event.key !== STORAGE_KEY) return;
			const next: ThemePreference =
				event.newValue === 'light' || event.newValue === 'dark' ? event.newValue : 'system';
			preference = next;
			syncMetaTag(next);
		};

		mediaQuery?.addEventListener('change', onMediaChange);
		window.addEventListener('storage', onStorage);

		return () => {
			mediaQuery?.removeEventListener('change', onMediaChange);
			window.removeEventListener('storage', onStorage);
		};
	}

	return {
		get preference() {
			return preference;
		},
		get systemScheme() {
			return systemScheme;
		},
		get effectiveTheme() {
			return effectiveTheme;
		},
		toggle,
		attachListeners,
	};
}

export const themeStore = createThemeStore();
