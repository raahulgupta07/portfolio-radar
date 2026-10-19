# Recorded tracker responses

Each file lists GET requests and the JSON the tracker answered. Tests replay
them with `httpx.MockTransport`, so connector tests need no network.

A request matches an entry when the path is equal and every listed param is
found inside the request's param (substring). The first match wins, so put
specific entries before general ones.

The current files follow the shapes in the public API docs (JIRA Cloud REST v3,
JIRA Data Center REST v2, Agile 1.0, OpenProject API v3). When City's read-only
tokens arrive, record real answers with `python -m app.connectors.record` and
replace these files (remove names and emails first).
