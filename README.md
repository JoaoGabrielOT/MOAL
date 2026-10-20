# MOAL - More Options At Lantern

Mod for BLOODBORNE (1.09, CUSA03173), developed by FROM SOFTWARE, made for the PC port
[Jgamrot/bloodborne_pc](https://github.com/Jgamrot/bloodborne_pc).

Mod page: https://www.nexusmods.com/bloodborne/mods/107

At every lit lamp, one menu with: return to the Hunter's Dream, travel straight to another lit lamp
(the 5 headstones of the Dream), Channel Blood Echoes, workshop (fortify, repair, gems, runes,
arcane haze), messengers (buy, buy with Insight, sell), chest and rebirth (with the Doll Rebirth
mod from Nexus Mods installed). Installation and usage are on the Nexus page and in the
`README.txt` that comes with the download.

This repository holds the Python tools that generate the mod from the game's own files; no game
file is included.

## Generating the mod

Needs Python 3.10 or newer, no extra libraries.

```
python tools/build_moal.py "D:\Games\Bloodborne\game" output/MOAL
python tools/check_moal.py output/MOAL/dvdroot_ps4/script/talk
python tools/test_moal.py  output/MOAL/dvdroot_ps4/script/talk
```

- `check_moal`: round-trip of every script, called groups exist, enough arguments, no `WorkValue`.
- `test_moal`: simulates the menu (`sim_moal.py`) and checks each option, the shop by progress,
  returning to the Dream, travelling (flag 7AAA0150 + destination), a headstone with no lit lamp,
  a lamp marked "not working", Rebirth (without the patch, without levels, Cruel Fate,
  Waste of Skin, level menu afterwards) and the Chalice Dungeon lamps.

## Files

- `build_moal.py`: generates everything (menu, travel, rebirth, events). The table of the 9 origins
  and the `GetStatus(14)`/`(20)` and `ChangePlayerStat(20)` slots are the ones from Doll Rebirth.
- `esd.py`, `emevd.py`, `fromsoft.py`: from the Jgamrot/bloodborne_pc port (GPL-2.0-or-later):
  reading and writing `.esd`, `.emevd`, DCX and BND4.
- `souls.py`, `dump_esd.py`, `msgs.py`: text dumps of the scripts and text search (for study).

Older versions (ESDStudio ESD scripts, for shadPS4) remain in the git history.

## License

GPL-2.0-or-later ([LICENSE-GPL.txt](LICENSE-GPL.txt)), because it uses `esd.py`, `emevd.py` and
`fromsoft.py` from the port.
