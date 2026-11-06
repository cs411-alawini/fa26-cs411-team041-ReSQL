"""CLI commands, frontend serving, risk-model selection and error handling."""
from __future__ import annotations

import pytest

from app import create_app
from app.risk import get_risk_model
from app.risk.ml import MLRiskModel
from tests.helpers import scalar


def test_cli_create_admin_and_jobs(app, db):
    runner = app.test_cli_runner()
    result = runner.invoke(args=["create-admin", "--email", "Boss@Example.com", "--password", "password123"])
    assert result.exit_code == 0 and "admin" in result.output
    assert scalar(db, "SELECT role FROM AppUser WHERE email = 'boss@example.com'") == "admin"
    result = runner.invoke(args=["refresh-cell-counts"])
    assert result.exit_code == 0 and "CellRiskScore rows" in result.output
    assert scalar(db, "SELECT SUM(crash_count) FROM CellRiskScore") == 5      # the unknown-condition crash is excluded
    result = runner.invoke(args=["run-alerts"])
    assert result.exit_code == 0 and "checked 0 subscriptions" in result.output


def test_cli_init_db_refuses_remote_hosts(app):
    app.config["DB_HOST"] = "10.1.2.3"
    result = app.test_cli_runner().invoke(args=["init-db"])
    assert result.exit_code != 0 and "Refusing" in result.output


def test_serves_built_frontend(app, tmp_path):
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "main.js").write_text("console.log(1)")
    spa = create_app({**app.config, "FRONTEND_DIST": str(tmp_path)})
    c = spa.test_client()
    assert c.get("/").data == b"<html>app</html>"
    assert c.get("/saved-routes").data == b"<html>app</html>"          # client-side route
    assert c.get("/assets/main.js").data == b"console.log(1)"
    assert c.get("/api/nope").status_code == 404                       # the API is unaffected


def test_risk_model_selection(app):
    with app.app_context():
        assert get_risk_model().name == "stage2_view"
        app.config["RISK_MODEL"] = "ml"
        model = get_risk_model()
        assert isinstance(model, MLRiskModel) and model.is_placeholder is False
        with pytest.raises(NotImplementedError):
            model.score_cells(["401_-883"], 1)
        app.config["RISK_MODEL"] = "magic"
        with pytest.raises(RuntimeError):
            get_risk_model()


def test_database_down_returns_503(app):
    app.config["DB_PORT"] = 1          # nothing listens there
    r = app.test_client().get("/api/lookups")
    assert r.status_code == 503 and r.get_json()["error"]["code"] == "database_unavailable"
    h = app.test_client().get("/api/health")
    assert h.status_code == 503 and h.get_json()["database"] == "unavailable"


def test_method_not_allowed_is_json(client):
    r = client.delete("/api/lookups")
    assert r.status_code == 405 and "error" in r.get_json()


def test_cli_explains_an_unreachable_database(app):
    from app import create_app

    broken = create_app({**app.config, "DB_HOST": "127.0.0.1", "DB_PORT": 1, "DB_UNIX_SOCKET": None})
    result = broken.test_cli_runner().invoke(args=["create-admin", "--email", "a@b.c", "--password", "x" * 10])
    assert result.exit_code == 1
    assert "Can't reach MySQL at 127.0.0.1:1" in result.output and "Cloud SQL Auth Proxy" in result.output
    assert "Traceback" not in result.output


def test_cli_explains_wrong_credentials(app):
    from app import create_app

    broken = create_app({**app.config, "DB_PASSWORD": "definitely-wrong"})
    result = broken.test_cli_runner().invoke(args=["run-alerts"])
    assert result.exit_code == 1
    assert "rejected DB_USER/DB_PASSWORD" in result.output
