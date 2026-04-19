"""One-time backfill: copy currency fields from api.tenants into platform_tenants.

Usage:
    PLATFORM_DATABASE_URL=... API_DATABASE_URL=... python -m app.scripts.backfill_tenant_currency
"""
from __future__ import annotations

import logging
import os
import sys

from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> int:
    platform_url = os.environ.get("PLATFORM_DATABASE_URL")
    api_url = os.environ.get("API_DATABASE_URL")
    if not platform_url or not api_url:
        logger.error("Both PLATFORM_DATABASE_URL and API_DATABASE_URL must be set")
        return 1

    platform_engine = create_engine(platform_url)
    api_engine = create_engine(api_url)

    with api_engine.connect() as api_conn:
        api_rows = api_conn.execute(text(
            "SELECT slug, default_currency_code, currency_exponent, currency_symbol_override "
            "FROM tenants"
        )).fetchall()
    logger.info("Found %d api.tenants rows", len(api_rows))

    api_by_slug = {r[0]: r for r in api_rows}

    with platform_engine.begin() as plat_conn:
        plat_rows = plat_conn.execute(text(
            "SELECT id, slug FROM platform_tenants"
        )).fetchall()
        logger.info("Found %d platform_tenants rows", len(plat_rows))

        updated = 0
        skipped = 0
        for (plat_id, slug) in plat_rows:
            api_row = api_by_slug.get(slug)
            if api_row is None:
                logger.warning("platform_tenant slug=%s has no matching api.tenants row; skipping", slug)
                skipped += 1
                continue
            plat_conn.execute(text(
                """
                UPDATE platform_tenants
                SET default_currency_code = :code,
                    currency_exponent = :exp,
                    currency_symbol_override = :sym
                WHERE id = :id
                """
            ), {
                "code": api_row[1],
                "exp": api_row[2],
                "sym": api_row[3],
                "id": plat_id,
            })
            updated += 1

    logger.info("Backfill complete: updated=%d, skipped=%d", updated, skipped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
