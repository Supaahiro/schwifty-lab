import type { RecordInput, RRSet, ZoneDetail, ZoneSummary } from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (body.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      // Non-JSON error body: keep the status text.
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export function getZones(): Promise<ZoneSummary[]> {
  return request("/zones");
}

export function getZone(zoneId: string): Promise<ZoneDetail> {
  return request(`/zones/${encodeURIComponent(zoneId)}`);
}

export function createRecord(zoneId: string, input: RecordInput): Promise<RRSet> {
  return request(`/zones/${encodeURIComponent(zoneId)}/records`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateRecord(zoneId: string, input: RecordInput): Promise<RRSet> {
  return request(`/zones/${encodeURIComponent(zoneId)}/records`, {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export function deleteRecord(zoneId: string, name: string, type: string): Promise<void> {
  const query = new URLSearchParams({ name, type });
  return request(`/zones/${encodeURIComponent(zoneId)}/records?${query}`, {
    method: "DELETE",
  });
}
