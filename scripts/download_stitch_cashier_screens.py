"""Download Stitch HTML + screenshots for cashier (Tactile Archive) reference QA.

Populate CASHIER_SCREENS with fresh screenshot_url and html_url from Stitch export
or MCP get_screen before running.

  python scripts/download_stitch_cashier_screens.py
"""

from __future__ import annotations

import json
import pathlib
import urllib.request

# Add rows when you have current hosted URLs from Stitch.
CASHIER_SCREENS: list[dict[str, str]] = [
    # {
    #     "slug": "cashier-dashboard",
    #     "screen_id": "8357c547a5b14f7396a045ad676d9cd2",
    #     "title": "Cashier Dashboard",
    #     "screenshot_url": "https://...",
    #     "html_url": "https://...",
    # },
]

PROJECT_ID = "2327673696871788694"


def main() -> None:
    root = pathlib.Path(__file__).resolve().parents[1] / "docs" / "design" / "stitch-cashier" / "screens"
    root.mkdir(parents=True, exist_ok=True)
    if not CASHIER_SCREENS:
        print(
            "CASHIER_SCREENS is empty. Add screenshot_url and html_url from Stitch, then re-run.\n"
            f"Project: {PROJECT_ID}\n"
            "Screen IDs: see docs/design/stitch-cashier/README.md"
        )
        (root / "manifest.json").write_text("[]", encoding="utf-8")
        return

    manifest: list[dict] = []
    opener = urllib.request.build_opener()
    opener.addheaders = [("User-Agent", "ims-stitch-cashier-intake/1.0")]
    urllib.request.install_opener(opener)

    for s in CASHIER_SCREENS:
        d = root / s["slug"]
        d.mkdir(exist_ok=True)
        shot = d / "screenshot.webp"
        html = d / "screen.html"
        urllib.request.urlretrieve(s["screenshot_url"], shot)
        urllib.request.urlretrieve(s["html_url"], html)
        manifest.append(
            {
                "slug": s["slug"],
                "screen_id": s["screen_id"],
                "stitch_name": f"projects/{PROJECT_ID}/screens/{s['screen_id']}",
                "title": s["title"],
                "local_files": {
                    "screenshot": str(shot.relative_to(root)),
                    "html": str(html.relative_to(root)),
                },
            }
        )

    (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {len(manifest)} cashier screens to {root}")


if __name__ == "__main__":
    main()
