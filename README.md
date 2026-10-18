# SasTimeAccelerate

Speed up the game's time while sailing, for Ships At Sea, as a UE4SS Lua mod.

## What it does

| Keys | Does |
| --- | --- |
| **Ctrl+Alt+Numpad +** | next speed up: 1x, 2x, 4x, 8x |
| **Ctrl+Alt+Numpad -** | next speed down |
| **Ctrl+Alt+Numpad 0** | back to normal speed at once |

A toast names the speed each time it changes. The keys are on the numeric keypad because the game uses
PageUp, PageDown and Home for the engine (and ignores Ctrl and Alt); Num Lock must be on for Numpad 0.

The speed is the game's global time dilation, so the world, the boat, the water and the calendar all run
faster together. Nothing here changes the calendar's own speed setting.

The game always starts at normal speed, whatever it was left at, and goes back to normal when a save is
loaded. There is no time limit. Go up a step at a time, and come down before docking or working a crane.

## Tested

Measured from the log, in solo play on the class 2 cargo boat:

- **At the dock**, the world clock ran at 4.00x and 8.00x real time, and the calendar kept pace (it runs at
  its own speed times the dilation).
- **Sailing at about 16 knots**, it held 4.00x at 4x and 8.00x (7.99 to 8.02) at 8x for 80 seconds. The boat's
  speed stayed at 16 to 17 knots. At 4x the heel stayed under half a degree. At 8x it was mostly under
  1.5 degrees, with a few readings between 2.7 and 5.7 degrees (and a pitch of 4.9) in rougher water, and it
  settled back each time. There is no reading of the same leg at normal speed to compare with.
- Not tested: other boats, crane work at speed, towing, multiplayer.

## Telemetry

While the speed is above normal the log (`UE4SS.log`) gets a line every five seconds:

```
[SasTimeAccelerate] speed 4x (dilation 4.00), world clock runs 4.00 x real, BP_Cargo_Boat_2_C_1 16.4 kn, roll 0.3, pitch -1.1, heading 212, Z 2 | calendar speed 8.00, 14:32
```

It says how fast the world clock really runs against the wall clock, the nearest boat's speed, heel and trim,
and the calendar's own speed and time, so that what a speed does to a boat can be read afterwards. When the mod
loads it also writes `version ..., file checksum ...`, so there is never a doubt which copy the game took.

## Install

1. Install [UE4SS](https://github.com/UE4SS-RE/RE-UE4SS) for the game (the experimental build, with the
   `ue4ss` folder next to `Sas-Win64-Shipping.exe`).
2. Copy the `SasTimeAccelerate` folder into `ue4ss\Mods`, so that `ue4ss\Mods\SasTimeAccelerate\enabled.txt` and
   `Scripts\main.lua` exist. Restart the game. (Ctrl+R in UE4SS can hang the game; restart instead.)

To uninstall, delete the folder, or delete only its `enabled.txt` to switch it off.

## Notes

- Time dilation also slows or speeds the other mods' timers, which run on the game thread. The crane operator
  works at any speed, but at 8x the crane moves eight times as fast, so keep it at normal speed while she works.
- Tested in solo play only.

## Working on it

```
.\deploy.ps1              # copy the mod into the game; takes -GameDir for a non-default library
.\package.ps1 v0.1.0      # build the release zip into dist\
python tools/check_lua.py # luacheck, a syntax check and the count of top-level locals
python -m pytest -q tests # run the script inside Python against a stand-in for the game
```

`pip install -r requirements-dev.txt` for the tests. The same checks run on GitHub on every push
(`.github/workflows/ci.yml`). luacheck is looked for in `$LUACHECK`, then `..\.tools\luacheck\luacheck.exe`,
then on the PATH.

## License

MIT.
