"""Build the Teams app package (radar-teams.zip) to upload in Teams admin center.

    python teams/make_package.py --bot-app-id <guid> --origin https://portfolio.cityholdings.com.mm

Needs Pillow only to redraw the icons (they are committed already).
"""

import argparse
import json
import re
import zipfile
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).parent


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bot-app-id", required=True)
    p.add_argument("--origin", required=True, help="The web app's address, https://…")
    p.add_argument("--out", type=Path, default=HERE / "radar-teams.zip")
    a = p.parse_args()
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", a.bot_app_id):
        raise SystemExit("--bot-app-id must be the bot app registration's client ID (a GUID)")
    origin = a.origin.rstrip("/")
    if urlparse(origin).scheme != "https":
        raise SystemExit("--origin must start with https://")
    text = (HERE / "manifest.template.json").read_text()
    text = text.replace("{{BOT_APP_ID}}", a.bot_app_id).replace("{{WEB_ORIGIN}}", origin)
    text = text.replace("{{WEB_HOST}}", urlparse(origin).hostname or "")
    json.loads(text)  # still valid JSON
    with zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", text)
        z.write(HERE / "color.png", "color.png")
        z.write(HERE / "outline.png", "outline.png")
    print(f"Wrote {a.out}. Upload it in Teams admin center → Manage apps → Upload.")


if __name__ == "__main__":
    main()
