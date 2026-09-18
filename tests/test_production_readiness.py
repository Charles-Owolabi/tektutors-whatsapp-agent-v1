import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.config import settings
from app.agent import get_cached_system_config, invalidate_cached_system_config, SUPPORTED_GROQ_MODELS


@pytest.mark.asyncio
async def test_health_endpoint():
    """Verify /health returns HTTP 200 with required production health indicators."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "uptime_seconds" in data
        assert "version" in data
        assert data["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_readiness_endpoint():
    """Verify /ready verifies database connectivity and Groq configuration."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("ready", "degraded")
        assert "database" in data
        assert data["database"] == "ok"
        assert "groq_engine" in data
        assert "model" in data


@pytest.mark.asyncio
async def test_security_headers_present():
    """Verify production security headers are attached to HTTP responses."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "SAMEORIGIN"
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"
        assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


@pytest.mark.asyncio
async def test_groq_model_configuration_and_cascade():
    """Verify primary model is llama-3.3-70b-versatile and cascade includes fallback models."""
    assert SUPPORTED_GROQ_MODELS[0] == "openai/gpt-oss-120b"
    assert "groq/compound-mini" in SUPPORTED_GROQ_MODELS
    assert "allam-2-7b" in SUPPORTED_GROQ_MODELS


@pytest.mark.asyncio
async def test_system_config_in_memory_caching():
    """Verify system config is cached in-memory and can be invalidated."""
    invalidate_cached_system_config()
    cfg1 = await get_cached_system_config()
    assert cfg1 is not None
    assert "agent_name" in cfg1
    assert "system_prompt" in cfg1

    # Second call should return the exact cached object without DB hit
    cfg2 = await get_cached_system_config()
    assert cfg1 is cfg2

    # Invalidate cache
    invalidate_cached_system_config()
    cfg3 = await get_cached_system_config()
    assert cfg3 is not None
    assert "agent_name" in cfg3
