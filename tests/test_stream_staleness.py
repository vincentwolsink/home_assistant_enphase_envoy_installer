"""Tests for the stream reader staleness watchdog.

Imports envoy_reader directly to avoid pulling in the full homeassistant
dependency tree through __init__.py.
"""

import asyncio
import importlib
import logging
import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


# ---- Import envoy_reader directly, bypassing __init__.py ----
# We temporarily prevent __init__.py from being loaded by pre-registering
# a stub for the package, then import the module file directly.

_pkg_name = "custom_components.enphase_envoy"

# Create stub package so Python doesn't try to execute __init__.py
if _pkg_name not in sys.modules:
    pkg = ModuleType(_pkg_name)
    pkg.__path__ = ["custom_components/enphase_envoy"]
    pkg.__package__ = _pkg_name
    sys.modules[_pkg_name] = pkg

# Also stub the .const and .envoy_endpoints sub-modules that envoy_reader
# imports at module level.
for sub in ("const", "envoy_endpoints"):
    full = f"{_pkg_name}.{sub}"
    if full not in sys.modules:
        sys.modules[full] = MagicMock()

# Make envoy_endpoints expose the constants envoy_reader needs.
_ep = sys.modules[f"{_pkg_name}.envoy_endpoints"]
_ep.ENDPOINT_URL_STREAM = "https://{}/stream/meter"
_ep.ENDPOINT_URL_INSTALLER_AGF_SET_PROFILE = "https://{}/installer/agf/set"
_ep.ENDPOINT_URL_INSTALLER_AGF_UPLOAD_PROFILE = "https://{}/installer/agf/upload"

# Now load envoy_reader from source.
import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location(
    f"{_pkg_name}.envoy_reader",
    "custom_components/enphase_envoy/envoy_reader.py",
    submodule_search_locations=[],
)
envoy_reader_mod = importlib.util.module_from_spec(spec)
sys.modules[f"{_pkg_name}.envoy_reader"] = envoy_reader_mod
spec.loader.exec_module(envoy_reader_mod)

EnvoyReader = envoy_reader_mod.EnvoyReader

ENVOY_MODEL_M = "Metered"


def _make_reader(**kwargs):
    """Create a minimal EnvoyReader for testing stream_reader.

    Uses a MagicMock wrapping a real instance to bypass read-only
    properties like ``is_metering_enabled``.
    """
    reader = MagicMock(spec=EnvoyReader)
    reader.host = "192.168.1.1"
    reader.is_metering_enabled = True
    reader.endpoint_type = ENVOY_MODEL_M
    reader._authorization_header = {"Authorization": "Bearer test"}
    reader._cookies = {}
    reader.is_receiving_realtime_data = False
    reader.init_authentication = AsyncMock()
    # Bind the real stream_reader method to the mock instance.
    reader.stream_reader = lambda **kw: EnvoyReader.stream_reader(reader, **kw)
    for k, v in kwargs.items():
        setattr(reader, k, v)
    return reader


class _FakeResponse:
    """Fake httpx streaming response."""

    def __init__(self, status_code=200, chunks=None, hang=False, hang_timeout=5):
        self.status_code = status_code
        self.text = ""
        self._chunks = chunks or []
        self._hang = hang
        self._hang_timeout = hang_timeout

    async def aread(self):
        pass

    async def aiter_text(self):
        for chunk in self._chunks:
            yield chunk
        if self._hang:
            await asyncio.sleep(self._hang_timeout)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class _FakeClient:
    """Fake httpx.AsyncClient that returns a FakeResponse from .stream()."""

    def __init__(self, response):
        self._response = response
        self.closed = False

    def stream(self, method, url, **kwargs):
        return self._response

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
async def test_stream_reconnects_on_read_timeout():
    """Stream returns None (triggering reconnection) when ReadTimeout is raised."""
    reader = _make_reader()

    # Simulate a response whose aiter_text raises ReadTimeout (as httpx
    # would when the read deadline expires on a stale connection).
    class _TimeoutResponse(_FakeResponse):
        async def aiter_text(self):
            yield "data: {}\n"
            raise httpx.ReadTimeout("read timed out")

    response = _TimeoutResponse(status_code=200)
    fake_client = _FakeClient(response)

    with (
        patch.object(envoy_reader_mod.httpx, "Timeout"),
        patch.object(envoy_reader_mod.httpx, "AsyncClient", return_value=fake_client),
    ):
        result = await reader.stream_reader(meter_callback=MagicMock())

    # stream_reader returns None on ReadTimeout (not False), so the
    # reconnection loop in __init__.py will reconnect.
    assert result is None
    assert reader.is_receiving_realtime_data is False
    assert fake_client.closed


@pytest.mark.asyncio
async def test_stream_uses_dedicated_client_with_timeout():
    """Stream creates a dedicated httpx client with SSE-appropriate timeouts."""
    reader = _make_reader()
    response = _FakeResponse(status_code=200, chunks=[])
    fake_client = _FakeClient(response)

    with (
        patch.object(envoy_reader_mod.httpx, "Timeout") as mock_timeout,
        patch.object(envoy_reader_mod.httpx, "AsyncClient") as mock_client_cls,
    ):
        mock_timeout.return_value = httpx.Timeout(
            connect=10.0, read=120.0, write=10.0, pool=10.0
        )
        mock_client_cls.return_value = fake_client

        await reader.stream_reader()

    # Timeout and AsyncClient are called once per stream_reader invocation.
    mock_timeout.assert_called_with(connect=10.0, read=60.0, write=10.0, pool=10.0)
    mock_client_cls.assert_called_with(verify=False, timeout=mock_timeout.return_value)
    assert fake_client.closed


@pytest.mark.asyncio
async def test_stream_normal_data_flow():
    """Stream processes data chunks and returns True on clean exit."""
    reader = _make_reader()
    callback = MagicMock()

    chunks = [
        'data: {"production": {}, "net-consumption": {}, "total-consumption": {}}\n',
    ]
    response = _FakeResponse(status_code=200, chunks=chunks)
    fake_client = _FakeClient(response)

    with (
        patch.object(envoy_reader_mod.httpx, "Timeout"),
        patch.object(envoy_reader_mod.httpx, "AsyncClient", return_value=fake_client),
    ):
        result = await reader.stream_reader(meter_callback=callback)

    assert result is True
    assert callback.called
    assert reader.is_receiving_realtime_data is False
    assert fake_client.closed


@pytest.mark.asyncio
async def test_stream_401_stops_reconnection():
    """Stream returns False on 401 to stop reconnection attempts."""
    reader = _make_reader()
    response = _FakeResponse(status_code=401)
    fake_client = _FakeClient(response)

    with (
        patch.object(envoy_reader_mod.httpx, "Timeout"),
        patch.object(envoy_reader_mod.httpx, "AsyncClient", return_value=fake_client),
    ):
        result = await reader.stream_reader()

    assert result is False
    assert fake_client.closed


@pytest.mark.asyncio
async def test_stream_500_retries():
    """Stream returns True on 500 to trigger reconnection."""
    reader = _make_reader()
    response = _FakeResponse(status_code=500)
    fake_client = _FakeClient(response)

    with (
        patch.object(envoy_reader_mod.httpx, "Timeout"),
        patch.object(envoy_reader_mod.httpx, "AsyncClient", return_value=fake_client),
    ):
        result = await reader.stream_reader()

    assert result is True
    assert fake_client.closed


@pytest.mark.asyncio
async def test_finally_block_demoted_to_debug(caplog):
    """The 'Stopped reading realtime data' log should be DEBUG, not ERROR."""
    reader = _make_reader()
    response = _FakeResponse(status_code=200, chunks=[])
    fake_client = _FakeClient(response)

    with (
        patch.object(envoy_reader_mod.httpx, "Timeout"),
        patch.object(envoy_reader_mod.httpx, "AsyncClient", return_value=fake_client),
        caplog.at_level(logging.DEBUG),
    ):
        await reader.stream_reader()

    stopped_records = [
        r for r in caplog.records if "Stopped reading realtime data" in r.message
    ]
    assert stopped_records, "Expected 'Stopped reading realtime data' log message"
    for record in stopped_records:
        assert record.levelno == logging.DEBUG, (
            f"Expected DEBUG level, got {record.levelname}"
        )
