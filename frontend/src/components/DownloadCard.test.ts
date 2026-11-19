import { render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import DownloadCard from './DownloadCard.svelte';
import type { DownloadDTO } from '../lib/types';

function renderCard(overrides: Partial<DownloadDTO>) {
	const download: DownloadDTO = {
		id: 'dl-1',
		url: 'https://example.com/gallery/123',
		status: 'pending',
		progress: 0,
		message: '',
		files_downloaded: 0,
		total_files: 0,
		...overrides,
	};

	return render(DownloadCard, {
		props: {
			download,
			onViewFiles: vi.fn(),
			onCancel: vi.fn(),
			onRequestDelete: vi.fn(),
		},
	});
}

describe('DownloadCard security, status badges, and semantics', () => {
	it('renders untrusted HTML/script payloads in url and message strictly as escaped text (XSS safe)', () => {
		const maliciousUrl = 'https://evil.test/?q=<script>window.__xss=1</script><img src=x onerror=alert(1)>';
		const maliciousMsg = '<script>alert("xss")</script><b>Not Bold</b><img src=x onerror=alert(2)>';

		const { container } = renderCard({
			url: maliciousUrl,
			status: 'failed',
			message: maliciousMsg,
		});

		// Must not create any <script> or <img> or <b> elements from untrusted text
		expect(container.querySelector('script')).toBeNull();
		expect(container.querySelector('img')).toBeNull();
		expect(container.querySelector('b')).toBeNull();

		// Must render exact literal strings safely as text
		expect(screen.getByText(maliciousUrl)).toBeInTheDocument();
		expect(screen.getByText(maliciousMsg)).toBeInTheDocument();
	});

	it('renders distinct Queued badge and indeterminate <progress> for pending and queued downloads', () => {
		const { container: c1 } = renderCard({ status: 'pending', progress: 0 });
		expect(c1.querySelector('.badge-queued')).toHaveTextContent('Queued');
		const progress1 = c1.querySelector('progress');
		expect(progress1).not.toBeNull();
		expect(progress1?.hasAttribute('value')).toBe(false);

		const { container: c2 } = renderCard({ status: 'queued', progress: 0 });
		expect(c2.querySelector('.badge-queued')).toHaveTextContent('Queued');
		expect(c2.querySelector('progress')?.hasAttribute('value')).toBe(false);
	});

	it('renders Cancelled badge (not Queued) and Delete action for cancelled downloads', () => {
		const { container } = renderCard({
			status: 'cancelled',
			progress: 25,
			url: 'https://example.com/item-cancel',
		});

		expect(container.querySelector('.badge-cancelled')).toHaveTextContent('Cancelled');
		expect(
			screen.getByRole('button', { name: 'Delete download for https://example.com/item-cancel' })
		).toBeInTheDocument();
	});

	it('renders determinate <progress> and Files + ZIP + Delete controls when completed', () => {
		const { container } = renderCard({
			id: 'done-42',
			status: 'completed',
			progress: 100,
			files_downloaded: 5,
			total_files: 5,
			url: 'https://example.com/done',
		});

		expect(container.querySelector('.badge-completed')).toHaveTextContent('Completed');
		const progress = container.querySelector('progress');
		expect(progress?.getAttribute('value')).toBe('100');
		expect(screen.getByText('5/5 files')).toBeInTheDocument();
		expect(
			screen.getByRole('button', { name: 'View files for https://example.com/done' })
		).toBeInTheDocument();
		expect(
			screen.getByRole('link', { name: 'Download ZIP archive for https://example.com/done' })
		).toHaveAttribute('href', '/api/downloads/done-42/zip');
	});
});
