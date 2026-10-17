"""SasTimeAccelerate run inside Python against a stand-in for UE4SS.

The script is the real one, unchanged. The game's player, its time functions and the nearest boat are small
Python classes; the key presses, the timer and the log are caught so that a test can press a key, let a
step run and read what the game was told.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from lupa import LuaRuntime

SCRIPT = Path(__file__).resolve().parents[1] / "SasTimeAccelerate" / "Scripts" / "main.lua"

STUB = r"""
Printed = {}
print = function(text) Printed[#Printed + 1] = text end
Timers = {}
function LoopInGameThreadWithDelay(ms, fn) Timers[#Timers + 1] = { ms = ms, fn = fn } end
Binds = {}
function RegisterKeyBind(key, modifiers, fn) Binds[key] = { modifiers = modifiers, fn = fn } end
NewPlayerCallbacks = {}
function NotifyOnNewObject(class, fn) NewPlayerCallbacks[#NewPlayerCallbacks + 1] = fn end
function FName(text) return text end
function FText(text) return text end
Key = setmetatable({}, { __index = function(_, name) return name end })
ModifierKey = setmetatable({}, { __index = function(_, name) return name end })
"""


class Vec:
    def __init__(self, **fields):
        self.__dict__.update(fields)


class Valid:
    def IsValid(self):
        return True


class Controller(Valid):
    def __init__(self):
        self.Pawn = Pawn()


class Pawn:
    def K2_GetActorLocation(self):
        return Vec(X=0.0, Y=0.0, Z=0.0)


class Statics:
    """GameplayStatics: remembers the dilation it was given, and a world clock that follows it."""

    def __init__(self):
        self.dilation = 1.0
        self.calls = []
        self.seconds = 0.0

    def SetGlobalTimeDilation(self, _controller, value):
        self.dilation = value
        self.calls.append(value)

    def GetGlobalTimeDilation(self, _controller):
        return self.dilation

    def GetTimeSeconds(self, _controller):
        return self.seconds


class Game:
    def __init__(self, ready=True):
        self.ready = ready
        self.controller = Controller()
        self.statics = Statics()
        self.toasts = []


@pytest.fixture
def mod():
    def start(ready=True):
        game = Game(ready)
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute(STUB)
        g = lua.globals()
        g.SAS_TEST = True
        g.FindFirstOf = lambda name: game.controller if (game.ready and name == "PlayerController") else None
        g.FindAllOf = lambda name: None
        g.StaticFindObject = lambda path: game.statics if (game.ready and "GameplayStatics" in path) else None
        loader = lua.eval("function(src, name) return load(src, '@' .. name) end")
        chunk = loader(SCRIPT.read_text(encoding="utf-8"), str(SCRIPT))
        chunk()
        step = g.Timers[1]["fn"]
        return type("Mod", (), {"g": g, "lua": lua, "game": game, "test": g.SasTest, "tick": staticmethod(step)})

    return start


def press(m, key):
    m.g.Binds[key]["fn"]()


def test_it_starts_at_normal_speed_and_says_which_version_is_running(mod):
    m = mod()
    m.tick()
    assert m.game.statics.calls == [1]
    first = list(m.g.Printed.values())[0]
    assert first.startswith("[SasTimeAccelerate] version ") and "file checksum" in first


def test_the_page_keys_step_through_the_speeds_and_stop_at_each_end(mod):
    m = mod()
    m.tick()
    seen = []
    for _ in range(6):
        press(m, "ADD")
        m.tick()
        seen.append(m.game.statics.dilation)
    assert seen == [2, 4, 8, 8, 8, 8]
    for _ in range(5):
        press(m, "SUBTRACT")
        m.tick()
    assert m.game.statics.dilation == 1
    assert m.test.Index() == 1


def test_home_returns_to_normal_at_once(mod):
    m = mod()
    m.tick()
    for _ in range(3):
        press(m, "ADD")
        m.tick()
    assert m.game.statics.dilation == 8
    press(m, "NUM_ZERO")
    m.tick()
    assert m.game.statics.dilation == 1 and m.test.Index() == 1


def test_the_keys_need_ctrl_and_alt(mod):
    m = mod()
    for key in ("ADD", "SUBTRACT", "NUM_ZERO"):
        assert set(m.g.Binds[key]["modifiers"].values()) == {"CONTROL", "ALT"}


def test_a_loaded_save_goes_back_to_normal_speed(mod):
    m = mod()
    m.tick()
    press(m, "ADD")
    m.tick()
    assert m.game.statics.dilation == 2
    m.g.NewPlayerCallbacks[1]()  # the game made a new player controller: a save was loaded
    m.tick()
    assert m.game.statics.dilation == 1 and m.test.Index() == 1


def test_nothing_is_done_while_the_game_has_no_player_and_it_is_tried_again(mod):
    m = mod(ready=False)
    press(m, "ADD")
    m.tick()
    assert m.game.statics.calls == [] and m.test.Index() == 1  # the speed did not change, nothing was told
    m.game.ready = True
    m.tick()
    assert m.game.statics.calls == [1]  # started at normal speed once the player existed


def test_it_logs_how_fast_the_world_runs_only_while_fast(mod):
    m = mod()
    m.tick()
    before = len(m.g.Printed)
    m.game.statics.seconds = 10.0
    m.tick()
    assert len(m.g.Printed) == before  # normal speed: nothing is logged
    press(m, "ADD")
    m.tick()
    lines = [m.g.Printed[i] for i in range(1, len(m.g.Printed) + 1)]
    assert any("speed 2x (dilation 2.00)" in line for line in lines)


def fnv1a(data: bytes) -> str:
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xFFFFFFFF
    return f"{value:08X}"


def test_the_checksum_in_the_log_is_the_files_own(mod):
    m = mod()
    data = SCRIPT.read_bytes()
    line = m.g.Printed[1]
    assert f"file checksum {fnv1a(data)} ({len(data)} bytes)" in line
