import asyncio
import time
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from mu_calculator import api


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(api, "Grump", lambda: SimpleNamespace(r=[1]))
    monkeypatch.setattr(
        api,
        "calculate",
        lambda g, c: {
            "mu": 3046,
            "area_km2": 16.3116,
            "coordinates": c,
            "raw_mu": 3045.8,
        },
    )
    with TestClient(api.app, raise_server_exceptions=False) as client:
        yield client


def test_shapes(client):
    assert client.get("/health").json()["ok"]
    assert client.get("/getMU", params=[("c", "1,1")] * 3).json()["mu"] == 3046
    assert "raw_mu" not in client.post("/getMU", json={"coordinates": []}).json()
    assert "raw_mu" in client.post("/getMU?detail=1", json={"coordinates": []}).json()
    bulk = client.post(
        "/getMUbulk", json={"fields": [{"id": "a", "coordinates": []}, []]}
    ).json()
    assert bulk["count"] == 2 and bulk["results"][0]["id"] == "a"


def test_body_shapes_and_limits(client):
    for payload in [[], None, "text"]:
        assert client.post("/getMU", json=payload).status_code == 400
    assert client.post("/getMU", content="{").status_code == 400
    assert client.post("/getMUbulk", json={"fields": [[]] * 51}).status_code == 400
    assert client.post("/getMU", content=" " * 32769).status_code == 413
    assert (
        client.post("/getMU", content=iter([b" " * 20000, b" " * 20000])).status_code
        == 413
    )
    response = client.options(
        "/getMU",
        headers={
            "Origin": "https://mu.investigatexm.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.headers["access-control-allow-origin"] == "*"


def test_item_errors(client, monkeypatch):
    def calculate(g, c):
        if c is None:
            raise ValueError("invalid triangle")
        return {"mu": 1, "area_km2": 1, "coordinates": c}

    monkeypatch.setattr(api, "calculate", calculate)
    response = client.post("/getMUbulk", json={"fields": [{}, []]}).json()
    assert response["results"][0]["ok"] is False
    assert response["results"][1]["ok"] is True
    assert client.post("/getMU", json={}).status_code == 400


def test_deadlines(client, monkeypatch):
    monkeypatch.setattr(api, "TIME_BUDGET", 0.01)

    def slow(g, c):
        time.sleep(0.05)
        return {"mu": 1, "area_km2": 1, "coordinates": c}

    monkeypatch.setattr(api, "calculate", slow)
    assert client.post("/getMU", json={"coordinates": []}).status_code == 504
    response = client.post("/getMUbulk", json={"fields": [[], []]}).json()
    assert all(x["error"] == "deadline exceeded" for x in response["results"])


def test_non_json_numbers_and_deep_nesting(client):
    for body in ['{"coordinates": NaN}', '{"id": Infinity}', "[" * 30000]:
        response = client.post("/getMU", content=body)
        assert response.status_code == 400
        assert response.json()["error"] == "Malformed JSON."


def test_unexpected_error_is_generic_and_has_cors(client, monkeypatch):
    def broken(g, c):
        raise RuntimeError("/secret/path")

    monkeypatch.setattr(api, "calculate", broken)
    response = client.post(
        "/getMU",
        json={"coordinates": []},
        headers={"Origin": "https://mu.investigatexm.com"},
    )
    assert response.status_code == 500
    assert response.json()["error"] == "Calculation failed."
    assert "secret" not in response.text
    assert response.headers["access-control-allow-origin"] == "*"
