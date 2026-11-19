try {
	const saved = localStorage.getItem('color-scheme');
	if (saved === 'light' || saved === 'dark') {
		const meta = document.querySelector('meta[name="color-scheme"]');
		if (meta) meta.setAttribute('content', saved);
	}
} catch {
	// Ignore storage access errors in restricted contexts
}
