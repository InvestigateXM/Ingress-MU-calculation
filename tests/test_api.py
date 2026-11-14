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


def request_records(caplog):
    import json
    return [json.loads(r.message) for r in caplog.records
            if r.name == 'uvicorn.error' and r.message.startswith('{')]


def test_private_request_logs(client, monkeypatch, caplog):
    import logging
    import json
    caplog.set_level(logging.INFO, logger='uvicorn.error')
    points = ['47.876543,8.765432', '47.654321,8.543219', '47.432198,8.321987']
    client.get('/getMU', params=[('c', p) for p in points])
    client.post('/getMU', json={'coordinates': points, 'note': 'private-body-marker'})
    client.post('/getMUbulk', json={'fields': [points, points]})

    def invalid(g, c):
        raise ValueError('private-body-marker ' + str(c))
    monkeypatch.setattr(api, 'calculate', invalid)
    client.get('/getMU', params=[('c', p) for p in points])
    client.post('/getMU', content='{private-body-marker')
    client.post('/getMU', content='x' * (api.BODY_LIMIT + 1))
    client.get('/private-body-marker?c=' + points[0])
    client.post('/getMUbulk', json={'fields': [points]})

    def broken(g, c):
        try:
            raise ValueError('private-body-marker')
        except ValueError:
            raise RuntimeError(str(c))
    monkeypatch.setattr(api, 'calculate', broken)
    assert client.post('/getMU', json={'coordinates': points}).status_code == 500
    records = request_records(caplog)
    assert len(records) == 9
    assert records[2]['fields'] == 2
    assert [r.get('error') for r in records[3:]] == [
        'invalid_coordinates', 'malformed_json', 'too_large', 'not_found',
        'invalid_coordinates', 'internal']
    assert 'Traceback (frame locations only)' in caplog.text
    for secret in points + [v for p in points for v in p.split(',')] + [
        '3046', '3045.8', '16.3116', 'private-body-marker']:
        assert secret not in caplog.text
    assert all('?' not in r['path'] for r in records)


@pytest.mark.parametrize('trusted', [False, True])
def test_request_headers(client, monkeypatch, caplog, trusted):
    import logging
    caplog.set_level(logging.INFO, logger='uvicorn.error')
    monkeypatch.setattr(api, 'TRUSTED_PROXY_HEADERS', trusted)
    cases = [
        ({'CF-Connecting-IP': '203.0.113.8', 'X-Forwarded-For': '198.51.100.9'}, '203.0.113.8'),
        ({'X-Forwarded-For': '198.51.100.9, 192.0.2.4'}, '198.51.100.9'),
        ({'CF-Connecting-IP': 'bad\r\nforged', 'X-Forwarded-For': '198.51.100.9'}, 'testclient'),
        ({'CF-Connecting-IP': '2001:db8::1'}, '2001:db8::1'),
        ({'X-Forwarded-For': 'bad\x01value'}, 'testclient'),
    ]
    for headers, expected in cases:
        client.get('/health', headers=dict(headers, **{'User-Agent': 'agent\r\n\x00\x7f' + 'x' * 5000}))
        record = request_records(caplog)[-1]
        assert record['client'] == (expected if trusted else 'testclient')
        assert record['user_agent'] == 'agent' + 'x' * 251
    assert len(request_records(caplog)) == len(cases)


def test_server_logging_configuration(monkeypatch):
    import sys
    import uvicorn
    from mu_calculator import __main__
    monkeypatch.setattr(sys, 'argv', ['mu_calculator', 'serve'])
    monkeypatch.setattr(__main__, 'ensure_data', lambda folder: None)
    monkeypatch.setenv('GRUMP_DIR', 'unused')
    calls = []
    monkeypatch.setattr(uvicorn, 'run', lambda *a, **kw: calls.append((a, kw)))
    __main__.main()
    assert calls[0][1]['access_log'] is False
    assert calls[0][1]['proxy_headers'] is False
    assert calls[0][1]['log_config']['handlers']['default']['stream'] == 'ext://sys.stdout'


def test_self_test_failure_does_not_echo_calculation(monkeypatch):
    import traceback
    monkeypatch.setattr(api, "ensure_tables", lambda folder: [])
    monkeypatch.setattr(api, "Grump", lambda: SimpleNamespace(r=[1], folder="unused"))

    def broken(g, c):
        raise ValueError("private-startup-marker " + str(c))

    monkeypatch.setattr(api, "calculate", broken)
    with pytest.raises(RuntimeError) as caught:
        with TestClient(api.app):
            pytest.fail("startup should fail")
    rendered = "".join(traceback.format_exception(caught.value))
    assert "private-startup-marker" not in rendered
    assert all(point not in rendered for point in api.SELF_TEST)
    assert "3046" not in rendered
