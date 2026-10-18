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
Hooks = {}
function RegisterHook(path, fn) Hooks[path] = fn end
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
        # The statics are reached through a Lua table of plain function calls: lupa mixes up the object of a
        # colon call on a Python object after the script has made enough garbage, which has nothing to do with the game.
        g.PyStatics, g.PyReady = game.statics, lambda: game.ready
        lua.execute("""
            StaticsLua = {
                SetGlobalTimeDilation = function(_, c, v) return PyStatics.SetGlobalTimeDilation(c, v) end,
                GetGlobalTimeDilation = function(_, c) return PyStatics.GetGlobalTimeDilation(c) end,
                GetTimeSeconds = function(_, c) return PyStatics.GetTimeSeconds(c) end,
            }
            function StaticFindObject(path) if PyReady() and path:find("GameplayStatics", 1, true) then return StaticsLua end end
        """)
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


# ---- taking hold of the boat ends fast time

class Part:
    """Anything with a name and an address: a boat, a control group, the autopilot."""

    count = 0

    def __init__(self, name):
        Part.count += 1
        self.name, self.address = name, Part.count

    def GetFullName(self):
        return self.name

    def GetAddress(self):
        return self.address

    def IsValid(self):
        return True


class FakeBoat(Part):
    def __init__(self, x=0.0):
        super().__init__("BP_Boat_C_1")
        self.x = x

    def K2_GetActorLocation(self):
        return Vec(X=self.x, Y=0.0, Z=0.0)

    def GetVelocity(self):
        return Vec(X=0.0, Y=0.0, Z=0.0)

    def K2_GetActorRotation(self):
        return Vec(Roll=0.0, Pitch=0.0, Yaw=0.0)


class Group(Part):
    def __init__(self, boat, field, value=0.0):
        super().__init__("Group")
        self.MovementComponent = type("Movement", (), {"GetOwner": lambda self_: boat})()
        setattr(self, field, value)


class Pilot(Part):
    def __init__(self):
        super().__init__("AutopilotComponent")
        self.bAutopilotActivated = False


@pytest.fixture
def boat_mod(mod):
    m = mod()
    m.boat = FakeBoat()
    m.other = FakeBoat(x=900000.0)
    m.throttle = Group(m.boat, "Throttle")
    m.helm = Group(m.boat, "SteeringInput")
    m.far_throttle = Group(m.other, "Throttle")
    m.pilot = Pilot()

    def find_all(name):
        parts = {"Boat": [m.boat, m.other], "PropulsionGroup": [m.throttle, m.far_throttle], "SteeringGroup": [m.helm],
                 "AutopilotComponent": [m.pilot]}.get(name)
        return m.lua.table_from(parts) if parts is not None else None

    m.g.FindAllOf = find_all
    m.tick()
    return m


def at_speed(m, key="ADD"):
    press(m, key)
    m.tick()
    assert m.game.statics.dilation > 1
    m.tick()  # the controls are looked at once more at speed, so they are remembered


def test_a_throttle_change_puts_the_speed_back_to_normal(boat_mod):
    m = boat_mod
    at_speed(m)
    m.throttle.Throttle = 0.5
    m.tick()
    assert m.game.statics.dilation == 1 and m.test.Index() == 1
    assert any("the throttle changed (0.00 to 0.50)" in line for line in m.g.Printed.values())


def test_an_unchanged_throttle_leaves_the_speed_alone(boat_mod):
    m = boat_mod
    at_speed(m)
    m.throttle.Throttle = 0.005  # below the size of a change
    m.tick()
    assert m.game.statics.dilation == 2


def test_another_boats_throttle_is_not_ours(boat_mod):
    m = boat_mod
    at_speed(m)
    m.far_throttle.Throttle = 1.0
    m.tick()
    assert m.game.statics.dilation == 2


def test_the_helm_moving_puts_the_speed_back_to_normal(boat_mod):
    m = boat_mod
    at_speed(m)
    m.helm.SteeringInput = -0.3
    m.tick()
    assert m.game.statics.dilation == 1


def test_with_the_autopilot_on_its_own_steering_does_not(boat_mod):
    m = boat_mod
    m.pilot.bAutopilotActivated = True
    m.tick()
    at_speed(m)
    for value in (0.1, -0.2, 0.3):
        m.helm.SteeringInput = value
        m.tick()
    assert m.game.statics.dilation == 2


def test_a_hand_on_the_helm_with_the_autopilot_on_ends_it(boat_mod):
    m = boat_mod
    m.pilot.bAutopilotActivated = True
    m.tick()
    at_speed(m)
    m.g.Hooks["/Script/Sas.AutopilotComponent:ServerOnReceiveManualSteeringInput"]()
    m.tick()
    assert m.game.statics.dilation == 1


def test_the_autopilot_turning_off_puts_the_speed_back_to_normal(boat_mod):
    m = boat_mod
    m.pilot.bAutopilotActivated = True
    m.tick()
    at_speed(m)
    m.pilot.bAutopilotActivated = False
    m.tick()
    assert m.game.statics.dilation == 1
    assert any("the autopilot is off" in line for line in m.g.Printed.values())


def test_changes_at_normal_speed_are_only_remembered(boat_mod):
    m = boat_mod
    m.throttle.Throttle = 0.8
    m.tick()
    at_speed(m)
    m.tick()
    assert m.game.statics.dilation == 2  # the throttle was set before the fast time began
