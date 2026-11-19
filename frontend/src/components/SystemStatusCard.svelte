<script lang="ts">
	import { onMount } from 'svelte';
	import Icons from './Icons.svelte';
	import { fetchEnginesStatus } from '../lib/api';
	import type { EnginesStatusResponse } from '../lib/types';

	let engines = $state<EnginesStatusResponse | null>(null);
	let loadError = $state(false);

	function formatVersion(value: string | null | undefined): string {
		if (!value) return 'Unavailable';
		return value;
	}

	onMount(async () => {
		try {
			engines = await fetchEnginesStatus();
		} catch {
			loadError = true;
		}
	});
</script>

<section class="card" aria-labelledby="engines-heading">
	<div class="card-header">
		<h2 id="engines-heading" class="card-title">
			<Icons name="cpu" size={18} />
			<span>System Engines</span>
		</h2>
		<span class="badge badge-completed">
			{engines?.runtime_updates_enabled ? 'Updatable' : 'Ready'}
		</span>
	</div>

	<div class="card-body">
		{#if loadError}
			<p class="form-help">Could not load engine versions.</p>
		{:else if !engines}
			<p class="form-help">Loading engine versions…</p>
		{:else}
			<div class="engine-row">
				<span class="engine-name">
					<Icons name="images" size={15} />
					<span>gallery-dl</span>
				</span>
				<span class="badge badge-neutral">{formatVersion(engines.gallery_dl)}</span>
			</div>

			<div class="engine-row">
				<span class="engine-name">
					<Icons name="video" size={15} />
					<span>yt-dlp</span>
				</span>
				<span class="badge badge-neutral">{formatVersion(engines.yt_dlp)}</span>
			</div>

			<div class="engine-row">
				<span class="engine-name">
					<Icons name="sliders" size={15} />
					<span>ffmpeg</span>
				</span>
				<span class="badge badge-neutral">{formatVersion(engines.ffmpeg)}</span>
			</div>
		{/if}
	</div>
</section>
