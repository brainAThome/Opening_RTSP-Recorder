"""Home Assistant integration tests (safe, minimal).

These tests are intentionally conservative and will be skipped if
pytest-homeassistant-custom-component is not installed.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import asyncio
from pytest_socket import enable_socket

pytest.importorskip("homeassistant")
pytest.importorskip("pytest_homeassistant_custom_component")

from pytest_homeassistant_custom_component.common import MockConfigEntry

# Ensure custom_components can be imported
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.rtsp_recorder import async_setup_entry, async_unload_entry
from custom_components.rtsp_recorder.const import DOMAIN
import custom_components.rtsp_recorder as rtsp_init


def _prepare_entry_and_mocks(hass, tmp_path, monkeypatch):
    storage_path = tmp_path / "recordings"
    snapshot_path = tmp_path / "thumbnails"
    analysis_path = tmp_path / "analysis"

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "storage_path": str(storage_path),
            "snapshot_path": str(snapshot_path),
            "analysis_output_path": str(analysis_path),
        },
        options={},
        title="RTSP Recorder",
    )
    entry.add_to_hass(hass)

    # Provide http mock for register_view
    hass.http = MagicMock()
    hass.http.register_view = MagicMock()

    # Patch external interactions for a safe test run
    monkeypatch.setattr(rtsp_init, "log_to_file", lambda *args, **kwargs: None)
    add_js_mock = MagicMock()
    monkeypatch.setattr(rtsp_init, "add_extra_js_url", add_js_mock)
    monkeypatch.setattr(rtsp_init, "enable_sqlite_backend", lambda *args, **kwargs: True)
    monkeypatch.setattr(rtsp_init, "_load_people_db", AsyncMock(return_value={}))
    monkeypatch.setattr(rtsp_init, "register_websocket_handlers", lambda *args, **kwargs: None)
    monkeypatch.setattr(rtsp_init, "register_people_websocket_handlers", lambda *args, **kwargs: None)

    register_services_mock = MagicMock(return_value={
        "handle_save_recording": AsyncMock(),
        "analyze_batch": AsyncMock(),
    })
    monkeypatch.setattr(rtsp_init, "register_services", register_services_mock)

    # Neutralize scheduler hooks
    monkeypatch.setattr(rtsp_init, "async_track_time_interval", lambda *args, **kwargs: None)
    monkeypatch.setattr(rtsp_init, "async_track_time_change", lambda *args, **kwargs: None)
    monkeypatch.setattr(rtsp_init, "async_track_state_change_event", lambda *args, **kwargs: None)

    # Avoid lingering timers during teardown
    class _DummyHandle:
        def cancel(self):
            return None

    if getattr(hass, "loop", None) is not None:
        monkeypatch.setattr(hass.loop, "call_later", lambda *args, **kwargs: _DummyHandle())

    return entry, storage_path, snapshot_path, analysis_path, add_js_mock, register_services_mock


@pytest.fixture(scope="session")
def event_loop():
    """Override event loop fixture to allow sockets for HA setup."""
    enable_socket()
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.mark.integration
@pytest.mark.ha
@pytest.mark.enable_socket
@pytest.mark.asyncio
async def test_async_setup_and_unload_entry(hass, tmp_path, monkeypatch):
    """Minimal HA integration setup/unload test (safe defaults)."""
    entry, *_ = _prepare_entry_and_mocks(hass, tmp_path, monkeypatch)

    assert await async_setup_entry(hass, entry) is True
    assert await async_unload_entry(hass, entry) is True


@pytest.mark.integration
@pytest.mark.ha
@pytest.mark.enable_socket
@pytest.mark.asyncio
async def test_async_setup_creates_paths_and_registers(hass, tmp_path, monkeypatch):
    """Ensure setup creates directories and registers services/resources."""
    entry, storage_path, snapshot_path, analysis_path, add_js_mock, register_services_mock = _prepare_entry_and_mocks(
        hass, tmp_path, monkeypatch
    )

    assert await async_setup_entry(hass, entry) is True

    assert storage_path.exists()
    assert snapshot_path.exists()
    assert analysis_path.exists()

    assert add_js_mock.called is True
    assert hass.http.register_view.called is True
    assert register_services_mock.called is True
