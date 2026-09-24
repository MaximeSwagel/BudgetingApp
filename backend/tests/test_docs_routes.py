import pytest


@pytest.mark.asyncio
async def test_openapi_schema_served_under_api_prefix(client):
    resp = await client.get("/api/openapi.json")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")

    body = resp.json()
    assert "openapi" in body
    assert body["info"]["title"] == "BudgetingApp API"


@pytest.mark.asyncio
async def test_swagger_ui_served_under_api_prefix(client):
    resp = await client.get("/api/docs")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "swagger-ui" in resp.text


@pytest.mark.asyncio
async def test_swagger_ui_fetches_schema_from_api_prefixed_path(client):
    resp = await client.get("/api/docs")
    assert resp.status_code == 200
    assert "/api/openapi.json" in resp.text


@pytest.mark.asyncio
async def test_redoc_served_under_api_prefix(client):
    resp = await client.get("/api/redoc")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")


@pytest.mark.asyncio
async def test_root_level_docs_paths_are_gone(client):
    docs_resp = await client.get("/docs")
    assert docs_resp.status_code == 404

    openapi_resp = await client.get("/openapi.json")
    assert openapi_resp.status_code == 404


@pytest.mark.asyncio
async def test_health_route_unaffected(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
