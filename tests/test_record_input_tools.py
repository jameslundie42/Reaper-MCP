"""Recording-input tools: audio_get_inputs, track_set_input, track_set_record_monitor.

track_set_input's docstring used to describe I_RECINPUT wrongly (0 = none,
-1 = MIDI all), so a model following it armed input 1 when it meant "no
input" and got no input when it meant MIDI. audio_get_inputs now hands out
the exact value for each channel and pair, and the docstring matches REAPER.
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


# ---- track_set_input ------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("value", [-1, 0, 1, 1024, 1026, 6112])
async def test_set_input_accepts_valid_values(tools, value):
    mcp, fake = tools
    await _call(mcp, "track_set_input", track_index=0, input_index=value)
    assert fake.calls == [("track_set_input", {"track_index": 0, "input_index": value})]


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [-2, 8192])
async def test_set_input_rejects_out_of_range(tools, value):
    mcp, fake = tools
    with pytest.raises(Exception, match="input_index"):
        await _call(mcp, "track_set_input", track_index=0, input_index=value)
    assert fake.calls == []


def test_set_input_docstring_matches_reaper():
    tool_doc = FastMCP("doc")
    track_tools.register(tool_doc)
    text = next(t for t in tool_doc._tool_manager.list_tools() if t.name == "track_set_input").description
    assert "-1 = no input" in text
    assert "0 = input 1" in text
    assert "0=none" not in text


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
    assert "no_input_index = -1" in body
    # MIDI, all devices (63 in bits 5-10), all channels (0 in bits 0-4)
    assert 4096 + (63 << 5) == 6112
    assert "4096 + (63 << 5)" in body
