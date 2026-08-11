import httpx
import pytest

from gaffertalk_api.main import app


@pytest.mark.anyio
async def test_health_returns_service_status() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "gaffertalk-api",
        "environment": "development",
    }
