# Portfolio Radar — web app

SvelteKit + Svelte 5 + Tailwind 4, built from `design/screens/` and the tokens in
`docs/design-system.md`.

The web app has no API or database of its own. Every page loads and acts through
the City MCP Gateway as an MCP client, with the signed-in user's token
(`src/lib/server/mcp.ts`). The browser never talks to the gateway.

```bash
npm install
cp .env.example .env      # GATEWAY_URL, sign-in settings
npm run dev               # http://localhost:5173
npm run check             # types
npm run test:e2e          # browser tests against a running stack with demo data
```

| Route | Screen |
| --- | --- |
| `/` | Portfolio overview |
| `/projects`, `/projects/[code]` | Project list, project detail |
| `/radar` | Conversation with Radar |
| `/roadmap`, `/risks` | Roadmap; risks and strategy |
| `/admin` | Admin (admins only) |
| `/login`, `/auth/callback` | City SSO (Entra ID); sample users when `DEV_LOGIN=true` |
| `/export/projects.csv` | Excel/CSV export |
