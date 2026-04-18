"""Deprecated — use reset_demo_showcase instead.

  IMS_DEMO_RESET_OK=1 python -m app.scripts.reset_demo_showcase

To also create a bootstrap admin user:

  IMS_DEMO_RESET_OK=1 ADMIN_BOOTSTRAP_EMAIL=admin@example.com ADMIN_BOOTSTRAP_PASSWORD=secret \\
    python -m app.scripts.reset_demo_showcase
"""

raise SystemExit(
    "seed_demo.py has been merged into reset_demo_showcase.py.\n"
    "Run: IMS_DEMO_RESET_OK=1 python -m app.scripts.reset_demo_showcase\n"
    "To create a bootstrap admin, also set ADMIN_BOOTSTRAP_EMAIL and ADMIN_BOOTSTRAP_PASSWORD."
)
