import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI, Depends
from src.api.auth import get_api_key

app = FastAPI()


@app.get("/test-auth")
async def protected_route(api_key: str = Depends(get_api_key)):
    return {"message": "success"}


client = TestClient(app)


def test_auth_success():
    response = client.get("/test-auth", headers={"X-API-Key": "default_internal_key"})
    assert response.status_code == 200


def test_auth_fail():
    response = client.get("/test-auth", headers={"X-API-Key": "wrong_key"})
    assert response.status_code == 403
