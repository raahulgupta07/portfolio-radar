#!/usr/bin/env python3
"""Download every OpenProject project to a CSV and a JSON file.

Read-only: it sends GET requests only and changes nothing in OpenProject.
Uses the Python standard library, so there is nothing to install.

    export OPENPROJECT_TOKEN='<your API token>'
    python3 scripts/openproject_export.py https://openproject.example.com
    python3 scripts/openproject_export.py https://openproject.example.com --with-dates

The token is read from the environment, never from the command line, and is never written to a file.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

PAGE = 200
MAX_PAGES = 200


def get(base: str, token: str, path: str, params: dict | None = None) -> dict:
    url = base.rstrip("/") + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    auth = base64.b64encode(f"apikey:{token}".encode()).decode()
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {auth}", "Accept": "application/hal+json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        hint = {401: "the token is wrong or expired", 403: "the token's user cannot see this", 404: "wrong URL or path"}.get(e.code, "")
        sys.exit(f"OpenProject answered {e.code} for {path}. {hint}")
    except urllib.error.URLError as e:
        sys.exit(f"Could not reach {base}: {e.reason}. Check the address, VPN and firewall.")


def collection(base: str, token: str, path: str, params: dict | None = None) -> list[dict]:
    out: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        data = get(base, token, path, {**(params or {}), "pageSize": PAGE, "offset": page})
        els = (data.get("_embedded") or {}).get("elements", [])
        out += els
        if not els or len(out) >= data.get("total", 0):
            break
    return out


def raw(v):
    return v.get("raw") if isinstance(v, dict) else v


def title(el: dict, link: str) -> str:
    l = (el.get("_links") or {}).get(link)
    if isinstance(l, list):
        return "; ".join(x.get("title", "") for x in l)
    return (l or {}).get("title") or ""


def href_id(el: dict, link: str) -> str:
    h = ((el.get("_links") or {}).get(link) or {}).get("href")
    return h.rstrip("/").rsplit("/", 1)[-1] if h else ""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base_url", help="for example https://openproject.example.com")
    ap.add_argument("--out", default=f"openproject-projects-{date.today()}", help="file name without extension")
    ap.add_argument("--with-dates", action="store_true", help="also read the earliest start and latest due date of each project's work packages (slower)")
    a = ap.parse_args()
    token = os.environ.get("OPENPROJECT_TOKEN", "")
    if not token:
        sys.exit("Set OPENPROJECT_TOKEN first:  export OPENPROJECT_TOKEN='...'")

    # Both active and archived projects, so nothing is missed.
    projects: dict[int, dict] = {}
    for flag in ("t", "f"):
        f = json.dumps([{"active": {"operator": "=", "values": [flag]}}])
        for p in collection(a.base_url, token, "/api/v3/projects", {"filters": f}):
            projects[p["id"]] = p
    print(f"Found {len(projects)} projects.")

    # Labels for the custom fields (customField12 -> "Project owner").
    schema = get(a.base_url, token, "/api/v3/projects/schema")
    labels = {k: v.get("name", k) for k, v in schema.items() if k.startswith("customField") and isinstance(v, dict)}

    rows = []
    for i, p in enumerate(sorted(projects.values(), key=lambda x: x["id"]), 1):
        row = {
            "id": p["id"], "identifier": p.get("identifier"), "name": p.get("name"), "active": p.get("active"),
            "public": p.get("public"), "parent_id": href_id(p, "parent"), "parent_name": title(p, "parent"),
            "status": title(p, "status"), "status_explanation": raw(p.get("statusExplanation")) or "",
            "description": (raw(p.get("description")) or "").replace("\r", " ").replace("\n", " "),
            "created_at": p.get("createdAt"), "updated_at": p.get("updatedAt"),
        }
        for key in sorted(k for k in p if k.startswith("customField")):
            row[labels.get(key, key)] = raw(p[key])
        for key in sorted(k for k in (p.get("_links") or {}) if k.startswith("customField")):
            row[labels.get(key, key)] = title(p, key)
        if a.with_dates:
            every = json.dumps([{"status": {"operator": "*", "values": []}}])
            path = f"/api/v3/projects/{p['id']}/work_packages"
            first = get(a.base_url, token, path, {"filters": every, "pageSize": 1, "sortBy": json.dumps([["startDate", "asc"]])})
            last = get(a.base_url, token, path, {"filters": every, "pageSize": 1, "sortBy": json.dumps([["dueDate", "desc"]])})
            f_el = (first.get("_embedded") or {}).get("elements", [])
            l_el = (last.get("_embedded") or {}).get("elements", [])
            row["first_start"] = (f_el[0].get("startDate") or f_el[0].get("date") or "") if f_el else ""
            row["last_due"] = (l_el[0].get("dueDate") or l_el[0].get("date") or "") if l_el else ""
            row["work_packages"] = first.get("total", 0)
            print(f"  {i}/{len(projects)}", end="\r")
        rows.append(row)

    columns = list(dict.fromkeys(k for r in rows for k in r))
    with open(a.out + ".csv", "w", newline="", encoding="utf-8-sig") as f:  # BOM so Excel reads UTF-8
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)
    with open(a.out + ".json", "w", encoding="utf-8") as f:
        json.dump(list(projects.values()), f, ensure_ascii=False, indent=1)
    print(f"\nWrote {a.out}.csv ({len(rows)} rows, {len(columns)} columns) and {a.out}.json (the full answer).")


if __name__ == "__main__":
    main()
