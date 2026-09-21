from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.agent.fake import ScriptedModelClient
from app.main import create_app
from app.settings import Settings


def make_client(settings: Settings, engine: Engine) -> TestClient:
    return TestClient(
        create_app(
            settings=settings,
            engine=engine,
            model_factory=lambda: ScriptedModelClient(()),
        )
    )


def test_dashboard_and_static_assets_are_served(
    test_settings: Settings,
    db_engine: Engine,
) -> None:
    with make_client(test_settings, db_engine) as client:
        dashboard = client.get("/")
        stylesheet = client.get("/static/styles.css")
        script = client.get("/static/dashboard.js")

    assert dashboard.status_code == 200
    assert "每日推送时间" in dashboard.text
    assert 'id="subscription-form"' in dashboard.text
    assert 'id="run-button"' in dashboard.text
    assert stylesheet.status_code == 200
    assert "--green" in stylesheet.text
    assert script.status_code == 200
    assert "/api/users" in script.text


def test_detail_pages_embed_requested_identifiers(
    test_settings: Settings,
    db_engine: Engine,
) -> None:
    with make_client(test_settings, db_engine) as client:
        run_page = client.get("/runs/run-123/view")
        digest_page = client.get("/digests/digest-123/view")

    assert run_page.status_code == 200
    assert 'data-value="run-123"' in run_page.text
    assert "工具调用轨迹" in run_page.text
    assert digest_page.status_code == 200
    assert 'data-value="digest-123"' in digest_page.text
    assert "引用来源" in digest_page.text
