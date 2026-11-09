"""Traffic Safety Risk Analyzer API (Flask application factory)."""
from __future__ import annotations

import functools
import logging
import os
from datetime import date, datetime
from decimal import Decimal

import click
from dotenv import load_dotenv
from flask import Flask, send_from_directory
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS

from .config import Config
from .db import close_db, execute, transaction
from .errors import ApiError, register_error_handlers


class JSONProvider(DefaultJSONProvider):
    sort_keys = False

    @staticmethod
    def default(o):
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, datetime):
            if o.tzinfo is None:  # DATETIME columns hold UTC (see db.py)
                return o.isoformat(timespec="seconds") + "Z"
            return o.isoformat(timespec="seconds")
        if isinstance(o, date):
            return o.isoformat()
        return DefaultJSONProvider.default(o)


def create_app(overrides: dict | None = None) -> Flask:
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
    app = Flask(__name__, static_folder=None)
    app.json_provider_class = JSONProvider
    app.json = JSONProvider(app)
    app.config.update(Config().to_flask())
    if overrides:
        app.config.update(overrides)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if app.config["JWT_SECRET"] == "dev-only-change-me" and not app.config.get("TESTING"):
        app.logger.warning("JWT_SECRET is not set; using the development default. Set it before deploying.")

    CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})
    register_error_handlers(app)
    app.teardown_appcontext(close_db)

    from .api import crashes, locations, meta, reports, routes, subscriptions, users
    for module in (meta, users, crashes, locations, reports, routes, subscriptions):
        app.register_blueprint(module.bp, url_prefix="/api")

    _serve_frontend(app)
    _register_commands(app)
    return app


def _serve_frontend(app: Flask) -> None:
    dist = app.config.get("FRONTEND_DIST")
    if not dist:
        return
    dist = os.path.abspath(dist)

    @app.get("/", defaults={"path": ""})
    @app.get("/<path:path>")
    def spa(path: str):
        if path == "api" or path.startswith("api/"):
            raise ApiError(404, "No such API endpoint")
        full = os.path.join(dist, path)
        if path and os.path.isfile(full):
            return send_from_directory(dist, path)
        return send_from_directory(dist, "index.html")


def _db_errors(app: Flask):
    """Turn a database connection failure in a CLI command into a short message with the likely fix."""
    def decorate(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            import pymysql
            try:
                return fn(*args, **kwargs)
            except pymysql.err.OperationalError as exc:
                cfg = app.config
                where = cfg.get("DB_UNIX_SOCKET") or f"{cfg['DB_HOST']}:{cfg['DB_PORT']}"
                code = exc.args[0] if exc.args else None
                if code == 2003:
                    hint = (f"Can't reach MySQL at {where}. For Cloud SQL, start the Cloud SQL Auth Proxy in another "
                            "window first and check that its --port matches DB_PORT in backend/.env.")
                elif code == 1045:
                    hint = f"MySQL at {where} rejected DB_USER/DB_PASSWORD from backend/.env."
                elif code == 1049:
                    hint = f"MySQL at {where} has no database named {cfg['DB_NAME']!r} (DB_NAME in backend/.env)."
                else:
                    hint = f"Database error from {where}: {exc}"
                raise click.ClickException(hint) from None
        return wrapper
    return decorate


def _register_commands(app: Flask) -> None:
    db_errors = _db_errors(app)

    @app.cli.command("create-admin")
    @click.option("--email", required=True)
    @click.option("--password", required=True)
    @click.option("--name", default="Admin")
    @db_errors
    def create_admin(email: str, password: str, name: str):
        """Create an admin account, or promote an existing account to admin."""
        from .auth import hash_password
        with transaction():
            execute("INSERT INTO AppUser (email, password_hash, display_name, role) VALUES (%s, %s, %s, 'admin') "
                    "ON DUPLICATE KEY UPDATE role = 'admin'", (email.lower(), hash_password(password), name))
        click.echo(f"{email} is an admin")

    @app.cli.command("init-db")
    @click.option("--drop", is_flag=True, help="Drop existing tables first")
    @click.option("--demo", is_flag=True, help="Also load the Illinois demo data (database/demo_seed.sql)")
    @click.option("--force", is_flag=True, help="Allow a non-local DB_HOST")
    @db_errors
    def init_db(drop: bool, demo: bool, force: bool):
        """Create the schema in a local database from ../database/*.sql."""
        from .db import get_db
        from .dbsetup import DATABASE_DIR, apply_schema, drop_all, run_sql_file
        if app.config["DB_HOST"] not in ("127.0.0.1", "localhost") and not force:
            raise click.ClickException("Refusing to touch a non-local database (this is not for Cloud SQL). "
                                       "Use --force if you really mean it.")
        conn = get_db()
        if drop:
            drop_all(conn)
        apply_schema(conn)
        click.echo(f"schema created in {app.config['DB_NAME']}")
        if demo:
            from .jobs.cell_counts import refresh
            run_sql_file(conn, os.path.join(DATABASE_DIR, "demo_seed.sql"))
            click.echo(f"demo data loaded; {refresh()} CellRiskScore rows")

    @app.cli.command("refresh-cell-counts")
    @db_errors
    def refresh_cell_counts():
        """Recompute CellRiskScore crash and fatality counts from Crash (the scoring job)."""
        from .jobs.cell_counts import refresh
        click.echo(f"{refresh()} CellRiskScore rows written")

    @app.cli.command("run-alerts")
    @db_errors
    def run_alerts():
        """Run the subscription alert job once (schedule this, e.g. hourly)."""
        from .jobs.alerts import run_alert_job
        result = run_alert_job()
        click.echo(f"checked {result['checked']} subscriptions, created {result['alerts_created']} alerts")
