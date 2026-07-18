import httpx

from tests.conftest import ZONES_PATH

ZONE = {
    "id": "example.test.",
    "name": "example.test.",
    "kind": "Native",
    "serial": 2026071801,
    "url": "/api/v1/servers/localhost/zones/example.test.",
    "dnssec": False,
    "rrsets": [
        {
            "name": "web.example.test.",
            "type": "A",
            "ttl": 3600,
            "comments": [{"content": "internal", "account": ""}],
            "records": [{"content": "192.168.0.10", "disabled": False}],
        },
        {
            "name": "example.test.",
            "type": "SOA",
            "ttl": 3600,
            "comments": [],
            "records": [
                {"content": "ns1.example.test. hostmaster.example.test. 1 10800 3600 604800 3600", "disabled": False}
            ],
        },
    ],
}


def test_health_does_not_call_pdns(client, pdns_mock) -> None:
    """The health endpoint must succeed with zero upstream traffic."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert not pdns_mock.calls


def test_list_zones_maps_summary(client, pdns_mock) -> None:
    """Zone listing is slimmed to id/name/kind/serial and sends the API key."""
    route = pdns_mock.get(ZONES_PATH).respond(200, json=[ZONE])
    response = client.get("/api/zones")
    assert response.status_code == 200
    assert response.json() == [
        {"id": "example.test.", "name": "example.test.", "kind": "Native", "serial": 2026071801}
    ]
    assert route.calls.last.request.headers["X-API-Key"] == "test-key"


def test_get_zone_shapes_and_sorts_rrsets(client, pdns_mock) -> None:
    """Zone detail keeps only displayable rrset fields, sorted by name/type."""
    pdns_mock.get(f"{ZONES_PATH}/example.test.").respond(200, json=ZONE)
    response = client.get("/api/zones/example.test.")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "example.test."
    assert [(r["name"], r["type"]) for r in body["rrsets"]] == [
        ("example.test.", "SOA"),
        ("web.example.test.", "A"),
    ]
    assert "comments" not in body["rrsets"][0]


def test_zone_not_found_passes_through(client, pdns_mock) -> None:
    pdns_mock.get(f"{ZONES_PATH}/nope.test.").respond(404, json={"error": "Not Found"})
    response = client.get("/api/zones/nope.test.")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_upstream_401_maps_to_502(client, pdns_mock) -> None:
    """A bad API key is a server misconfiguration, not the UI user's fault."""
    pdns_mock.get(ZONES_PATH).respond(401, json={"error": "Unauthorized"})
    response = client.get("/api/zones")
    assert response.status_code == 502
    assert response.json() == {"detail": "Unauthorized"}


def test_pdns_unreachable_maps_to_502(client, pdns_mock) -> None:
    pdns_mock.get(ZONES_PATH).mock(side_effect=httpx.ConnectError("refused"))
    response = client.get("/api/zones")
    assert response.status_code == 502
    assert "unreachable" in response.json()["detail"]
