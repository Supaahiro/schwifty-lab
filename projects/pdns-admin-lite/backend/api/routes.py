"""HTTP endpoints exposed to the frontend.

Zones are intentionally read-only here (created/deleted by Ansible in the real
lab); only records (rrsets) can be mutated.
"""

from fastapi import APIRouter, HTTPException, Query, Request

from core.models import RecordType, RecordUpsert, ZoneDetail, ZoneSummary
from core.pdns import PdnsClient, canonicalize

router = APIRouter()


def _client(request: Request) -> PdnsClient:
    return PdnsClient(request.app.state.http, request.app.state.settings.pdns_server_id)


def _to_rrset(zone_id: str, body: RecordUpsert, changetype: str) -> dict:
    return {
        "name": canonicalize(body.name, zone_id),
        "type": body.type.value,
        "ttl": body.ttl,
        "changetype": changetype,
        "records": [{"content": content, "disabled": False} for content in body.records],
    }


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/zones", response_model=list[ZoneSummary])
async def list_zones(request: Request) -> list[dict]:
    return await _client(request).list_zones()


@router.get("/zones/{zone_id}", response_model=ZoneDetail)
async def get_zone(request: Request, zone_id: str) -> dict:
    zone = await _client(request).get_zone(zone_id)
    zone["rrsets"] = sorted(
        zone.get("rrsets", []), key=lambda rrset: (rrset["name"], rrset["type"])
    )
    return zone


@router.post("/zones/{zone_id}/records", status_code=201)
async def create_record(request: Request, zone_id: str, body: RecordUpsert) -> dict:
    client = _client(request)
    rrset = _to_rrset(zone_id, body, "REPLACE")
    zone = await client.get_zone(zone_id)
    # Not atomic (check-then-patch), acceptable for a single-user POC.
    for existing in zone.get("rrsets", []):
        if existing["name"] == rrset["name"] and existing["type"] == rrset["type"]:
            raise HTTPException(
                status_code=409,
                detail=f"Record set {rrset['name']}/{rrset['type']} already exists",
            )
    await client.patch_rrsets(zone_id, [rrset])
    return rrset


@router.put("/zones/{zone_id}/records")
async def upsert_record(request: Request, zone_id: str, body: RecordUpsert) -> dict:
    rrset = _to_rrset(zone_id, body, "REPLACE")
    await _client(request).patch_rrsets(zone_id, [rrset])
    return rrset


@router.delete("/zones/{zone_id}/records", status_code=204)
async def delete_record(
    request: Request,
    zone_id: str,
    name: str = Query(min_length=1),
    type: RecordType = Query(),
) -> None:
    rrset = {
        "name": canonicalize(name, zone_id),
        "type": type.value,
        "changetype": "DELETE",
        "records": [],
    }
    await _client(request).patch_rrsets(zone_id, [rrset])
