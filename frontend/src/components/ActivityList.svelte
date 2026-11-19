<script lang="ts">
	import Icons from './Icons.svelte';
	import DownloadCard from './DownloadCard.svelte';
	import { downloadsStore } from '../lib/downloads.svelte';
	import type { DownloadDTO, DownloadFilter } from '../lib/types';

	interface Props {
		cancellingIds: ReadonlySet<string>;
		onViewFiles: (download: DownloadDTO) => void;
		onCancel: (download: DownloadDTO) => void;
		onRequestDelete: (download: DownloadDTO) => void;
	}

	let { cancellingIds, onViewFiles, onCancel, onRequestDelete }: Props = $props();

	const filters: { id: DownloadFilter; label: string }[] = [
		{ id: 'all', label: 'All' },
		{ id: 'active', label: 'Active' },
		{ id: 'completed', label: 'Done' },
		{ id: 'failed', label: 'Failed' },
	];

	function countFor(id: DownloadFilter): number {
		return downloadsStore.counts[id];
	}
</script>

<section aria-labelledby="activity-heading">
	<div class="activity-header">
		<h2 id="activity-heading" class="activity-title">
			<Icons name="activity" size={22} />
			<span>Activity</span>
		</h2>

		<div class="filter-group" role="group" aria-label="Filter downloads by status">
			{#each filters as item (item.id)}
				<button
					type="button"
					class="filter-btn"
					aria-pressed={downloadsStore.filter === item.id}
					onclick={() => downloadsStore.setFilter(item.id)}
				>
					{item.label} ({countFor(item.id)})
				</button>
			{/each}
		</div>
	</div>

	<div class="downloads-list">
		{#if downloadsStore.loading}
			<div class="empty-state" role="status">
				<span class="spinner" aria-hidden="true"></span>
				<p>Connecting to server…</p>
			</div>
		{:else if downloadsStore.filteredItems.length === 0}
			<div class="empty-state">
				<Icons name="inbox" size={36} />
				<p>
					{downloadsStore.filter === 'all'
						? 'No downloads yet. Paste a URL to get started.'
						: 'No downloads match this filter.'}
				</p>
			</div>
		{:else}
			{#each downloadsStore.filteredItems as download (download.id)}
				<DownloadCard
					{download}
					cancelling={cancellingIds.has(download.id)}
					{onViewFiles}
					{onCancel}
					{onRequestDelete}
				/>
			{/each}
		{/if}
	</div>
</section>
