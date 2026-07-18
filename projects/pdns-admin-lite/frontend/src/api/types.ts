// Mirrors of the backend Pydantic models (backend/core/models.py).

export interface ZoneSummary {
  id: string;
  name: string;
  kind: string;
  serial: number;
}

export interface DnsRecord {
  content: string;
  disabled: boolean;
}

export interface RRSet {
  name: string;
  type: string;
  ttl: number;
  records: DnsRecord[];
}

export interface ZoneDetail extends ZoneSummary {
  rrsets: RRSet[];
}

export const RECORD_TYPES = ["A", "AAAA", "CNAME", "TXT", "MX", "SRV", "NS", "PTR"] as const;

export type RecordType = (typeof RECORD_TYPES)[number];

export interface RecordInput {
  name: string;
  type: RecordType;
  ttl: number;
  records: string[];
}
