import pytest
import respx
from fastapi.testclient import TestClient

from core.config import Settings
from main import build_app

PDNS_BASE = "http://pdns.test/api/v1"
ZONES_PATH = "/servers/localhost/zones"


@pytest.fixture
def pdns_mock():
    """Mock router intercepting the app's outbound calls to PowerDNS.

    respx only patches httpx's default transports, so the TestClient's own
    ASGI transport is unaffected.
    """
    with respx.mock(base_url=PDNS_BASE) as router:
        yield router


@pytest.fixture
def client(pdns_mock):
    app = build_app(Settings(pdns_api_url=PDNS_BASE, pdns_api_key="test-key"))
    with TestClient(app) as test_client:
        yield test_client
