<script lang="ts">
	// The line icons used in the designs (24×24, stroke).
	let { name, size = 18, stroke = 1.9 }: { name: string; size?: number; stroke?: number } = $props();
</script>

<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width={stroke} stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
	{#if name === 'home'}<path d="M4 11l8-7 8 7v9h-5v-6H9v6H4z" />
	{:else if name === 'projects'}<rect x="3" y="7" width="18" height="13" rx="2" /><path d="M9 7V4h6v3M3 13h18" />
	{:else if name === 'programs'}<rect x="3" y="4" width="7" height="7" rx="1.5" /><rect x="14" y="4" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="18" height="6" rx="1.5" />
	{:else if name === 'roadmap'}<path d="M4 6h10M8 12h12M4 18h8" />
	{:else if name === 'risks'}<path d="M12 3l8 3v6c0 4.5-3.4 8-8 9-4.6-1-8-4.5-8-9V6z" /><path d="M12 8v5M12 16v.5" />
	{:else if name === 'admin'}<rect x="4" y="4" width="7" height="7" rx="2" /><rect x="13" y="4" width="7" height="7" rx="2" /><rect x="4" y="13" width="7" height="7" rx="2" /><rect x="13" y="13" width="7" height="7" rx="2" />
	{:else if name === 'search'}<circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" />
	{:else if name === 'bell'}<path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15zM10 21h4" />
	{:else if name === 'download'}<path d="M12 4v11M7 10l5 5 5-5M5 20h14" />
	{:else if name === 'file'}<path d="M7 3h7l5 5v13H7zM14 3v5h5" />
	{:else if name === 'lock'}<rect x="5" y="11" width="14" height="9" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" />
	{:else if name === 'arrow'}<path d="M5 12h14M13 6l6 6-6 6" />
	{:else if name === 'arrow-up-right'}<path d="M7 17L17 7M9 7h8v8" />
	{:else if name === 'back'}<path d="M19 12H5M11 6l-6 6 6 6" />
	{:else if name === 'check'}<path d="M5 12l5 5 9-10" />
	{:else if name === 'external'}<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
	{:else if name === 'refresh'}<path d="M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5" />
	{:else if name === 'plus'}<path d="M12 5v14M5 12h14" />
	{:else if name === 'logout'}<path d="M15 4h4v16h-4M10 8l-4 4 4 4M6 12h11" />
	{:else if name === 'send'}<path d="M4 12l16-8-6 16-3-7z" />
	{:else if name === 'x'}<path d="M6 6l12 12M18 6L6 18" />
	{/if}
</svg>
