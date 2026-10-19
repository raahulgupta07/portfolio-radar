# Design system

Style reference: the Dribbble shot "Salesforce CRM – Leads Management Software" (RonDesignLab),
adapted with our own brand — no Salesforce name or logo. Light, calm, rounded, black accents,
pastel colour per source.

## Tokens

```css
:root {
  /* ground and surfaces */
  --bg: #E7F0EA;          /* pale mint page background */
  --surface: #FFFFFF;     /* cards, menu, panels */
  --surface-2: #F1F5F2;   /* inputs, chips, quiet tiles */
  --surface-3: #F4F7F5;   /* list rows, Radar bubbles */
  --line: #EEF2EF;        /* row dividers */
  --line-strong: #DDE5DF; /* outlined buttons */

  /* text */
  --ink: #111111;
  --ink-2: #2A302C;
  --ink-muted: #5B635D;   /* 4.5:1 on white */
  --ink-soft: #3E4640;

  /* accents */
  --black: #111111;       /* active tab, primary buttons, approval cards */
  --black-2: #161616;     /* dark cards (Radar strip, rules panel) */
  --mint: #7FD69A;        /* Radar's colour */

  /* source pastels (also used for health tiles) */
  --jira: #CFE3FB;        --jira-bar: #7FB2EC;
  --openproject: #FBE6A9; --openproject-bar: #EAC45A;
  --multica: #F8CDD0;     --multica-bar: #EE9AA0;

  /* health */
  --on-track-bg: #E2F2E7; --on-track: #2E8B57;
  --at-risk-bg: #FBE6A9;  --at-risk: #B98300;
  --off-track-bg: #F8CDD0;--off-track: #C23B3B;
  --done-bg: #CFE3FB;     --done: #111111;
  --alert-dot: #D64545;

  /* shape */
  --r-card: 30px;  --r-tile: 22px;  --r-chip: 999px;  --r-input: 999px;
  --gap: 16px;
}
```

Health is never shown by colour alone: always a dot + label ("On track", "At risk", "Off track", "Done").

## Type

- Font: **Plus Jakarta Sans** (Google Fonts), weights 400–800.
- Page title 48 px / 700 / -0.035em. Card title 18 px / 700. Body 14 px. Small 12–13 px.
- Big numbers 26–40 px / 600–700.

## Components

| Component | Spec |
| --- | --- |
| Floating menu (desktop, iPad) | White pill, 64 px wide, radius 36, shadow `0 8px 24px rgba(17,17,17,.06)`, centred vertically on the left. 44 px round buttons with pastel backgrounds; active = black with white icon. Radar on top (face, red count badge), then Overview, Projects, Roadmap, Risks, Admin; then search, alerts, progress ring, avatar |
| Phone tab bar | Floating white pill at bottom, 68 px high: Radar, Overview, Projects, Alerts, avatar |
| Title row | Big title + count in an outlined circle; round icon buttons on the right |
| Card | White, radius 30, padding 22–26, no border |
| Pastel tile | Source or health colour, radius 22–30 |
| Chip / pill | Radius 999, 12–13 px bold; filter groups sit in a grey pill track, active = black |
| Dot row | 7–8 px black dot + label + small grey count pill |
| Bar chart | Thin rounded bars in source pastel colours; current value black |
| Black card | Radar strip, approval cards, prefix list, rules |
| Buttons | Primary: black pill. Secondary: white or grey pill. Min height 44 px |
| Radar bubble | Grey `#F1F5F2`, radius 22 with a 6 px corner; user bubble black |
| "Radar asks" card | Yellow `#FBE6A9`, label "RADAR ASKS", two buttons |

## Layout

- Desktop pages are fluid (max-width 1440), cards in auto-fit grids.
- Radar screen: menu · conversation (flex) · Radar panel (320–360 px).
- iPad landscape 1194×834: same, narrower panel.
- Phone 390×844: stacked cards, floating tab bar, message box above the tab bar.

## Screens

The HTML in `design/screens/` is the reference. Each file is a design component with inline styles
and a small `renderVals()` script for sample data and interactions. Use it for layout, spacing,
colours and copy; rebuild it as real React components.
