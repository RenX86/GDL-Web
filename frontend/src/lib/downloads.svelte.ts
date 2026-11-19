import { fetchDownloads } from './api';
import { normalizeStatus, type DownloadDTO, type DownloadFilter, type SSEEvent } from './types';

function getTimestamp(item: DownloadDTO): number {
	const raw = item.start_time ?? item.created_at;
	if (!raw) return 0;
	const parsed = Date.parse(raw);
	return Number.isNaN(parsed) ? 0 : parsed;
}

function hasSeenIspBlock(id: string): boolean {
	try {
		return sessionStorage.getItem(`seen_isp_block_${id}`) === 'true';
	} catch {
		return false;
	}
}

function markSeenIspBlock(id: string): void {
	try {
		sessionStorage.setItem(`seen_isp_block_${id}`, 'true');
	} catch {
		// Ignore sessionStorage restrictions
	}
}

export function createDownloadsStore() {
	let items = $state<DownloadDTO[]>([]);
	let filter = $state<DownloadFilter>('all');
	let loading = $state(true);
	let connected = $state(false);
	let ispBlockDownloadId = $state<string | null>(null);
	const seenIspBlocks = new Set<string>();

	const sortedItems = $derived.by(() => {
		return [...items].sort((a, b) => getTimestamp(b) - getTimestamp(a));
	});

	const counts = $derived.by(() => {
		let active = 0;
		let completed = 0;
		let failed = 0;
		for (const item of items) {
			const status = normalizeStatus(item.status);
			if (status === 'queued' || status === 'downloading') active += 1;
			else if (status === 'completed') completed += 1;
			else if (status === 'failed' || status === 'cancelled') failed += 1;
		}
		return {
			all: items.length,
			active,
			completed,
			failed,
		};
	});

	const filteredItems = $derived.by(() => {
		if (filter === 'all') return sortedItems;
		return sortedItems.filter((item) => {
			const status = normalizeStatus(item.status);
			if (filter === 'active') return status === 'queued' || status === 'downloading';
			if (filter === 'completed') return status === 'completed';
			if (filter === 'failed') return status === 'failed' || status === 'cancelled';
			return true;
		});
	});

	function checkIspBlock(item: DownloadDTO): void {
		if (!item.isp_block) return;
		if (seenIspBlocks.has(item.id) || hasSeenIspBlock(item.id)) return;
		seenIspBlocks.add(item.id);
		markSeenIspBlock(item.id);
		ispBlockDownloadId = item.id;
	}

	function upsert(item: DownloadDTO): void {
		checkIspBlock(item);
		const index = items.findIndex((existing) => existing.id === item.id);
		if (index >= 0) {
			items = [...items.slice(0, index), item, ...items.slice(index + 1)];
		} else {
			items = [item, ...items];
		}
	}

	function remove(id: string): void {
		items = items.filter((item) => item.id !== id);
	}

	function clear(): void {
		items = [];
		ispBlockDownloadId = null;
	}

	function handleEvent(event: SSEEvent): void {
		switch (event.type) {
			case 'initial': {
				const list = Array.isArray(event.data) ? event.data : [];
				items = list;
				loading = false;
				for (const item of list) {
					checkIspBlock(item);
				}
				break;
			}
			case 'update': {
				loading = false;
				upsert(event.data);
				break;
			}
			case 'delete': {
				remove(event.data.id);
				break;
			}
			case 'clear': {
				loading = false;
				clear();
				break;
			}
		}
	}

	function setFilter(next: DownloadFilter): void {
		filter = next;
	}

	function dismissIspBlock(): void {
		ispBlockDownloadId = null;
	}

	async function refresh(): Promise<void> {
		try {
			const list = await fetchDownloads();
			items = list;
			loading = false;
		} catch {
			loading = false;
		}
	}

	function connect(): () => void {
		if (typeof EventSource === 'undefined') {
			loading = false;
			return () => {};
		}

		const source = new EventSource('/api/events');

		source.onopen = () => {
			connected = true;
		};

		source.onmessage = (messageEvent) => {
			connected = true;
			try {
				const parsed = JSON.parse(messageEvent.data) as SSEEvent;
				handleEvent(parsed);
			} catch {
				// Ignore malformed SSE payloads
			}
		};

		source.onerror = () => {
			connected = false;
			if (source.readyState === EventSource.CLOSED) {
				loading = false;
			}
		};

		return () => {
			connected = false;
			source.close();
		};
	}

	return {
		get items() {
			return items;
		},
		get sortedItems() {
			return sortedItems;
		},
		get filteredItems() {
			return filteredItems;
		},
		get counts() {
			return counts;
		},
		get filter() {
			return filter;
		},
		get loading() {
			return loading;
		},
		get connected() {
			return connected;
		},
		get ispBlockDownloadId() {
			return ispBlockDownloadId;
		},
		setFilter,
		upsert,
		remove,
		clear,
		handleEvent,
		dismissIspBlock,
		refresh,
		connect,
	};
}

export const downloadsStore = createDownloadsStore();
