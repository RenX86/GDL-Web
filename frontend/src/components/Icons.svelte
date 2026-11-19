<script lang="ts">
	export type IconName =
		| 'sun'
		| 'moon'
		| 'download'
		| 'images'
		| 'video'
		| 'link'
		| 'trash'
		| 'cpu'
		| 'activity'
		| 'folder'
		| 'zip'
		| 'close'
		| 'terminal'
		| 'sliders'
		| 'alert'
		| 'shield'
		| 'info'
		| 'check'
		| 'play'
		| 'music'
		| 'file'
		| 'inbox'
		| 'x-circle';

	interface Props {
		name: IconName;
		size?: number;
	}

	let { name, size = 18 }: Props = $props();
</script>

<svg
	width={size}
	height={size}
	viewBox="0 0 24 24"
	fill="none"
	stroke="currentColor"
	stroke-width="2.25"
	stroke-linecap="round"
	stroke-linejoin="round"
	aria-hidden="true"
	focusable="false"
>
	{#if name === 'sun'}
		<circle cx="12" cy="12" r="4" />
		<path d="M12 2v2" />
		<path d="M12 20v2" />
		<path d="m4.93 4.93 1.41 1.41" />
		<path d="m17.66 17.66 1.41 1.41" />
		<path d="M2 12h2" />
		<path d="M20 12h2" />
		<path d="m6.34 17.66-1.41 1.41" />
		<path d="m19.07 4.93-1.41 1.41" />
	{:else if name === 'moon'}
		<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
	{:else if name === 'download'}
		<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
		<polyline points="7 10 12 15 17 10" />
		<line x1="12" x2="12" y1="15" y2="3" />
	{:else if name === 'images'}
		<rect width="18" height="18" x="3" y="3" rx="2" ry="2" />
		<circle cx="9" cy="9" r="2" />
		<path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21" />
	{:else if name === 'video'}
		<rect width="20" height="14" x="2" y="5" rx="2" />
		<polygon points="10 9 15 12 10 15 10 9" fill="currentColor" />
	{:else if name === 'link'}
		<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
		<path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
	{:else if name === 'trash'}
		<path d="M3 6h18" />
		<path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" />
		<path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
		<line x1="10" x2="10" y1="11" y2="17" />
		<line x1="14" x2="14" y1="11" y2="17" />
	{:else if name === 'cpu'}
		<rect width="16" height="16" x="4" y="4" rx="2" />
		<rect width="6" height="6" x="9" y="9" rx="1" />
		<path d="M15 2v2" />
		<path d="M15 20v2" />
		<path d="M2 15h2" />
		<path d="M2 9h2" />
		<path d="M20 15h2" />
		<path d="M20 9h2" />
		<path d="M9 2v2" />
		<path d="M9 20v2" />
	{:else if name === 'activity'}
		<polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
	{:else if name === 'folder'}
		<path
			d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"
		/>
	{:else if name === 'zip'}
		<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
		<polyline points="14 2 14 8 20 8" />
		<path d="M10 12v-1" />
		<path d="M10 16v-1" />
		<path d="M10 20v-1" />
	{:else if name === 'close'}
		<line x1="18" x2="6" y1="6" y2="18" />
		<line x1="6" x2="18" y1="6" y2="18" />
	{:else if name === 'terminal'}
		<polyline points="4 17 10 11 4 5" />
		<line x1="12" x2="20" y1="19" y2="19" />
	{:else if name === 'sliders'}
		<line x1="4" x2="20" y1="21" y2="21" />
		<line x1="4" x2="20" y1="14" y2="14" />
		<line x1="4" x2="20" y1="7" y2="7" />
		<circle cx="9" cy="7" r="2" fill="currentColor" />
		<circle cx="15" cy="14" r="2" fill="currentColor" />
		<circle cx="9" cy="21" r="2" fill="currentColor" />
	{:else if name === 'alert'}
		<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
		<line x1="12" x2="12" y1="9" y2="13" />
		<line x1="12" x2="12.01" y1="17" y2="17" />
	{:else if name === 'shield'}
		<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
		<line x1="12" x2="12" y1="8" y2="12" />
		<line x1="12" x2="12.01" y1="16" y2="16" />
	{:else if name === 'info'}
		<circle cx="12" cy="12" r="10" />
		<line x1="12" x2="12" y1="16" y2="12" />
		<line x1="12" x2="12.01" y1="8" y2="8" />
	{:else if name === 'check'}
		<circle cx="12" cy="12" r="10" />
		<path d="m9 12 2 2 4-4" />
	{:else if name === 'play'}
		<circle cx="12" cy="12" r="10" />
		<polygon points="10 8 16 12 10 16 10 8" fill="currentColor" />
	{:else if name === 'music'}
		<path d="M9 18V5l12-2v13" />
		<circle cx="6" cy="18" r="3" />
		<circle cx="18" cy="16" r="3" />
	{:else if name === 'file'}
		<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
		<polyline points="14 2 14 8 20 8" />
	{:else if name === 'inbox'}
		<polyline points="22 12 16 12 14 15 10 15 8 12 2 12" />
		<path
			d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"
		/>
	{:else if name === 'x-circle'}
		<circle cx="12" cy="12" r="10" />
		<line x1="15" x2="9" y1="9" y2="15" />
		<line x1="9" x2="15" y1="9" y2="15" />
	{/if}
</svg>
