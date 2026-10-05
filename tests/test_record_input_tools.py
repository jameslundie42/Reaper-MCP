"""Recording-input tools: audio_get_inputs and track_set_record_monitor.

Input numbers depend on which interface REAPER has open, so audio_get_inputs
hands out the exact track_set_input value for each channel and stereo pair.
track_set_record_monitor sets I_RECMON for recording through an amp sim.
"""

from pathlib import Path

import pytest
from mcp.server.fastmcp import FastMCP

import reaper_mcp.main
from reaper_mcp.tools import track_tools

LUA = Path(__file__).resolve().parent.parent / "reaper_scripts" / "reaper_mcp_server.lua"


class _FakeClient:
    def __init__(self):
        self.calls = []

    async def execute(self, command, **params):
        self.calls.append((command, params))
        return {"ok": True}


@pytest.fixture
def tools(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setattr(reaper_mcp.main, "client", fake)
    mcp = FastMCP("test")
    track_tools.register(mcp)
    return mcp, fake


async def _call(mcp, name, **args):
    return await mcp.call_tool(name, args)


def _lua_handler(name: str) -> str:
    source = LUA.read_text(encoding="utf-8")
    start = source.index(f"function track.{name}(p)")
    return source[start: source.index("\nend\n", start)]


# ---- track_set_record_monitor --------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("mode, value", [("off", 0), ("on", 1), ("tape", 2)])
async def test_record_monitor_maps_modes(tools, mode, value):
    mcp, fake = tools
    await _call(mcp, "track_set_record_monitor", track_index=3, mode=mode)
    assert fake.calls == [("track_set_record_monitor", {"track_index": 3, "mode": value})]


@pytest.mark.asyncio
async def test_record_monitor_rejects_unknown_mode(tools):
    mcp, fake = tools
    with pytest.raises(Exception, match="mode must be one of"):
        await _call(mcp, "track_set_record_monitor", track_index=0, mode="auto")
    assert fake.calls == []


@pytest.mark.asyncio
async def test_record_monitor_rejects_master(tools):
    mcp, fake = tools
    with pytest.raises(Exception, match="track_index"):
        await _call(mcp, "track_set_record_monitor", track_index=-1, mode="on")
    assert fake.calls == []


def test_record_monitor_lua_writes_recmon():
    body = _lua_handler("track_set_record_monitor")
    assert '"I_RECMON"' in body


# ---- audio_get_inputs ------------------------------------------------------

@pytest.mark.asyncio
async def test_audio_get_inputs_dispatches(tools):
    mcp, fake = tools
    await _call(mcp, "audio_get_inputs")
    assert fake.calls == [("audio_get_inputs", {})]


def test_audio_get_inputs_lua_reports_reaper_input_values():
    body = _lua_handler("audio_get_inputs")
    assert 'GetAudioDeviceInfo("IDENT_IN")' in body
    assert "mono_input_index = i" in body
    assert "stereo_input_index = 1024 + i" in body
    assert "midi_all_input_index = RECINPUT_MIDI_ALL" in body
