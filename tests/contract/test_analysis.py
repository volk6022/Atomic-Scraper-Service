import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

app = FastAPI()


@app.post("/omni-parse")
async def omni_parse():
    return {}


@app.post("/jina-extract")
async def jina_extract():
    return {}


client = TestClient(app)


def test_omni_parse_contract():
    response = client.post(
        "/omni-parse",
        headers={"X-API-Key": "default_internal_key"},
        json={"base64_image": "test"},
    )
    assert response.status_code == 200


def test_jina_extract_contract():
    response = client.post(
        "/jina-extract",
        headers={"X-API-Key": "default_internal_key"},
        json={"html": "<html></html>"},
    )
    assert response.status_code == 200
