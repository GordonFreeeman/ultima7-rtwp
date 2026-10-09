# Porting Tactical Patch v1.2.2 to Ultima VII: Revisited

A developer handoff for Anthony Salter and contributors to Ultima VII: Revisited.

## Scope and reference versions

This guide describes how to reproduce the patch's gameplay in Revisited's C++/Lua architecture. It is not a ready-to-compile port, a claim that the features are already implemented in Revisited, or a runtime validation report for that engine.

The source review is pinned to these snapshots, checked on **9 October 2026**:

| Project | Reviewed branch | Exact commit |
| --- | --- | --- |
| Tactical Patch v1.2.2 | `GordonFreeeman/ultima7-rtwp:main` | `7780e5263f023038a46af5642d13b234b686da59` |
| Ultima VII: Revisited | `ViridianGames/U7Revisited:master` | `b80a7d0dd139486ecc0e92413bc32e9f6f0ee8cf` |

The target is Anthony's upstream repository, not a separate fork. All external source links below use these commits. Re-check integration points when working against a later revision; the project's older roadmap is not used as evidence of current implementation status.

**Port the behavior, not the DOS patch machinery.** The cumulative feature set consists of individual-party real-time-with-pause orders, five difficulty choices, companion spellcasting and mana, merchant spellbooks, the graphical difficulty selector, and the improved tactical popup. The [patch README][p-readme] gives the player-facing description; [HANDOVER.md][p-handover] records the native implementation and lifecycle details.

Do not run `install.py` against Revisited or copy patched `U7.EXE`, `MAINMENU.EXE`, `USECODE`, or `LINKDEP` files into it expecting engine changes. DOS addresses, segmented pointers, overlay relocation, spare NPC-buffer bytes, and executable-size guards are implementation constraints of the original game. Revisited needs native C++ state, its own UI, Lua changes, and save migration instead. No proprietary game files are necessary in the port contribution.

## 1. Integration map and current gaps

These are source-level integration candidates, not promises that the current APIs already implement the required behavior.

| Feature | Patch reference | Revisited integration point and remaining work |
| --- | --- | --- |
| Pause and combat mode | `source/pause.asm`, `source/commands.inc` | [CombatMode.h][r-combat], [MainState.h][r-main]: implement `RealTimePauseCombatMode` and connect simulation/input policy. |
| Party orders and path ownership | `source/commands.inc`, `source/weapons.inc` | [MainState][r-main], [U7Object][r-object], [PathfindingSystem][r-path]: connect stable actor selection, movement, equipment validation, targeting, and follow-policy protection. |
| Difficulty rules | [source/v12.inc][p-logic] | Apply a shared policy at the engine's damage and selected ability-decision boundaries. Difficulty must be separate from `CombatStyle`. |
| Companion casting | [source/v12.inc][p-logic] | [U7GumpSpellbook.cpp][r-book], `MainState::OpenSpellbookGump(int npcId)`, Lua spell execution, and actor mana. Audit the entire cast path, not just the book window. |
| Merchant spellbooks | [source/asset_patcher.py][p-assets] | [Lua scripts][r-scripts], existing purchase helpers, and book-instance initialization. Translate the transaction, not the inserted DOS bytecode. |
| Difficulty menu and tactical panel | [menu.asm][p-menu], [panel.inc][p-panel] | [TitleState.cpp][r-title], the existing GUI, and RTwP HUD/input. Rebuild drawing, hit testing, focus, and layout using the same logical rectangles. |
| Persistence and cleanup | `source/commands.inc`, `source/v12.inc` | [GameSerializer.cpp][r-save] and actor/item serialization: persist gameplay data, discard stale runtime references, and handle old saves. |

### Important findings in the reviewed target

`CombatStyle` already distinguishes `Original`, `RealTimePause`, and `TurnBased`. However, `RealTimePauseCombatMode` is a scaffold: it does not override the base `IsImplemented()` result of `false`. The base class also returns `!IsImplemented()` from `IsSimulationPaused()` and `false` from `AllowsPlayerOrders()`. Merely changing `IsImplemented()` to `true` would neither implement pause state nor enable orders. Implement the mode lifecycle, input, HUD, and both policy methods together. [Source][r-combat]

`MainState` already declares `PauseCombatForOrders`, `BeginCombatFighting`, `HandleCombatOrdersClick`, `IssueCombatMoveOrder`, and `MaybeUpdatePartyFollowing`. Several are private. Move responsibilities into the combat-mode/controller layer or expose a narrow interface rather than assuming the strategy class can call them directly. Existing fields include `m_paused`, `m_combatPaused`, and `m_isPopupShowing`; define their interaction instead of adding another unrelated pause switch. [Source][r-main]

The spellbook already has an NPC owner and caster-related logic, but `IsSpellLearned` explicitly describes sandbox unlocking, `Setup` still notes missing learned-spell loading, bookmarks use static storage, and reagent traversal searches party backpacks. These are integration gaps, not a finished equivalent of the patch's per-caster/per-book rules. [Source][r-book]

## 2. Tactical orders: the behavioral contract

The patch opens tactical pause with Space in ordinary world view, including outside active combat. A Revisited implementation restricted to encounters would be a deliberate subset. Preserve exploration-time orders and their lifetime across combat boundaries for full parity.

Each selected actor has **one current order**, not a queue. Party-number buttons select the current roster position, but orders belong to actor identity. Reordering the party must not transfer Jaana's order to another member.

| Order | Meaning | Completion or cancellation |
| --- | --- | --- |
| Automatic | Existing engine AI/follow policy owns the actor. | A confirmed manual command takes ownership. |
| Hold | Stop owned movement and autonomous target acquisition. | A new command or Automatic replaces it. |
| Attack | Maintain the chosen target; existing combat code handles pursuit, reach, hit resolution, ammunition, and effects. | Invalid, dead, or unconscious target becomes Hold. |
| Move | Follow a route to the selected destination. | Arrival or route failure becomes Hold. |

Target uses current equipment. Melee and Ranged validate real equipment and open the existing equipment UI when necessary; they must not manufacture a weapon or ammunition. Gear opens the selected member's inventory. Cast opens that member's spellbook. These are command actions, not additional persistent order types. [Native contract][p-handover]

### Suggested portable state

The following is design notation, not existing Revisited API or compiled code:

```text
ActorHandle = (worldGeneration, objectId)
Order = {
    owner: ActorHandle,
    mode: Automatic | Hold | Attack | Move,
    target: optional ActorHandle,
    destination: optional world position,
    revision: monotonically increasing command number,
    pathRequest: optional owned request/route
}
TacticalSession = {
    selectedActor,
    panelVisible,
    inputMode: Panel | PickTarget | PickDestination | ChildInterface,
    ordersByActor
}
```

Revisited uses both NPC IDs and object IDs. Convert explicitly when opening a book or resolving a party member; do not pass a roster index or object ID to an NPC-ID API. A world-generation check also prevents an old object ID from identifying an unrelated actor after loading.

Maintain the underlying Automatic policy independently of the current manual order. On combat start, refresh the policy that Automatic would restore, without replacing Hold or Move. On combat end, Attack becomes Hold; existing Hold and Move remain. A story-driven departure takes precedence over tactical ownership and must not be undone by restoring an obsolete follow schedule. These transitions are implemented in `tactical_combat_started`, `tactical_combat_ended`, and related ownership helpers. [Source][p-orders]

Protect manual ownership **where follow behavior is assigned**, including `MaybeUpdatePartyFollowing` and relevant movement/schedule writers. Reasserting Hold on the next frame is too late if the actor already moved. Likewise, autonomous target selection must not overwrite an explicit Attack target.

### Pathfinding and command replacement

Canceling a target/destination picker with Escape or right-click preserves the prior order. Keep selection pending until confirmed. For exact native Move behavior, once a valid destination is confirmed the old route is released; failure to build the replacement produces Hold, not restoration of the previous route. [Source][p-orders]

Revisited exposes asynchronous schedule-path requests/results. If tactical movement shares that infrastructure, tag results with world generation, actor identity, and order revision. A result for an abandoned command, a departed/deleted actor, or a previous world must never replace the current route. Workers may calculate immutable routes during pause; applying those results must not advance actor movement. [Target structures][r-main]

## 3. Pause, input, and popup behavior

Simulation pause and panel visibility are different states. Tab/Hide hides the panel while keeping the world paused; Tab/Show reopens it. Space/Resume resumes. Escape cancels a picker first, otherwise resumes from the tactical panel. Closing an inventory or spellbook opened from tactical pause returns to that pause, not to running simulation. [Native UI contract][p-handover]

Use a single authoritative pause policy, ideally composed from pause reasons or scoped ownership. A child UI must not clear a pause owned by its parent. Gate world movement, combat progression, projectiles, NPC schedules, simulation-time script callbacks, and mana regeneration consistently. Rendering, mouse input, camera inspection, and UI animation can continue. Rebase wall-clock bookkeeping on resume so paused time does not become one large catch-up simulation step.

The patch executes selected spellbook actions inside the paused modal. This is explicit player-directed mutation, not autonomous world ticking. Revisited should allow the authorized spell action while keeping unrelated simulation paused. A deferred spell-action queue that executes only after Resume would be a different design.

The native popup is 216 by 120 pixels on a 320 by 200 screen. Its nine command buttons are 64 by 14, with six-pixel horizontal and four-pixel vertical gaps. These are reference proportions, not dimensions to hardcode into the 3D UI. Preserve readable labels, padding, inactive gaps, selection/order feedback, drag bounds, and the hidden-paused indicator. Measure text in Revisited's actual font and use the same transformed bounds for drawing and hit testing. [Source][p-panel]

A click activates only after press and release on the same control; releasing elsewhere cancels. Consume the opening click when handing control to a target picker or equipment window. Neither the same click nor an already-held button should also select a world target, drag inventory, or move the Avatar. Resolve picker cancellation before global Escape handling. Test scaled rendering, screen edges, and the longest labels.

## 4. Difficulty: exact rules and numerical fixtures

Use a separate five-value difficulty setting. Revisited's three-value `CombatStyle` selects a combat system and must not be overloaded with difficulty.

| Stored value | Display label | Factor F | Effective enemy durability | Enemy outgoing damage |
| --- | --- | ---: | ---: | ---: |
| 0 | Game Journalist | 25 | 25% | 25% |
| 1 | Easy | 75 | 75% | 75% |
| 2 | Normal | 100 | 100% | 100% |
| 3 | Hard | 125 | 125% | 125% |
| 4 | Avatar | 200 | 200% | 200% |

These factors modify damage, not stored/displayed maximum HP. Do not also multiply HP, which would double-apply durability. [Implementation][p-logic]

### Damage boundary

The original hook classifies **party versus nonparty**, not hostility. A neutral nonparty NPC is consequently in the same branch as an enemy. Exempting neutrals in Revisited is a possible design change, not exact patch parity.

For a positive native damage input `d`, use wide integer intermediates:

```text
Normal, nonpositive damage, or a missing attacker:
    preserve the original damage
Party -> party, or nonparty -> nonparty:
    preserve the original damage
Nonparty -> party:
    applied = min(127, max(1, floor((d * F + 50) / 100)))
Party -> nonparty, with recipient remainder r:
    n = d * 100 + r
    quotient = floor(n / F)
    recipient.remainder = n mod F
    applied = min(127, quotient)
```

A recipient's remainder begins at zero and accumulates across hits, including hits from different party attackers. Zero applied damage on one small hit is intentional; later hits recover the fraction. Do not clamp each of these hits to at least one, or Hard/Avatar durability will be wrong. The native fallback for a recipient without a ledger slot, or failed ledger allocation, applies at least one instead. A modern actor-keyed ledger can avoid that limitation. [Implementation and native state][p-logic]

The 127 cap is a DOS signed-byte constraint. Preserve it for a compatibility policy; using Revisited's wider damage range is a documented deviation. Normal bypasses the transformation. Do not apply scaling twice through both C++ damage and a Lua wrapper, or scale healing, equipment base damage, and final damage independently.

Golden vectors for positive damage of 40, with a fresh recipient ledger:

| Difficulty | Nonparty -> party | Party -> nonparty | Remaining fraction |
| --- | ---: | ---: | ---: |
| Game Journalist | 10 | 127 | 0 |
| Easy | 30 | 53 | 25 |
| Normal | 40 | 40 | unchanged |
| Hard | 50 | 32 | 0 |
| Avatar | 80 | 20 | 0 |

Five successive one-point party hits on Hard produce `0, 1, 1, 1, 1`. On Avatar, six such hits produce `0, 1, 0, 1, 0, 1`. Keep separate ledgers for separate recipients. Clear the ledger when replacing the world. The DOS setting is fixed for the running game; a new in-session difficulty control should explicitly reset or convert remainders on change.

### Powerful enemy abilities

Only the hooked native teleportation, invisibility, and summoning chance checks change. This is not a new spell list for every enemy or a multiplier for all AI randomness.

Game Journalist suppresses these checks throughout the story and does not consume a random draw. Before magic restoration, the other modes retain the original bounds. After restoration, transform each original random bound `B` as follows: Easy `2*B`, Normal `B`, Hard `floor(2*B/3)`, Avatar `floor(2*B/5)`. Preserve the original caller's success comparison and RNG range convention. A smaller bound is not by itself a universally defined probability multiplier. [Source][p-logic]

For `B=60` after restoration, the bounds are disabled, 120, 60, 40, 24. Before restoration they are disabled, 60, 60, 60, 60. Normal adds no extra random draws. If adapting this helper to new ability checks with very small bounds, handle a zero transformed bound explicitly; do not assume the audited DOS call sites' ranges apply everywhere.

The story gate is the original Tetrahedron Generator completion flag, numbered 3 in the patch. Revisited's [Nystul script][r-nystul] also consults `get_flag(3)` for magic-related dialogue. Bind a named progression predicate to the actual completion event and verify its save/load behavior; do not copy the DOS bitmask or memory address, and do not set the flag merely to enable a menu option.

### Main-menu interaction and persistence

Display `Difficulty: <label>` alongside the normal start/continue actions. Mouse activation and Up/Down plus Enter must cycle the same value, wrap Avatar to Game Journalist, and use the normal hover/focus highlight. The entire visible label must be clickable, including Game Journalist. Returning from a canceled child screen must redraw the current label immediately. [Native v1.2.2 implementation][p-menu]

The patch defaults missing/invalid preferences to Normal and saves a single raw byte, 0 through 4, in `TACTIC.DIF`. It reads that preference for the next loaded or new game in the process; it is not a per-save difficulty field. Revisited can store the equivalent validated value in its configuration instead. A raw-byte importer is optional. Document any different per-save or live-change policy so loading cannot silently override the visible selection.

## 5. Companion spellcasting and spellbooks

For parity, the Avatar keeps ordinary casting rules. Companion casting unlocks after the Tetrahedron Generator event for **Jaana, NPC 5**, and **Mariah, NPC 153, if already in the party**. This patch does not make Mariah recruitable or grant magic to every companion. Resolve NPC IDs to live actor objects and reject invalid or unavailable selected casters. [Source][p-logic]

A companion needs an actual spellbook in their own inventory, including nested containers, the spell learned in that book, sufficient level/mana, and the required reagents in their own inventory. Preserve normal target validation and spell effects. Buying advanced spells through the DOS merchant UI still uses the Avatar's book, which can then be passed to a companion. Direct purchases for another caster would be a useful enhancement, but are not provided by the patch. [Contract][p-readme]

### Revisited-specific work

Use the book's owner/caster context throughout validation, targeting, cost consumption, and Lua effects. Replace sandbox learned-spell acceptance with real book-instance data. Store learned circles and bookmarks on the book, not in one process-wide static variable. A transferred book retains its learned spells; a fresh book must not inherit a previously opened book's state. Replace party-wide reagent searches with caster-scoped traversal for parity. [Current target implementation][r-book]

The DOS implementation temporarily substitutes the selected companion for a global Avatar reference during its synchronous spellbook modal. **Do not reproduce that substitution in Revisited.** Pass explicit caster identity to spell execution, including delayed callbacks/projectiles. Audit Lua effects for hardcoded Avatar references: correct mana deduction alone does not establish correct healing targets, projectile origin, ownership, or self-cast behavior. Use scoped cleanup for success, cancellation, script failure, and world replacement.

Validate costs against the current inventory before committing the cast, then consume them exactly once according to the normal spell transaction. Cancellation before cast commitment must not consume costs. A valid cast that fizzles under normal game rules is distinct from canceling the picker; retain the engine's intended failure-cost policy.

### Mana and time

Native companion capacity initializes once from the five-bit intelligence value, `max(8, intelligence & 31)`, with current mana initially full. Existing initialized mana is not refilled whenever the book opens. The patch stores marker/capacity and current mana in spare DOS NPC bytes; use explicit versioned fields in Revisited instead. [Source][p-logic]

After magic restoration, eligible party companions regenerate up to capacity while simulation runs. The native update checks for at least 16 game-clock units since its last check, adds at most one point, and resets its timestamp to the current clock. It does **not** loop to award several points after a large clock jump. Those units are not asserted here to be seconds or rendering frames. Calibrate against the simulation clock. A continuous accumulator/catch-up model is an intentional modernization; pause must never generate mana in either model.

## 6. Merchant spellbooks

The patch adds a `spellbook` conversation option to six merchants, without replacing their original quests or offers:

| Merchant | Original Usecode function |
| --- | --- |
| Nystul | `0x418` |
| Rudyom | `0x44A` |
| Nicodemus | `0x466` |
| Mariah | `0x499` |
| Wis-Sur | `0x4D8` |
| Sarpling | `0x4BC` |

Each purchase costs **500 gold** and creates one shape-761 spellbook with the eight ordinary linear spells, no advanced spells, and a cleared bookmark. The native allocation hook initializes newly allocated books generally, not just merchant purchases. Existing books and loaded learned-spell data must remain untouched. [Transaction and merchant IDs][p-assets]; [book initialization][p-logic]

In Revisited, adapt the corresponding [Lua conversations][r-scripts]. A verified example is `npc_nystul_0024.lua`; locate the others by merchant identity, not by assuming DOS function IDs are Lua filenames or runtime object IDs. Keep original dialogue availability and story gates. An added offer must not bypass a merchant's normal refusal to converse.

Use a shared purchase operation: confirm, validate funds and carrying capacity, prepare the initialized book, and commit gold deduction plus inventory insertion as one logical transaction. On decline, insufficient funds, insufficient capacity, or creation failure, leave both inventory and gold unchanged. Repeated purchases should create exactly one independent book each. Restore the outer conversation's answers after the confirmation dialog.

Do not port the DOS helper ID `0xB00`, binary branch rewriting, or `LINKDEP` reconstruction into Lua. Those exist to patch the original bytecode VM, not to define the merchant behavior.

## 7. Save/load and lifecycle boundaries

Separate persistent gameplay data from session ownership. For parity, mana and learned book data survive saves; tactical orders, target references, owned routes, and damage remainder ledgers are runtime state. Loading starts with Automatic orders. Revisited uses its own serialization; retaining gameplay semantics does not make its saves DOS-compatible. [Native lifecycle][p-handover]; [target serializer][r-save]

Saving or canceling a save dialog must preserve the running session's orders. Serialize ordinary actor policy rather than a temporary tactical override that could leave a character frozen after reload. Canceling a load confirmation preserves current orders. Once a load is confirmed, invalidate old-world selections, callbacks, path requests, and temporary caster state before replacing world data. Clear stale references even when a failed load leaves the old world visible.

Add backward-compatible defaults for newly serialized mana/book fields without repeatedly refilling initialized characters or erasing learned spells. Validate ranges on load. Do not retain raw object pointers across world replacement. `RebuildWorldFromLoadedData` and serializer entry points are useful audit locations, but cleanup must also cover new-game, quit, and aborted load paths. [Target interface][r-main]

## 8. Suggested integration sequence

1. Establish the shared tactical controller, pause ownership, stable handles, and UI input routing. Keep exploration orders outside an encounter object's lifetime; let `RealTimePauseCombatMode` delegate to that controller.
2. Implement Hold, Move, Attack, Automatic, equipment checks, follow-policy protection, and asynchronous result rejection. Validate actual movement/damage, not only HUD labels.
3. Add the independent difficulty policy and main-menu setting, with numerical and RNG regression tests.
4. Finish per-book learned state, explicit caster propagation, mana persistence/regeneration, and caster-local reagents. Then adapt merchant conversations through one transaction helper.
5. Validate save migration, every cancel/return path, and the other combat styles. Keep new behavior configurable rather than silently changing Original mode.

This ordering is a proposed porting workflow. No Revisited implementation or executable is delivered by this documentation change.

## 9. Acceptance checklist for the port

The following are **tests to implement/run in Revisited**, not claims of passing engine tests. Use deterministic clocks/RNG and mocked inventory/path services for unit tests, then exercise the real UI, scripts, combat, and serializer.

| ID | Scenario | Expected result |
| --- | --- | --- |
| T01 | Space in exploration and combat | Tactical UI opens; simulation stops; UI remains responsive. |
| T02 | Hide, reopen, open/close inventory, Resume | Hide and child close retain pause; Resume releases only the tactical pause reason. |
| T03 | Assign different orders, then reorder party | Commands remain with their actors. |
| T04 | Hold a companion, move Avatar normally | No follow step, teleport, or autonomous attack replaces Hold. |
| T05 | Cancel target/destination with Escape or right-click | Prior order and route survive; cursor/input capture are restored. |
| T06 | Confirm unreachable Move; replace Move while path is pending | Failure becomes Hold; obsolete results cannot overwrite a newer order. |
| T07 | Attack with Avatar and companion, melee and ranged | Correct target takes real damage; ammunition/equipment rules apply. |
| T08 | Target dies; actor departs; actor becomes unavailable | Orders release/transition safely; story/death behavior wins. |
| T09 | Start/end combat with Hold, Move, and Attack active | Hold/Move persist; ending combat converts Attack to Hold; Automatic restores the right current policy. |
| T10 | Press inside button, release outside; click a gap | No action; opening clicks do not leak into child/world input. |
| D01 | Run the damage table and one-point sequences above | Exact values and per-recipient remainders match the selected compatibility policy. |
| D02 | Friendly fire, nonparty pairs, no attacker, zero/negative damage | Unmodified damage; neutral/nonparty treatment is explicitly covered. |
| D03 | All five ability modes before/after story event | Expected bounds; suppression draws no RNG; Normal preserves draw count. |
| D04 | Mouse and keyboard cycle all labels, including wraparound | Identical preference, proper hover/focus, full-label click area, no duplicate activation. |
| D05 | Cancel character creation; relaunch; malformed preference | Immediate redraw, persistence, and Normal fallback. |
| M01 | Avatar, Jaana, Mariah, and noncaster; before/after flag | Correct eligibility; no new recruitment or premature companion unlock. |
| M02 | Missing book, unlearned spell, insufficient level/mana/reagent | No unauthorized cast or partial consumption. |
| M03 | Reagents only on another member versus nested on caster | Other member cannot subsidize the cast in parity mode; caster's nested reagents work. |
| M04 | Cast self/targeted spells as a companion; cancel or fail script | Correct caster/effect origin; costs occur once; Avatar identity stays unchanged. |
| M05 | Transfer/reopen books; buy a new book | Learned state stays with the correct book; no shared bookmark/unlock leakage. |
| M06 | Advance clock by 15, then 1 unit; pause; make a large jump | Capacity bound and chosen native/catch-up timing policy are respected; no pause regeneration. |
| S01 | Each merchant: decline, 499 gold, full inventory, creation failure | No gold lost and no book added on failure. |
| S02 | Successful and repeated purchases, including 500 gold exactly | One initialized book per successful purchase; exactly 500 gold charged each time. |
| S03 | Existing merchant quests and refusal branches | Original availability and conversation behavior remain intact. |
| L01 | Save/cancel while moving or attacking; cancel load | Running orders remain valid without simulation advancing inside the modal. |
| L02 | Confirm load/new game with pending paths or spell callbacks | No stale callbacks or pointers; new session starts Automatic. |
| L03 | Load old/new saves with mana and learned books | Defined migration; no refill exploit or learned-spell loss. |
| R01 | Original and Turn-Based styles; scaled UI and screen edges | No accidental mode changes, input regressions, clipped controls, or off-screen panels. |

The repository's [native tests][p-tests] and [VALIDATION.txt][p-validation] concern the DOS patch. Machine-code stubs, byte-identical rebuilds, and successful DOSBox checks do not establish Revisited correctness. Use their cases as references, not as a substitute for executing the port's tests.

## 10. Sharing, attribution, and licensing

Share this guide, the patch source, and the existing technical handover. For reproduction, recipients can apply the patch locally to their own supported original installation. Do not include proprietary game executables, resources, or personal saves in a Revisited source contribution.

At the reviewed patch snapshot, `LICENSE-UPSTREAM.txt` retains John Glassmyer's MIT notice for adapted upstream material, while `ATTRIBUTION.md` distinguishes the newly developed patch code. There is no separate root license explicitly covering all new contributions. Revisited's own [license][r-license] is BSD-2-Clause. Keep upstream notices and clarify permission for any newly authored code being copied or adapted before redistribution; public visibility alone is not a blanket reuse license. See [GitHub's licensing guidance][gh-license] and the patch's [attribution][p-attribution].

**This document does not select a license, relicense either project, or grant rights to Ultima VII assets.** Licensing clearance is separate from technical portability. No license files, engine code, patch objects, installers, or release metadata are changed by adding this guide.

## Source references

Patch links identify the cumulative v1.2.2 source snapshot. Revisited links identify the target snapshot inspected for this guide. Proposed structures, integration ordering, and acceptance scenarios above are recommendations, not pre-existing APIs or test results.

[p-readme]: https://github.com/GordonFreeeman/ultima7-rtwp/blob/7780e5263f023038a46af5642d13b234b686da59/README.md
[p-handover]: https://github.com/GordonFreeeman/ultima7-rtwp/blob/7780e5263f023038a46af5642d13b234b686da59/HANDOVER.md
[p-orders]: https://github.com/GordonFreeeman/ultima7-rtwp/blob/7780e5263f023038a46af5642d13b234b686da59/source/commands.inc
[p-logic]: https://github.com/GordonFreeeman/ultima7-rtwp/blob/7780e5263f023038a46af5642d13b234b686da59/source/v12.inc
[p-assets]: https://github.com/GordonFreeeman/ultima7-rtwp/blob/7780e5263f023038a46af5642d13b234b686da59/source/asset_patcher.py
[p-menu]: https://github.com/GordonFreeeman/ultima7-rtwp/blob/7780e5263f023038a46af5642d13b234b686da59/source/menu/menu.asm
[p-panel]: https://github.com/GordonFreeeman/ultima7-rtwp/blob/7780e5263f023038a46af5642d13b234b686da59/source/panel.inc
[p-tests]: https://github.com/GordonFreeeman/ultima7-rtwp/tree/7780e5263f023038a46af5642d13b234b686da59/tests
[p-validation]: https://github.com/GordonFreeeman/ultima7-rtwp/blob/7780e5263f023038a46af5642d13b234b686da59/VALIDATION.txt
[p-attribution]: https://github.com/GordonFreeeman/ultima7-rtwp/blob/7780e5263f023038a46af5642d13b234b686da59/ATTRIBUTION.md
[r-combat]: https://github.com/ViridianGames/U7Revisited/blob/b80a7d0dd139486ecc0e92413bc32e9f6f0ee8cf/Source/CombatMode.h
[r-main]: https://github.com/ViridianGames/U7Revisited/blob/b80a7d0dd139486ecc0e92413bc32e9f6f0ee8cf/Source/MainState.h
[r-object]: https://github.com/ViridianGames/U7Revisited/blob/b80a7d0dd139486ecc0e92413bc32e9f6f0ee8cf/Source/U7Object.h
[r-path]: https://github.com/ViridianGames/U7Revisited/blob/b80a7d0dd139486ecc0e92413bc32e9f6f0ee8cf/Source/PathfindingSystem.h
[r-book]: https://github.com/ViridianGames/U7Revisited/blob/b80a7d0dd139486ecc0e92413bc32e9f6f0ee8cf/Source/U7GumpSpellbook.cpp
[r-scripts]: https://github.com/ViridianGames/U7Revisited/tree/b80a7d0dd139486ecc0e92413bc32e9f6f0ee8cf/Redist/Data/Scripts
[r-nystul]: https://github.com/ViridianGames/U7Revisited/blob/b80a7d0dd139486ecc0e92413bc32e9f6f0ee8cf/Redist/Data/Scripts/npc_nystul_0024.lua
[r-save]: https://github.com/ViridianGames/U7Revisited/blob/b80a7d0dd139486ecc0e92413bc32e9f6f0ee8cf/Source/GameSerializer.cpp
[r-title]: https://github.com/ViridianGames/U7Revisited/blob/b80a7d0dd139486ecc0e92413bc32e9f6f0ee8cf/Source/TitleState.cpp
[r-license]: https://github.com/ViridianGames/U7Revisited/blob/b80a7d0dd139486ecc0e92413bc32e9f6f0ee8cf/LICENSE
[gh-license]: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository
