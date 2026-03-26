"""One-off helper: download Stitch HTML + screenshots into docs/stitch/admin-web/."""

from __future__ import annotations

import json
import pathlib
import urllib.request

SCREENS: list[dict[str, str]] = [
    {
        "slug": "executive-overview",
        "screen_id": "c41290bb6b3c49daaf584818fbec282f",
        "title": "Executive Overview",
        "screenshot_url": "https://lh3.googleusercontent.com/aida/ADBb0uhkAPUhc4x1xMPWfjKleHNSlXSH-PGcXmMdIhU1evZeKv5ktxixCcp1NlRRr9Gvo-RwVViPpvpH6-VhK-Dxh2xXjrHkJr6Fk3bcTYzc-Wrqvqslw_zGLrMBCW4kD8TcYPL7pJRLiqh-iILIAhIWlJia7WU3BHzilYXtHYAigdtfHGVfesimDnSOFJKb0dtleVHbcahygHD_4xdQPuP7m2M_3Hhz9lvkMhlT1M21ie7C7WEU8LtO8LhopmY",
        "html_url": "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ7Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpaCiVodG1sXzg3NzEwNmRiZWM3OTQzOWFiNTY5ZTdhNTQ4MDA1NDkyEgsSBxCh1LmbkB4YAZIBIwoKcHJvamVjdF9pZBIVQhMyMzI3NjczNjk2ODcxNzg4Njk0&filename=&opi=89354086",
    },
    {
        "slug": "order-audit-ledger",
        "screen_id": "bd729c55e4944488bb465b9cc44e19ee",
        "title": "Order Audit Ledger (Synced)",
        "screenshot_url": "https://lh3.googleusercontent.com/aida/ADBb0uj2DaZ0EnUtwIwjZ9HLuIJsCgsmiG8hQgyTO9WvvPENwBweuVvbYlyTTeWDDTcP7mOCw914w6xPYD_q5uhzKfUBmMFOx9KWfBaOOXjJWdKUU60iWHVT053Wn-kBMT3mXPVg4haTO3ILvtqBMn8299_vbNjx91EH8nOeIiM9qL5NH5l6PH7yJaE3E-RPq3d18utqe2-LsH6MUON6sx6tKjHsjkoTe8n4FKRXzGogALn5JBJK5XpNV-xxl3M",
        "html_url": "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ7Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpaCiVodG1sXzI1MWJlY2YyMzIyOTRhNjNhNWExYjExYzVlYWNjNDUxEgsSBxCh1LmbkB4YAZIBIwoKcHJvamVjdF9pZBIVQhMyMzI3NjczNjk2ODcxNzg4Njk0&filename=&opi=89354086",
    },
    {
        "slug": "supplier-hub",
        "screen_id": "46aa7e73c37a46998ef3899377ae7aaf",
        "title": "Supplier Hub (Synced)",
        "screenshot_url": "https://lh3.googleusercontent.com/aida/ADBb0uhNhXPw-wff7qHvjswTrfo3-6fKVQevU0s9-dpQP5dNoXR3NnqbFje8DSvc0q-YosaiEjrV1rNPKZ54x0zridPPNVBKQc03tcioq8NSCGpzsSwFKPhCF8hfi4Jd_IScn7jNeATUwhz4DEvAksNCRHwK6balD2as6kSpDVGAVbjyWmIcHRRtQuwgEiTmzxoAHG7Ju-ZBbq8Idrn2jf1ky6PGOF-fy01am0b2IFVTXDhyhNJoSab_cp5QMTw",
        "html_url": "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ7Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpaCiVodG1sXzk4OWZmZjYxZGM2ZDQ4N2RhYWRjNDIzZWQ0OWIzZDVkEgsSBxCh1LmbkB4YAZIBIwoKcHJvamVjdF9pZBIVQhMyMzI3NjczNjk2ODcxNzg4Njk0&filename=&opi=89354086",
    },
    {
        "slug": "analytics-insights",
        "screen_id": "e0ae24d061944017a964a1a4fbc82817",
        "title": "Analytics & Insights (Synced)",
        "screenshot_url": "https://lh3.googleusercontent.com/aida/ADBb0uivGDYlnEOvuPqXSc2EFMW-dsAg5gRO-dhRsaiClWA4Fd807HMdNTV_-yEP_wZe7ibeTDIKJfVeHzYNghrc8RZj8W1pbmZUtU3YuHBhj1OFJMis0q8x8M7cfIXB1KLI2bqlLc3CEqwFQWNIYf0L1tagzX8XKuzJ1EMWmNp65T5aVdC8EnM80HtH2uxNi3Y6HP0hgicHv96XCZTgOElumO7MXVKLmB7TGDU1YdhPFKDOcoou5HWHhmFyWA",
        "html_url": "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ7Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpaCiVodG1sX2MwOTk0MTBiYzc3NzQ2NDU4ZDY3MzdjOTU5ODc1YjlhEgsSBxCh1LmbkB4YAZIBIwoKcHJvamVjdF9pZBIVQhMyMzI3NjczNjk2ODcxNzg4Njk0&filename=&opi=89354086",
    },
    {
        "slug": "new-entry-hub",
        "screen_id": "376fb70716e64c8c9de7af90b98df7cc",
        "title": "New Entry Hub (Synced)",
        "screenshot_url": "https://lh3.googleusercontent.com/aida/ADBb0uhFnB4RcZtSD5a7ZbIHk-hEC7ISKUPdYpWM1JNrVh-2TcOALrnwxSY-C707cGL5oycAUoxGSUqG74jXIgPyporaPZUmZPILjrWACfKRp3DtnJsCuZurOWVhbPvYbNkjXHx2DY1eBIuVzJOTbzk50WpxecjRu9cXDkAyMoe2sfXDES-DtAzK2D_MOfZfqbKxnVIfMPdpRogf6Z2ZbOsMCt5fKSwtqr6duFXdHQa00AjnRc0C5CMaL483Mw",
        "html_url": "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ7Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpaCiVodG1sX2IxNDU5ZGRmOTA1ZTQzODBhZGExMWQxOTBhNDRjZDFhEgsSBxCh1LmbkB4YAZIBIwoKcHJvamVjdF9pZBIVQhMyMzI3NjczNjk2ODcxNzg4Njk0&filename=&opi=89354086",
    },
    {
        "slug": "inventory-ledger",
        "screen_id": "f98f213ca4bf42ba888b56a17d6ea2cf",
        "title": "Inventory Ledger (Synced)",
        "screenshot_url": "https://lh3.googleusercontent.com/aida/ADBb0ui0x9sa2or6vdjXqX9PirJQ-FS_OdF5cVWt5-pZZzV-44SxV7wYx26rYuX1I2IQlO45ZLDhavyFmZGJyYbiEukf73SVMbmkgEjcSUEl-aaP6O2Eurj3pg32EoqRfSIoCAAcxhknyVZP7N7TsonHdui7Li0bG4DCa5YSbNk6LpcAEKTjxAlek9Y3ctbKIxYKS9sSIgoNLHRpqQZmmlHDmBnBzlgMD8rxp1xLc0UAfoIxMp_HrP2PRtrEZ34",
        "html_url": "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ7Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpaCiVodG1sX2Y1OTJjYTllYzcxYjQ4MWI5ZWVhMjRlYzRlNDE3OGVkEgsSBxCh1LmbkB4YAZIBIwoKcHJvamVjdF9pZBIVQhMyMzI3NjczNjk2ODcxNzg4Njk0&filename=&opi=89354086",
    },
    {
        "slug": "staff-permissions",
        "screen_id": "4a460c16c35841d59faef891a5a12127",
        "title": "Staff & Permissions (Synced)",
        "screenshot_url": "https://lh3.googleusercontent.com/aida/ADBb0uhB2PejJ27rADc2zUebJi2ttbJMFaK22g8f70ijvWQQQzvaaE9tg_ijSVmZQFm87tqh8z1G7kXoJMLGVbqOwtJOKdFHj09Boeke-_6VXa7ZUAYegdRq60xyIh32iag8hmjnMc7426q6I3Ak88DNMp-2iAvCOMnBJIWbvVSomtsLkK0OqtPyAzlW6V-37sjgRzO2ta2hNXZAkDSNiDc5n2CsXeSClm4C4Vyt_Wvyem8AxWRmT8LibYap1mo",
        "html_url": "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ7Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpaCiVodG1sXzM4YjhlNTU4ZGIzYTRjM2ZiOGJkNTk5NTcxMzZmYWIxEgsSBxCh1LmbkB4YAZIBIwoKcHJvamVjdF9pZBIVQhMyMzI3NjczNjk2ODcxNzg4Njk0&filename=&opi=89354086",
    },
]

PROJECT_ID = "2327673696871788694"


def main() -> None:
    root = pathlib.Path(__file__).resolve().parents[1] / "docs" / "stitch" / "admin-web"
    root.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    opener = urllib.request.build_opener()
    opener.addheaders = [("User-Agent", "ims-stitch-intake/1.0")]
    urllib.request.install_opener(opener)

    for s in SCREENS:
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
    print(f"Wrote {len(manifest)} screens to {root}")


if __name__ == "__main__":
    main()
