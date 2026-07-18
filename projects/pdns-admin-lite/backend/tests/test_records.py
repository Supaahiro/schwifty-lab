import json

import pytest

from core.pdns import canonicalize
from tests.conftest import ZONES_PATH

ZONE_PATH = f"{ZONES_PATH}/example.test."

EMPTY_ZONE = {"id": "example.test.", "name": "example.test.", "kind": "Native", "serial": 1, "rrsets": []}

ZONE_WITH_WEB = {
    **EMPTY_ZONE,
    "rrsets": [
        {
            "name": "web.example.test.",
            "type": "A",
            "ttl": 3600,
            "records": [{"content": "192.168.0.10", "disabled": False}],
        }
    ],
}


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("web", "web.example.test."),
        ("@", "example.test."),
        ("", "example.test."),
        ("web.example.test", "web.example.test."),
        ("web.example.test.", "web.example.test."),
        ("example.test", "example.test."),
        ("other.example.com.", "other.example.com."),
    ],
)
def test_canonicalize(name: str, expected: str) -> None:
    assert canonicalize(name, "example.test.") == expected


def test_create_record_sends_replace_patch(client, pdns_mock) -> None:
    """POST canonicalizes the name and issues a changetype REPLACE patch."""
    pdns_mock.get(ZONE_PATH).respond(200, json=EMPTY_ZONE)
    patch = pdns_mock.patch(ZONE_PATH).respond(204)
    response = client.post(
        "/api/zones/example.test./records",
        json={"name": "web", "type": "A", "ttl": 300, "records": ["192.168.0.10"]},
    )
    assert response.status_code == 201
    payload = json.loads(patch.calls.last.request.content)
    assert payload == {
        "rrsets": [
            {
                "name": "web.example.test.",
                "type": "A",
                "ttl": 300,
                "changetype": "REPLACE",
                "records": [{"content": "192.168.0.10", "disabled": False}],
            }
        ]
    }


def test_create_existing_rrset_conflicts(client, pdns_mock) -> None:
    pdns_mock.get(ZONE_PATH).respond(200, json=ZONE_WITH_WEB)
    response = client.post(
        "/api/zones/example.test./records",
        json={"name": "web", "type": "A", "ttl": 300, "records": ["192.168.0.99"]},
    )
    assert response.status_code == 409


def test_upsert_record_skips_existence_check(client, pdns_mock) -> None:
    """PUT replaces the whole rrset without reading the zone first."""
    patch = pdns_mock.patch(ZONE_PATH).respond(204)
    response = client.put(
        "/api/zones/example.test./records",
        json={"name": "web", "type": "A", "ttl": 600, "records": ["192.168.0.10", "192.168.0.11"]},
    )
    assert response.status_code == 200
    payload = json.loads(patch.calls.last.request.content)
    assert payload["rrsets"][0]["changetype"] == "REPLACE"
    assert [r["content"] for r in payload["rrsets"][0]["records"]] == [
        "192.168.0.10",
        "192.168.0.11",
    ]


def test_delete_record_sends_delete_changetype(client, pdns_mock) -> None:
    patch = pdns_mock.patch(ZONE_PATH).respond(204)
    response = client.delete("/api/zones/example.test./records?name=web&type=A")
    assert response.status_code == 204
    payload = json.loads(patch.calls.last.request.content)
    assert payload == {
        "rrsets": [
            {"name": "web.example.test.", "type": "A", "changetype": "DELETE", "records": []}
        ]
    }


def test_invalid_record_type_rejected(client, pdns_mock) -> None:
    response = client.post(
        "/api/zones/example.test./records",
        json={"name": "web", "type": "SPF", "ttl": 300, "records": ["x"]},
    )
    assert response.status_code == 422
    assert not pdns_mock.calls


def test_empty_records_rejected(client, pdns_mock) -> None:
    response = client.put(
        "/api/zones/example.test./records",
        json={"name": "web", "type": "A", "ttl": 300, "records": []},
    )
    assert response.status_code == 422
    assert not pdns_mock.calls
