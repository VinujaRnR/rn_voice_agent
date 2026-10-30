import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_female_voices_list():
    """Verify available female voices are listed."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/tts/voices")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert len(data["voices"]) >= 4
        assert all(v["gender"] == "Female" for v in data["voices"])


@pytest.mark.asyncio
async def test_female_tts_stream_generation():
    """Verify high-definition female voice audio is generated as audio/mpeg."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/tts", params={"text": "Hello, this is Sarah speaking in a female voice."})
        assert res.status_code == 200
        assert res.headers["content-type"] == "audio/mpeg"
        assert len(res.content) > 1000

