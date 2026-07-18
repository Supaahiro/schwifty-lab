#!/bin/sh
# One-shot seeder for the demo PowerDNS container: creates the example.test.
# zone and a couple of A records through the same REST calls a real Ansible
# role would use. Idempotent: re-running against a seeded server succeeds.
set -eu

API="${PDNS_API_URL:?PDNS_API_URL is required}"
KEY="${PDNS_API_KEY:?PDNS_API_KEY is required}"

echo "Waiting for PowerDNS API at ${API}..."
tries=0
until curl -fsS -H "X-API-Key: ${KEY}" "${API}/servers/localhost" > /dev/null 2>&1; do
  tries=$((tries + 1))
  if [ "${tries}" -ge 30 ]; then
    echo "PowerDNS API not reachable after ${tries} attempts, giving up" >&2
    exit 1
  fi
  sleep 2
done

echo "Creating zone example.test. (kind Native)"
status=$(curl -s -o /tmp/zone-create.json -w '%{http_code}' \
  -X POST "${API}/servers/localhost/zones" \
  -H "X-API-Key: ${KEY}" -H 'Content-Type: application/json' \
  -d '{"name": "example.test.", "kind": "Native", "soa_edit_api": "DEFAULT", "nameservers": ["ns1.example.test."]}')
case "${status}" in
  201) echo "Zone created" ;;
  409) echo "Zone already exists, skipping" ;;
  *)
    echo "Zone creation failed (HTTP ${status}):" >&2
    cat /tmp/zone-create.json >&2
    exit 1
    ;;
esac

echo "Seeding demo A records"
curl -fsS -X PATCH "${API}/servers/localhost/zones/example.test." \
  -H "X-API-Key: ${KEY}" -H 'Content-Type: application/json' \
  --data @- << 'EOF'
{
  "rrsets": [
    {
      "name": "ns1.example.test.",
      "type": "A",
      "ttl": 3600,
      "changetype": "REPLACE",
      "records": [{"content": "192.168.0.1", "disabled": false}]
    },
    {
      "name": "web.example.test.",
      "type": "A",
      "ttl": 3600,
      "changetype": "REPLACE",
      "records": [{"content": "192.168.0.10", "disabled": false}]
    }
  ]
}
EOF

echo "Seed complete"
