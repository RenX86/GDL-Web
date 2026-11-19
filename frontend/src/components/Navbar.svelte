<script lang="ts">
	import Icons from './Icons.svelte';
	import { themeStore } from '../lib/theme.svelte';

	const isDark = $derived(themeStore.effectiveTheme === 'dark');
	const nextModeLabel = $derived(isDark ? 'Switch to light theme' : 'Switch to dark theme');
</script>

<a href="#main-content" class="skip-link visually-hidden">Skip to main content</a>

<header class="navbar">
	<nav class="navbar-inner" aria-label="Primary">
		<div class="navbar-brand">
			<img src="/logo.png" alt="" width="36" height="36" decoding="async" />
			<h1 class="navbar-title">Gallery-DL Web</h1>
		</div>

		<div class="navbar-actions">
			<button
				type="button"
				class="theme-toggle-btn"
				onclick={() => themeStore.toggle()}
				aria-pressed={isDark}
				aria-label={nextModeLabel}
			>
				<Icons name={isDark ? 'sun' : 'moon'} size={16} />
				<span>{isDark ? 'Light' : 'Dark'}</span>
			</button>
		</div>
	</nav>
</header>
