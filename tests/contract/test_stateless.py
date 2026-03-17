import pytest
from fastapi.testclient import TestClient
from src.api.auth import get_api_key

# We'll need to create the app and routers first, but let's define the tests
from fastapi import FastAPI

app = FastAPI()


# Placeholder for routers
@app.post("/scraper")
async def scraper():
    return {}


@app.post("/serper")
async def serper():
    return {}


client = TestClient(app)


def test_scraper_contract():
    response = client.post(
        "/scraper",
        headers={"X-API-Key": "default_internal_key"},
        json={"url": "https://example.com"},
    )
    assert response.status_code == 200


def test_serper_contract():
    response = client.post(
        "/serper", headers={"X-API-Key": "default_internal_key"}, json={"q": "test"}
    )
    assert response.status_code == 200
