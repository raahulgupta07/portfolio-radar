<script lang="ts" module>
	export type Mood =
		| 'ready'
		| 'resting'
		| 'scanning'
		| 'thinking'
		| 'alert'
		| 'asking'
		| 'happy'
		| 'listening'
		| 'offline';
</script>

<script lang="ts">
	// Radar's face, from design/screens/RadarFace.dc.html. The mood shows what Radar is doing.
	let { mood = 'ready', size = 40 }: { mood?: Mood; size?: number } = $props();

	const mint = '#7FD69A';
	const dot = (x: number, y: number) => `M${x} ${y} l0.01 0`;
	type Face = {
		label: string;
		body: string;
		tip: string;
		ping: number;
		ew: number;
		eyeL: string;
		eyeR: string;
		mouth: string;
		brow?: string;
		cheeks: number;
		badge?: string;
		badgeBg?: string;
		badgeInk?: string;
	};
	const MOODS: Record<Mood, Face> = {
		ready: { label: 'ready', body: mint, tip: mint, ping: 0, ew: 8, eyeL: dot(38, 54), eyeR: dot(62, 54), mouth: 'M44 70 Q50 75 56 70', cheeks: 0 },
		resting: { label: 'resting', body: '#A9DDB8', tip: '#9AA59D', ping: 0, ew: 4, eyeL: 'M32 56 Q38 60 44 56', eyeR: 'M56 56 Q62 60 68 56', mouth: 'M47 71 H53', cheeks: 0, badge: 'z', badgeBg: '#FFFFFF', badgeInk: '#111111' },
		scanning: { label: 'scanning projects', body: mint, tip: mint, ping: 1, ew: 8, eyeL: dot(43, 53), eyeR: dot(67, 53), mouth: 'M45 71 Q50 73 55 71', cheeks: 0 },
		thinking: { label: 'thinking', body: mint, tip: mint, ping: 0.45, ew: 8, eyeL: dot(34, 50), eyeR: dot(58, 50), mouth: 'M46 71 H54', brow: 'M53 41 L64 38', cheeks: 0, badge: '…', badgeBg: '#FFFFFF', badgeInk: '#111111' },
		alert: { label: 'found a problem', body: mint, tip: '#D64545', ping: 1, ew: 11, eyeL: dot(38, 53), eyeR: dot(62, 53), mouth: 'M50 66 a4 4 0 1 0 0.01 0', brow: 'M31 42 L44 44 M56 44 L69 42', cheeks: 0, badge: '!', badgeBg: '#D64545', badgeInk: '#FFFFFF' },
		asking: { label: 'waiting for you', body: mint, tip: '#F2C14E', ping: 0, ew: 8, eyeL: dot(38, 51), eyeR: dot(62, 51), mouth: 'M45 71 Q50 69 55 71', brow: 'M56 40 L68 36', cheeks: 0, badge: '?', badgeBg: '#F2C14E', badgeInk: '#111111' },
		happy: { label: 'happy, all done', body: mint, tip: mint, ping: 0, ew: 4.5, eyeL: 'M32 56 Q38 47 44 56', eyeR: 'M56 56 Q62 47 68 56', mouth: 'M41 66 Q50 78 59 66', cheeks: 0.8 },
		listening: { label: 'listening', body: mint, tip: mint, ping: 1, ew: 4, eyeL: 'M32 54 Q38 59 44 54', eyeR: 'M56 54 Q62 59 68 54', mouth: 'M45 70 Q50 74 55 70', cheeks: 0.5 },
		offline: { label: 'cannot reach a source', body: '#C9D3CC', tip: '#9AA59D', ping: 0, ew: 7, eyeL: dot(38, 57), eyeR: dot(62, 57), mouth: 'M42 74 Q50 66 58 74', brow: 'M31 45 L43 49 M57 49 L69 45', cheeks: 0, badge: '!', badgeBg: '#9AA59D', badgeInk: '#FFFFFF' }
	};
	const f = $derived(MOODS[mood] ?? MOODS.ready);
</script>

<svg viewBox="0 0 100 100" width={size} height={size} role="img" aria-label={`Radar, ${f.label}`} style="display:block">
	<g opacity={f.ping} fill="none" stroke={f.tip} stroke-width="3" stroke-linecap="round">
		<path d="M38 12 A14 14 0 0 1 62 12" />
		<path d="M31 9 A22 22 0 0 1 69 9" />
	</g>
	<line x1="50" y1="26" x2="50" y2="15" stroke="#111111" stroke-width="3.5" stroke-linecap="round" />
	<circle cx="50" cy="13" r="5.5" fill={f.tip} stroke="#111111" stroke-width="2.5" />
	<rect x="11" y="25" width="78" height="68" rx="32" fill={f.body} stroke="#111111" stroke-width="3" />
	<circle cx="29" cy="68" r="6" fill="#F27E7E" opacity={f.cheeks} />
	<circle cx="71" cy="68" r="6" fill="#F27E7E" opacity={f.cheeks} />
	<path d={f.brow ?? 'M0 0'} fill="none" stroke="#111111" stroke-width="3.5" stroke-linecap="round" />
	<path d={f.eyeL} fill="none" stroke="#111111" stroke-width={f.ew} stroke-linecap="round" stroke-linejoin="round" />
	<path d={f.eyeR} fill="none" stroke="#111111" stroke-width={f.ew} stroke-linecap="round" stroke-linejoin="round" />
	<path d={f.mouth} fill="none" stroke="#111111" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round" />
	{#if f.badge}
		<circle cx="84" cy="24" r="13" fill={f.badgeBg} stroke="#111111" stroke-width="2.5" />
		<text x="84" y="29.5" text-anchor="middle" font-family="Plus Jakarta Sans, Arial, sans-serif" font-size="15" font-weight="800" fill={f.badgeInk}>{f.badge}</text>
	{/if}
</svg>
