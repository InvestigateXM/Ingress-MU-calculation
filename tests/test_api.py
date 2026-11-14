import asyncio
import time
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from mu_calculator import api


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(api, "ensure_tables", lambda folder: [])
    monkeypatch.setattr(api, "Grump", lambda: SimpleNamespace(r=[1], folder="unused"))
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
    assert client.get("/health").json()["table_max_level"] == 6
    assert client.get("/").json()["table_max_level"] == 6
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


def test_preparation_failure_prevents_startup(monkeypatch):
    monkeypatch.setattr(api, 'Grump', lambda: SimpleNamespace(r=[1], folder='unused'))
    def failed(folder):
        raise RuntimeError('table preparation failed')
    monkeypatch.setattr(api, 'ensure_tables', failed)
    with pytest.raises(RuntimeError, match='table preparation failed'):
        with TestClient(api.app):
            pytest.fail('API served before preparation')
import pytest

@pytest.mark.parametrize('value, enabled', [('1', True), ('0', False), ('true', True), ('false', False), ('TRUE', True), ('FALSE', False)])
def test_detail_query(client, value, enabled):
    for endpoint, body in [('/getMU', {'coordinates': []}), ('/getMUbulk', {'fields': [[]]})]:
        response = client.post(endpoint, params={'detail': value}, json=dict(body, detail=not enabled))
        assert response.status_code == 200
        result = response.json()
        if endpoint == '/getMUbulk':
            result = result['results'][0]
        assert ('raw_mu' in result) == enabled
    response = client.get('/getMU', params={'detail': value})
    assert ('raw_mu' in response.json()) == enabled

@pytest.mark.parametrize('value, enabled', [(True, True), (False, False), (1, True), (0, False), ('1', True), ('0', False), ('true', True), ('false', False), ('TRUE', True), (None, False)])
def test_detail_json(client, value, enabled):
    response = client.post('/getMU', json={'coordinates': [], 'detail': value})
    assert response.status_code == 200
    assert ('raw_mu' in response.json()) == enabled

def test_invalid_detail(client):
    for response in [client.get('/getMU?detail=yes'), client.post('/getMU', json={'detail': 'yes'}), client.post('/getMUbulk?detail=yes', json={'fields': [[]]})]:
        assert response.status_code == 400
        assert response.json()['error'] == 'detail must be true, false, 1 or 0.'
