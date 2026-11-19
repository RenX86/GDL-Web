import { beforeEach, describe, expect, it } from 'vitest';
import { createDownloadsStore } from './downloads.svelte';
import type { DownloadDTO } from './types';

function makeDownload(overrides: Partial<DownloadDTO> & { id: string }): DownloadDTO {
	return {
		url: `https://example.com/${overrides.id}`,
		status: 'pending',
		progress: 0,
		start_time: '2026-01-01T12:00:00Z',
		message: '',
		files_downloaded: 0,
		total_files: 0,
		...overrides,
	};
}

describe('downloads store SSE, sorting, and filtering', () => {
	beforeEach(() => {
		sessionStorage.clear();
	});

	it('sorts newest downloads first on initial SSE event', () => {
		const store = createDownloadsStore();
		expect(store.loading).toBe(true);

		store.handleEvent({
			type: 'initial',
			data: [
				makeDownload({ id: 'old', start_time: '2026-01-01T10:00:00Z', status: 'completed' }),
				makeDownload({ id: 'newest', start_time: '2026-01-01T14:00:00Z', status: 'downloading' }),
				makeDownload({ id: 'mid', start_time: '2026-01-01T12:00:00Z', status: 'pending' }),
			],
		});

		expect(store.loading).toBe(false);
		expect(store.filteredItems.map((d) => d.id)).toEqual(['newest', 'mid', 'old']);
	});

	it('reactively filters by all, active, completed, and failed', () => {
		const store = createDownloadsStore();
		store.handleEvent({
			type: 'initial',
			data: [
				makeDownload({ id: 'q1', status: 'queued' }),
				makeDownload({ id: 'p1', status: 'pending' }),
				makeDownload({ id: 'd1', status: 'downloading', progress: 40 }),
				makeDownload({ id: 'c1', status: 'completed', progress: 100 }),
				makeDownload({ id: 'f1', status: 'failed', error: 'Boom' }),
				makeDownload({ id: 'x1', status: 'cancelled' }),
			],
		});

		expect(store.counts).toEqual({
			all: 6,
			active: 3,
			completed: 1,
			failed: 2,
		});

		store.setFilter('active');
		expect(store.filteredItems.map((d) => d.id).sort()).toEqual(['d1', 'p1', 'q1']);

		store.setFilter('completed');
		expect(store.filteredItems.map((d) => d.id)).toEqual(['c1']);

		store.setFilter('failed');
		expect(store.filteredItems.map((d) => d.id).sort()).toEqual(['f1', 'x1']);

		store.setFilter('all');
		expect(store.filteredItems).toHaveLength(6);
	});

	it('handles SSE update, delete, and clear events cleanly', () => {
		const store = createDownloadsStore();
		store.handleEvent({
			type: 'initial',
			data: [makeDownload({ id: 'job-1', status: 'queued', progress: 0 })],
		});

		// Update existing item
		store.handleEvent({
			type: 'update',
			data: makeDownload({ id: 'job-1', status: 'downloading', progress: 55 }),
		});
		expect(store.items).toHaveLength(1);
		expect(store.items[0].status).toBe('downloading');
		expect(store.items[0].progress).toBe(55);

		// Add new item via update
		store.handleEvent({
			type: 'update',
			data: makeDownload({
				id: 'job-2',
				status: 'completed',
				progress: 100,
				start_time: '2026-01-01T15:00:00Z',
			}),
		});
		expect(store.filteredItems.map((d) => d.id)).toEqual(['job-2', 'job-1']);

		// Delete one item
		store.handleEvent({ type: 'delete', data: { id: 'job-1' } });
		expect(store.items.map((d) => d.id)).toEqual(['job-2']);

		// Clear all items
		store.handleEvent({ type: 'clear', data: {} });
		expect(store.items).toHaveLength(0);
	});

	it('surfaces ISP block dialog once per download ID', () => {
		const store = createDownloadsStore();
		store.handleEvent({
			type: 'update',
			data: makeDownload({ id: 'blocked-1', status: 'failed', isp_block: true }),
		});
		expect(store.ispBlockDownloadId).toBe('blocked-1');

		store.dismissIspBlock();
		expect(store.ispBlockDownloadId).toBeNull();

		// Duplicate SSE update for the same download does not re-open the modal
		store.handleEvent({
			type: 'update',
			data: makeDownload({ id: 'blocked-1', status: 'failed', isp_block: true }),
		});
		expect(store.ispBlockDownloadId).toBeNull();
	});
});
