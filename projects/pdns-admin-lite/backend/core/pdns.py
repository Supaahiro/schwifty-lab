"""Thin async client for the PowerDNS Authoritative REST API.

All upstream failures are raised as PdnsError; a single FastAPI exception
handler (see main.py) turns them into JSON error responses. Client-attributable
upstream statuses (400/404/409/422) pass through unchanged, anything else —
including auth/config problems and network failures — surfaces as 502.
"""

import httpx

PASSTHROUGH_STATUSES = {400, 404, 409, 422}


class PdnsError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def canonicalize(name: str, zone_id: str) -> str:
    """Turn a record name into the FQDN (trailing dot) PowerDNS expects.

    "@" or the empty string mean the zone apex; a name already ending with a
    dot is taken as-is; a name already ending with the zone is only given the
    trailing dot; anything else is treated as relative to the zone.
    """
    zone_fqdn = zone_id if zone_id.endswith(".") else f"{zone_id}."
    zone_bare = zone_fqdn.rstrip(".")
    name = name.strip()
    if name in ("", "@"):
        return zone_fqdn
    if name.endswith("."):
        return name
    if name == zone_bare or name.endswith(f".{zone_bare}"):
        return f"{name}."
    return f"{name}.{zone_fqdn}"


class PdnsClient:
    def __init__(self, http: httpx.AsyncClient, server_id: str) -> None:
        self._http = http
        self._base = f"/servers/{server_id}"

    async def list_zones(self) -> list[dict]:
        resp = await self._request("GET", f"{self._base}/zones")
        return resp.json()

    async def get_zone(self, zone_id: str) -> dict:
        resp = await self._request("GET", f"{self._base}/zones/{zone_id}")
        return resp.json()

    async def patch_rrsets(self, zone_id: str, rrsets: list[dict]) -> None:
        await self._request(
            "PATCH",
            f"{self._base}/zones/{zone_id}",
            json={"rrsets": rrsets},
        )

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            resp = await self._http.request(method, path, **kwargs)
        except httpx.TransportError as exc:
            raise PdnsError(502, f"PowerDNS unreachable: {exc}") from exc
        if resp.is_error:
            status = resp.status_code if resp.status_code in PASSTHROUGH_STATUSES else 502
            raise PdnsError(status, self._error_detail(resp))
        return resp

    @staticmethod
    def _error_detail(resp: httpx.Response) -> str:
        try:
            detail = resp.json().get("error")
        except ValueError:
            detail = None
        return detail or f"PowerDNS returned HTTP {resp.status_code}"
