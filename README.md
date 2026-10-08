# Ultima VII Tactical Patch v1.2

Independent competition build for the original English DOS Black Gate 3.4 with Forge of Virtue. Includes the v1.1 tactical controls, five difficulty choices, companion spellcasting, and merchant spellbooks. Start through ULTIMA7.COM in your existing DOS setup. Install on the host computer using Python 3.10 or later; NASM is needed only to rebuild modified source.

The ZIP contains source, preassembled patch objects, installer, tests and documentation. Each game file is reconstructed from the recipient's own matching original. No game executable, original resource, save or screenshot is included.

## Difficulty

Before the original graphical menu, a native DOS selector accepts 1 to 5. Enter accepts the current selection; Esc also continues with it. Normal is the default. The selection is stored in TACTIC.DIF in the game folder and applies to the next loaded or new game in that process. Restart through ULTIMA7.COM to change it.

| Choice | Enemy effective durability | Enemy outgoing damage | Powerful native abilities |
| --- | ---: | ---: | --- |
| 1 Game Journalist | 25% | 25% | Disabled |
| 2 Easy | 75% | 75% | Reduced frequency after magic is restored |
| 3 Normal | 100% | 100% | Original random bounds and behavior |
| 4 Hard | 125% | 125% | Increased frequency after magic is restored |
| 5 Avatar | 200% | 200% | Frequent use after magic is restored |

Durability scales incoming party damage, retaining native displayed HP and save values. Native signed damage is capped at 127. A per-NPC remainder ensures small repeated hits still count on Hard and Avatar. Party-on-party damage, nonparty-on-nonparty damage and damage without an attacker retain native behavior.

The adjusted powerful abilities are teleportation, invisibility and summoning. After the original Tetrahedron Generator flag is set, Easy doubles their random bounds, Hard uses two thirds, and Avatar uses two fifths, with integer rounding. This changes the native chance checks, rather than assigning new spells to every monster. Before that story event, Easy, Hard and Avatar retain the original ability chances; Game Journalist suppresses these abilities throughout.

## Companion magic

After destroying the Tetrahedron Generator, select Jaana while tactically paused and press C or click Cast. She needs a spellbook and the required reagents in her own inventory, including nested bags. Native learned spells, level checks, reagent consumption, target selection and spell effects apply.

Mariah is also supported if she is already in the party; this patch does not change her recruitment. The other original recruitable companions retain their martial roles. The Avatar may use Cast throughout the game under the original rules.

Companion mana starts at intelligence, with a minimum capacity of eight, and regenerates one point per sixteen native game-clock units while the game runs. Mana is saved in otherwise unused native NPC bytes. Pause time does not regenerate mana. Native identity/flag bytes are preserved. Casting returns to tactical pause, with the actual Avatar restored.

To purchase advanced spells, let the Avatar carry the book during the original merchant transaction, then pass it to the companion. Existing spellbooks keep their learned spells.

## Merchant spellbooks

Choose **spellbook** in the normal dialogue with Nystul, Rudyom, Nicodemus, Mariah or Wis-Sur. Sarpling, an additional reagent seller, has the same offer. Each book costs **500 gold**, using the game's normal gold and carrying-capacity checks. Declining or lacking funds creates no book.

New books contain the eight ordinary linear spells and no advanced spells. Advanced spells must be learned separately through the original game. This purchase does not alter the merchant's existing quests or offers.

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
| C Cast | Open the selected member's native spellbook |
| I Gear | Open the selected member's native equipment interface |
| Tab / Hide / Paused Show | Hide or reopen the panel while simulation remains paused |
| Esc | Resume from the panel, or cancel a tactical target/destination picker |
| Right-button press in a tactical picker | Cancel selection and retain the prior order |

Mouse buttons activate when released over the same control. The opening click is consumed before handing control to a target picker or equipment screen. Each actor has one current order; canceled selections retain the prior order. Ordinary right-mouse Avatar movement respects manually commanded companions, so a held companion stays in place. Saves remain native format, and loading starts with automatic companion behavior.

Outside tactical pause, the native C combat shortcut retains its original behavior. If the Avatar has an explicit Hold order, return the Avatar to Auto before using C to end ordinary combat. See `VALIDATION.txt` for the observed native behavior.

## Install or upgrade

1. Exit the game and DOSBox.
2. Extract the complete ZIP into a separate folder.
3. Open a terminal in that folder and run:

```text
python install.py "C:\Games\Ultima7\Blackgat" --check
python install.py "C:\Games\Ultima7\Blackgat"
```

On Linux or macOS use python3 and your game path. The only supported pristine U7.EXE is 689,248 bytes with SHA-256:

```text
4d588b12c775927c77c221531be4910eaf413864a8e2ec3f6f0d7a9c302b6e54
```

Exact original resource hashes and all release hashes are in BUILD.json. Other languages, editions and independent changes are rejected.

The installer changes U7.EXE, MAINMENU.EXE, STATIC/USECODE, STATIC/LINKDEP1 and STATIC/LINKDEP2. It prepares and verifies all five before writing and saves verified originals in TACTICAL-PATCH. Saves, configuration, launcher and difficulty preference are retained. --check makes no game writes. Repeated installation is idempotent.

Exact tactical v1.1 and the older v7 are accepted when a pristine U7.ORI exists in TACTICAL-PATCH or TACTICAL. If your verified original is elsewhere:

```text
python install.py "C:\Games\Ultima7\Blackgat" --original "C:\Backups\U7.ORI"
```

To restore all five original files, exit DOSBox and run:

```text
python install.py "C:\Games\Ultima7\Blackgat" --uninstall
```

Backups and TACTIC.DIF remain. Conflicting backups or unknown game changes cause refusal before replacement. A lock prevents simultaneous installation. A failed replacement rolls back completed replacements. A forcibly terminated multi-file install may be partial; retain the backups, confirm no installer is running, remove a stale INSTALL.lock, and rerun the installer to finish or restore.

## Rebuild and verify

With Python 3.10+ and NASM, reconstruct U7.EXE from your pristine original:

```text
python source/native_patcher.py "/path/to/pristine/U7.EXE" "U7.REBUILT.EXE" --source source
```

Append --nasm with its full path if needed. Create a full patch package, rebuilding the menu and Usecode dependency tables:

```text
python build_distribution.py --original "/path/to/pristine/U7.EXE" --mainmenu "/path/to/pristine/MAINMENU.EXE" --usecode "/path/to/pristine/STATIC/USECODE" --expected "U7.REBUILT.EXE" --source source --version 1.2 --output release --archive Tactical-Patch-1.2.zip
```

The pristine LINKDEP1 and LINKDEP2 must be beside USECODE. The builder verifies them against a byte-identical reconstruction. Installation itself uses the bundled compiled patch objects and requires no assembler.

VALIDATION.txt describes observed DOSBox checks and their limits. This release has focused native and machine-code verification, not a complete campaign playthrough. HANDOVER.md and REVERSE_ENGINEERING.txt explain the implementation. Share the entire patch ZIP, keeping your game and saves separate. Source attribution and the retained upstream notice are in ATTRIBUTION.md and LICENSE-UPSTREAM.txt.
