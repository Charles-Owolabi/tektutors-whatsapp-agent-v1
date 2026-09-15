import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

client = TestClient(app)

def test_webhook_verification_success():
    response = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": settings.WHATSAPP_VERIFY_TOKEN,
            "hub.challenge": "123456789"
        }
    )
    assert response.status_code == 200
    assert response.text == "123456789"

def test_webhook_verification_failure():
    response = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_token",
            "hub.challenge": "123456789"
        }
    )
    assert response.status_code == 403

def test_simulator_chat_endpoint():
    payload = {
        "phone": "2348099887766",
        "message": "Hi, what courses are available?"
    }
    response = client.post("/api/simulator/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["phone"] == "2348099887766"
    assert "ai_response" in data
