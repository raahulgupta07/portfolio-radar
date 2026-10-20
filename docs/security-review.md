# Security review

19 Oct 2026 · covers the gateway, the web app, connectors, secrets, Radar's LLM use, Teams chat and the
Azure set-up. Three reviewers read the code separately; every finding below was confirmed in the code
and fixed in the same change, with a regression test where one fits
(`backend/tests/test_security.py`, `test_identity.py`, `test_teams.py`).

## Fixed

| # | Severity | Finding | Fix |
|---|---|---|---|
| 1 | High | An app admin could point a saved secret reference at an infrastructure secret (`kv://database-url`, `env://DATABASE_URL`) and send it to their own server through a test button, or overwrite it with `set_secret` | Two vaults: Admin secrets in their own vault (gateway may write it); the database URL and web secret in another, each app may read only its own secret. `env://` may name only that setting's own variable (`LLM_API_KEY`, …). Changing a tracker, LLM or SMTP address needs the secret pasted again within 15 minutes, checked on the server |
| 2 | High | A secret sent through `omni.invoke_tool` was written in plain text to the audit log | The audit row masks the inner tool's secret arguments too |
| 3 | Medium | Any app's delegated token counted as a person, so an agent with on-behalf-of rights could approve drafts | Person tokens only from the sign-in app(s) (`ENTRA_USER_APPS`, set to the web app by Bicep); production refuses person tokens if none is listed |
| 4 | Medium | Guests (B2B) got the default viewer role; the tenant ID claim was not checked | `tid` must be City's tenant; guests get only roles a group gives them |
| 5 | Medium | Any agent set up in Admin could read everyone's pending questions, post into any conversation, and forge an approver's answer on an "ask" card | `pending_questions`, `list_asks`, `post_message` are for Radar itself only; posted payloads cannot carry answer, approval or Teams fields |
| 6 | Medium | One draft with a bad send time stopped all sending | `send_at` must be a time with a time zone; a bad stored value no longer blocks the list |
| 7 | Medium | Radar's LLM could call `remember`, and memory was added to its instructions: text in a tracker could plant lasting "instructions" | The LLM's tools are read-only; memory notes go in as data with the question. The evidence line is built from the MCP calls that really ran |
| 8 | Medium | SMTP STARTTLS did not check the server certificate | Default TLS context with certificate and host checks |
| 9 | Medium | Open redirect after sign-in with `?next=/\evil.example` | Only same-site paths; backslashes and control characters refused |
| 10 | Medium | Identities could read more secrets than they need; Key Vault open to the internet | Per-secret role assignments; both vaults private (private endpoints, public access off) |
| 11 | Low | The web app took roles from an unsigned cookie (UI only; the gateway still refused) | Roles and id come from the gateway (`whoami`, cached 5 min per token); the cookie keeps only the display name. An unknown or expired token means signed out |
| 12 | Low | Teams token without a `serviceurl` claim skipped the service URL check | The claim is required and must match |
| 13 | Low | A tracker could stall the sync (huge `Retry-After`, endless paging, huge answers) | `Retry-After` capped at 60 s, at most 500 pages, 20 MB per answer |
| 14 | Low | Long tracker text could break the PDF (truncation cut through markup) | Text is cut as plain text, then escaped |
| 15 | Low | No CSP, HSTS or nosniff | CSP (scripts only from the site, no framing), HSTS on https, `X-Content-Type-Options` |
| 16 | Low | Sign-out left the City SSO session open (shared PCs) | Sign-out also ends the Entra session |
| 17 | Low | MCP result cache kept raw tokens and never shrank | Keyed by a hash of the token; old entries dropped; at most 500 |
| 18 | Low | CSV export missed tab and carriage return in the formula guard | Added |
| 19 | Low | A broken sign-in cookie gave a 500 | 400 with a clear message |
| 20 | Low | Public paths matched by prefix | Exact paths only |
| 21 | Low | Unknown tool names skipped the rate limit; no size limit on arguments | Rate limit first; arguments over 100 KB refused |
| 22 | Low | `APP_ENV` defaulted to dev, so a deployment that forgot it would honour dev tokens | Defaults to prod |
| 23 | Low | `ask_radar` and the conversation needed no role | They need `viewer` |
| 24 | Low | LLM address could be plain http | https only |
| 25 | Low | Refused tokens were not logged | Logged with path and client address |
| 26 | Low | Containers ran as root | Non-root users in both images |
| 27 | Low | Actions pinned by tag; image tag defaulted to `latest`; gateway reached over http inside Azure | Actions pinned to commit SHAs; image tag required; internal https only |
| 28 | Low (dev) | Docker Compose published the database and gateway (with dev admin token) on every network interface | Bound to 127.0.0.1 |

## Accepted, with reasons

- **Admins can still send a request to any https address they type** (LLM, webhook, tracker). That is
  their job; secrets no longer follow an address change, and every change is in the audit log.
- **The worker has the database URL.** The nightly adapter writes the synced data directly
  (`docs/architecture.md`). Next step if wanted: a database role limited to the sync tables.
- **The worker container holds all four job identities.** They separate what each job may do at the
  gateway and in the audit log; they do not protect against code running inside the worker.
- **People are keyed by their user principal name**, which Entra lets IT change. If City reuses UPNs,
  switch to the `oid` claim (the Teams link already checks `aadObjectId`).
- **Teams chat answers need no approval.** They go only to the person who asked, in a 1:1 chat, like
  the in-app chat. Digests and messages to other people still need an approver. (Decision for the
  product owner.)

- **Superadmin (added after this review).** One local account with a password, for set-up and when SSO is
  down. Off unless set. Only an scrypt hash is accepted in production. Viewer + admin, never approver.
  60-minute sessions, signed with a key derived from the hash. 5 wrong tries per address (20 in all) lock it
  for 15 minutes. Every try is audited. Keep it as break-glass, or switch it off once SSO works.

## Checked and fine

GET-only tracker client (request hook too) · no redirects followed with tokens · JQL values quoted ·
dev tokens only in dev/test · Entra: RS256, issuer, audience, expiry, signing keys from the tenant ·
unlisted apps refused · group overage fails closed · Admin cannot give agents admin or approver
roles or built-in names · agents' server limits hold through omni · approvals by people with the
approver role only · `set_secret` never returns the value · field projection only removes data ·
DNS-rebinding protection on · no `{@html}` in the web app · OIDC state and PKCE (S256) · cookies
httpOnly, SameSite=Lax, Secure on https · SvelteKit CSRF check on · Teams: Microsoft's token checked,
service URL allow-list, City tenant, 1:1 only, sender's account matched by object ID · PostgreSQL
private with TLS required · registry without admin user · deploy by OIDC, environment-scoped.
