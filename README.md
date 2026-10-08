# Ultima VII: The Black Gate: native tactical patch

This package installs the tactical modification into an existing, locally owned game. It contains the patch, source, installer, and technical notes. It does not contain a playable game, original or modified `U7.EXE`, the copied original overlay, game assets, saves, configuration, or gameplay screenshots.

The modification runs in the original DOS engine. Continue starting the game through its normal `ULTIMA7.COM` launcher in your existing DOS setup. The installation tool runs on your host computer, outside DOS, using Python 3.10 or later. NASM is needed only to rebuild the source.

## Supported executable

The only supported pristine input is the English **The Black Gate 3.4 with Forge of Virtue** executable identified below. A matching filename or displayed version alone is insufficient.

| Input | Bytes | SHA-256 |
| --- | ---: | --- |
| Supported pristine `U7.EXE` | 689,248 | `4d588b12c775927c77c221531be4910eaf413864a8e2ec3f6f0d7a9c302b6e54` |
| Accepted previous tactical v7 `U7.EXE` | 713,824 | `7e7d908a0885627f545fd6a6ef299d34e170bdb19bfc85e8db6d2d05b5f01349` |

The current release's exact output identity is in `BUILD.json` and `patch.json`. Other languages, executable versions, and independently modified executables are rejected.

## Tactical controls

Press Space in the world view to open the compact, 180 by 94 pixel tactical panel, initially at the bottom left of the native screen. Click its party numbers and command buttons, or use the corresponding keys. Drag the title bar to move the panel; its position remains within the screen and is remembered during the running game.

| Key or control | Action |
| --- | --- |
| Space / Resume | Open tactical pause; resume when already paused |
| 1 to 9 / party number | Select a member by the current party order; 1 is the Avatar |
| T Target | Select an attack target using the current equipment |
| M Melee / R Ranged | Validate the actual left-hand weapon; open equipment if needed, then select a target |
| G Move | Select a destination; move there, then hold |
| H Hold / A Auto | Hold position, or return to ordinary companion behavior |
| I Gear | Open the selected member's native equipment interface |
| Tab / Hide / Paused Show | Hide or reopen the panel while simulation remains paused |
| Esc | Resume from the panel, or cancel a tactical target/destination picker |
| Right-button press in a tactical picker | Cancel selection and retain the prior order |

Mouse buttons activate when released over the same control. The opening click is consumed before handing control to a target picker or equipment screen. Each actor has one current order; canceled selections retain the prior order. Ordinary right-mouse Avatar movement respects manually commanded companions, so a held companion stays in place. Saves remain native format, and loading starts with automatic companion behavior.

The native C combat shortcut retains its original behavior. If the Avatar has an explicit Hold order, return the Avatar to Auto before using C to end ordinary combat. See `VALIDATION.txt` for the observed native behavior.

## Install or upgrade

1. Exit the game and DOSBox before replacing its executable.
2. Extract this entire patch package into a separate folder.
3. Open a terminal in the extracted patch folder. Supply your existing game folder containing `U7.EXE`, or the full path to that file.

On Windows:

```text
python install.py "C:\Games\Ultima7\Blackgat" --check
python install.py "C:\Games\Ultima7\Blackgat"
```

On Linux or macOS, use `python3` if that is your installed command:

```text
python3 install.py "/path/to/Blackgat" --check
python3 install.py "/path/to/Blackgat"
```

`--check` reconstructs and verifies the entire output without changing any game files. Installation replaces only `U7.EXE` and stores the verified pristine executable at `TACTICAL-PATCH/U7.ORI`. It retains your present saves, game data, launchers, and configuration. Running the installer again on the current release reports that it is already installed and leaves it alone.

For a v7 upgrade, the installer recognizes the exact previous executable and automatically uses `TACTICAL/U7.ORI` from that installation, or a matching `TACTICAL-PATCH/U7.ORI`. Keep that original backup. If it is elsewhere, supply it explicitly:

```text
python install.py "C:\Games\Ultima7\Blackgat" --original "C:\Backups\U7.ORI"
```

The original backup must match the supported pristine hash. Upgrading requires a verified original executable; the installer does not reconstruct one from an unverified modified binary. Never use an executable from a different game version as the backup.

## Restore the original executable

Exit the game, then run:

```text
python install.py "C:\Games\Ultima7\Blackgat" --uninstall
```

Use `python3` and your own path on Linux/macOS. An explicit `--original` path can also be supplied. The installer restores only a verified supported original and retains saves, configuration, and all backup files. A different or unknown executable is never silently overwritten.

## Installation safeguards

The installer verifies the complete input hash, checks the source and compiled object hashes, prepares the replacement in memory, validates DOS overlay and relocation bounds, and verifies the complete release hash before replacing the executable. It creates a pristine backup without overwriting an existing different file. The replacement is staged beside `U7.EXE` and moved into place atomically.

An installation lock protects against two copies of this installer modifying one game folder at once. If the host process is interrupted, a verified backup may remain and the original or complete replacement executable remains in place. A stale `TACTICAL-PATCH/INSTALL.lock` can be removed after confirming no installer is running. A damaged or conflicting backup produces an error and is left untouched.

## Rebuild from source

The source is included for review and modification. Python 3.10 or later and NASM are required. From the extracted patch folder:

```text
python source/native_patcher.py "/path/to/your/pristine/U7.EXE" "U7.REBUILT.EXE" --source source
```

Append `--nasm "/path/to/nasm"` if NASM is not on your `PATH`. Compare the printed output SHA-256 with `BUILD.json`. This local rebuild generates an executable using your own original bytes; do not add the executable or its original backup to the shareable patch archive.

After modifying the source, create a new patch-only package with:

```text
python build_distribution.py --original "/path/to/your/pristine/U7.EXE" --source source --version custom --output release --archive Tactical-Patch-custom.zip
```

Use `--expected "/path/to/your/final/U7.EXE"` to require exact reproduction of an independently built candidate. A release should be built from stable sources after its native runtime checks. `BUILD.json` describes the generated output and patch blocks; it is a build record, not a claim of complete campaign testing.

## What to share

Share the complete patch ZIP. Recipients install it into their own matching game. Keep the full-game archive, original and modified executables, backups, and personal saves out of the patch ZIP. `HANDOVER.md` describes the behavior and state lifecycle for programmers interested in implementing a similar feature in another engine.

The native mappings and patch metadata macros come from John Glassmyer's MIT-licensed UltimaHacks. The retained notice and scope of attribution are in `LICENSE-UPSTREAM.txt` and `ATTRIBUTION.md`.
