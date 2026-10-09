# Programmer handover: Tactical Patch v1.2.2

## Current release and rebuild baseline

Version 1.2.1 updates the supplied working independent v1.2 release. Its two game-file changes are U7.EXE (panel geometry) and MAINMENU.EXE (a Difficulty control inside the native graphical menu). The supplied v1.2 source was first rebuilt byte for byte, including its executable, pre-menu selector and Usecode output. The v1.2 damage, companion casting, mana and merchant implementations remain the baseline for this UI update.

The full game retains pristine U7.ORI, MAINMENU.ORI, USECODE.ORI, LINKDEP1.ORI and LINKDEP2.ORI under Blackgat/TACTICAL-PATCH. The source builder accepts those backup names directly. The installer recognizes the exact supplied v1.2 executable and main-menu hashes and rebuilds both from verified originals. Unknown independent modifications are rejected before game writes. Current observed checks belong to VALIDATION.txt and VALIDATION.json; historical implementation notes below describe the retained mechanics.

This native DOS modification demonstrates a tactical command layer for individual party members in Ultima VII: The Black Gate. Anthony can inspect `commands.inc` for the order state model, `panel.inc` for the pause interface, and `pause.asm` for lifecycle ownership, then implement those behaviors through the remake's actor, path, combat, UI, and save/load APIs. The executable addresses, segmented-memory conventions, register preservation, and Borland overlay hooks are specific to the supported DOS build.

## Player-visible contract

The world can be paused for issuing commands to individual party members. A member has one current order: automatic behavior, hold, attack a selected actor, or move to a selected position and then hold. Assigning another order replaces that member's current order. Other members keep their own orders.

Selection numbers are presentation: they refer to the current party roster. An order belongs to an actor identity, so party reordering cannot transfer a command to a different actor. Names and equipment come from live game state.

Equipment selection uses the existing inventory interface. Melee and ranged commands validate what the member actually has equipped; they do not spawn equipment or ammunition. The general attack command retains the native handling of hybrid weapons. Esc or a right-button press cancels a tactical target/destination picker and retains the prior valid order. The order should be committed only after its selection and validation succeed.

The pause UI lets the player inspect and assign orders while simulation time is stopped. Inventory and interface timing can continue using a separate wall clock. Resuming permits normal simulation to execute all assigned orders. Native reach, collision, ammunition, damage, and actor status rules remain authoritative.

The native panel is 216 by 120 pixels within the 320 by 200 game screen. Its default position is x=4, y=76 at the bottom left. The nine command buttons are 64 by 14 pixels, separated by six-pixel column gaps and four-pixel row gaps. It shows the selected member, current order, target when applicable, equipment hint, party selection buttons, and command buttons. Left-button press and release over the same control activates it; release elsewhere cancels the click. Gaps and unoccupied party slots are inactive. Dragging the title moves the panel within x=0..104 and y=0..80, with its position remembered and clamped while the process runs. Tab or Hide removes the panel while keeping simulation paused; the Paused Show control or Tab reopens it. Space/Resume resumes the world. In a remake, keep panel visibility and simulation pause as separate state variables.

Before transferring input to a native target picker, equipment dialog, or resumed world, the panel drains its mouse event queue and waits for held buttons to release. This prevents the click that opened a child interface from also selecting a target or beginning an inventory drag. The same input ownership rule applies to a remake's event dispatch, even when its mouse coordinates and UI framework are different.

The original picker in native segment 234 has no keyboard or right-button cancellation. A guarded 53-byte event-dispatch patch routes its input through the tactical wrapper. While the tactical modal is active, Esc or a right-button press takes the original cursor-restoration and return path with an uncommitted selection. This retains the previous command and restores the native cursor correctly. A remake can implement the same behavior as a canceled picker result with cursor cleanup owned by the picker lifecycle.

## State model

| State | Execution policy | Transition |
| --- | --- | --- |
| Automatic | Original companion behavior owns the actor | Manual command takes ownership |
| Hold | Stop owned movement and prevent autonomous attack selection | New order or return to automatic |
| Attack | Maintain the explicit selected target; native combat executes the action | Target becomes invalid/dead/unconscious → hold; new order replaces it |
| Move | Advance the route toward the selected destination | Arrival or route failure → hold; new order releases the old route |

The native implementation uses compact per-actor records with actor identity, mode, target identity, owned-route pointer, and the native schedule/attack policy that must be restored when manual control ends. A remake can express these as ordinary objects, stable entity handles, and explicit ownership instead of raw DOS pointers.

The actor's automatic policy and the tactical order are different kinds of state. Temporarily applying a manual order should not erase the policy needed to return that actor to ordinary companion behavior. The verified native start/end lifecycle helpers synchronize the stored ordinary policy after the original combat transition has actually executed: party follow schedule 31 becomes combat schedule 0 on start, and combat 0 becomes follow 31 on end. A held or moving actor remains on its explicit order while its stored return-to-automatic policy tracks that real transition.

Ending native combat changes an explicit attack order to hold and clears its target. Existing hold orders and owned move routes remain active. The helpers update only the ordinary party 0/31 policies and preserve other native schedule types, including departure behavior. They do not infer combat phase from the Avatar's temporary wait schedule: the Avatar can be held while a companion is still executing an explicit attack. A remake can use its combat-started and combat-ended events to apply the same state transitions.

## Update order and responsibilities

At each unpaused world step, resolve the actor and target identities against the current world. Check party membership and native actor status before enforcing an order. Obtain fresh actor data after any call that can invalidate a cache entry; never retain a borrowed cache pointer across such calls.

For hold, stop only the actor's owned action state. For attack, maintain the explicit target while leaving the engine's attack, pursuit, range, hit, damage, projectile, and ammunition code in charge. An explicit target must have priority over autonomous target choice. The Avatar and companions may use distinct native branches; each branch needs its own execution evidence.

Manual ownership must also survive ordinary Avatar movement. The native right-mouse movement owner at resident 4:07AB can reset the entire party to follow schedule 31 when the Avatar has a nonstandard schedule. Reapplying hold at the next tactical tick is too late: a companion can move for one frame after that reset. The guarded wrapper uses `tactical_preserve_manual_follow` to permit the native reset for the Avatar and automatic followers while skipping explicitly commanded companions. It resolves their stable identity without allocating new tactical records. In a remake, check manual command ownership at the follow-policy mutation itself, so an unrelated movement event cannot briefly replace hold, attack, or owned move.

For move, construct a path for the selected actor and advance it during simulation. Own the path explicitly: replacing, canceling, finishing, exiting, or removing an actor must not leak or double-free it. Canceling the destination picker retains the prior command. Once a destination is confirmed, this implementation releases the previous route; construction failure results in hold, which appears in the current order status.

Normal native events can take priority. A departing companion must keep the departure schedule established by game scripts; releasing tactical ownership must not force it back into the party's former follow/combat schedule. Dead, unconscious, deleted, or otherwise unavailable actors cannot be treated as healthy commanded members.

## Save, cancel, exit, and load

Orders are runtime session state. This implementation preserves the original save format rather than serializing extension records or heap pointers into a save.

| Event | Required lifecycle |
| --- | --- |
| Open save UI | Suspend manual enforcement and restore ordinary native schedules/attack policy before serialization |
| Save or cancel without loading | Reapply the session's pending orders; do not advance routes merely because the UI opened |
| Exit through the modal | Release orders and owned routes |
| Confirm load | Release old-world routes while the old heap still exists, then run the native loader |
| Loader returns | Clear extension records without dereferencing any old-world pointer |
| Fresh game process | Initialize empty tactical state |

After loading, companions start in automatic behavior and the player can issue fresh orders. Loading a save can replace the world in place or restart the executable via the launcher; both paths need a lifecycle owner. Canceling a load confirmation retains orders. Once the confirmed native load has begun, old orders are released even if that load later fails.

For a new engine, a world generation identifier on entity handles can make stale references fail safely. An explicit pre-load cleanup followed by a post-load reset remains useful even with managed memory, because subscriptions, routes, UI selections, and scheduled jobs also refer to the old world.

## Native implementation boundaries

- `pause.asm` owns world input interception, the blocking modal, the simulation-step callback, and save/restore wrappers.
- `commands.inc` owns actor selection, command commit/cancel, route ownership, enforcement, automatic policy restoration, and session lifecycle.
- `panel.inc` owns compact panel drawing, visibility, party/command button hit testing, mouse event ownership, and title-bar dragging.
- `weapons.inc` validates actual equipment through native accessors.
- `tactical_combat_started` and `tactical_combat_ended` synchronize stored ordinary policies after guarded native combat transitions; ending combat cancels attack orders while preserving explicit hold and move.
- `tactical_preserve_manual_follow` protects manual companion ownership at the native Avatar movement reset, while the tactical picker wrapper owns Esc/right-button cancellation and native cursor cleanup.
- `source/native_patcher.py` parses the supported MZ/FBOV file, expands a loader-managed overlay, applies guarded patch blocks, and repairs relocation metadata.
- `install.py` applies preassembled objects without requiring NASM. Original overlay code and relocations are copied from the recipient's own pristine executable at installation time.

The v1.2 patch retains the native engine, pathfinding, save format and ULTIMA7.COM launcher. It patches native damage inputs, MAINMENU.EXE and the merchant Usecode functions with their two dependency tables. Its native code references documented routines and fixed addresses for one hash-identified executable. Porting those offsets to another executable or treating them as stable interfaces is unsafe.

## Useful acceptance scenarios in another engine

Pause after issuing a move and confirm that world positions, projectiles, and simulation ticks stop while interface timers remain usable. Hide and reopen the panel with Tab and mouse controls, and verify that hiding never resumes the world. Drag the panel and confirm bounded placement without a world action. Issue different commands to multiple members and verify independent execution after resume. Reorder the party and confirm that orders remain attached to the same actors. Cancel target and destination pickers with Esc and with a right-button press; confirm that each returns to the paused interface, restores the cursor, and retains the prior command.

Hold a companion, resume, and move the Avatar with the ordinary right-mouse input. Observe the companion over individual updates and confirm it never takes an uncommanded step. Repeat with an owned move and an explicit attack to confirm that the Avatar's movement does not replace those orders with automatic following.

Exercise attack orders separately for the Avatar and companions, with melee and ranged equipment. Confirm actual damage/ammunition use and target continuity, not just an attack animation or a displayed status. Test a moving target, a dead/unconscious target, no ammunition, inaccessible terrain, and a changed weapon.

Start and end ordinary combat while an actor holds or moves. Returning it to automatic afterward must use the current ordinary policy. Confirm that an actual combat end cancels attack into hold while an owned move route and an explicit hold remain in place.

Save and cancel while moving and attacking; pending session commands should resume. Load both through the inventory/save modal and a fresh launcher process; commands should clear and no old-world route may be released after the heap has been replaced. Remove a commanded companion through a native story event and verify that the script's departure behavior remains in control.

The distribution's build identity does not substitute for these runtime observations. Review the release's separate validation report if provided by its author.


## v1.2 difficulty and magic implementation

`v12.inc` owns the new mechanics. `v12-state.inc` reserves DS:1064..106E within the audited build-stamp space. A D2 signature initializes the boot difficulty (0..4, default 2), near damage ledger, active caster, mana tick and modal load marker. The menu and engine use the same one-byte TACTIC.DIF file.

The 219:0008 damage hook borrows the native caller BP and modifies only its positive signed damage byte. Party membership uses actual IBOs. Enemy incoming damage uses inverse factors with a near heap remainder indexed by NPC ID; enemy outgoing damage uses factors 25/75/100/125/200. The ledger is cleared on restoration and never saved. Unknown actor IDs and allocation failure fall back to a minimum one-point hit.

Six RNG sites in overlay 219 own innate teleportation, invisibility and summoning. Game Journalist returns a failing sentinel without consuming RNG. Other settings consult original global flag 3. Normal passes the exact native bounds and preserves the original RNG stream. The native flags object is inline at DS:5F9C, with the far flags pointer at +4, count at +8 and flag 3 in first-byte bit 10h. Treating DS:5F9A as a near object pointer is incorrect.

Caster IDs are Jaana 5 and Mariah 153. C uses a synchronous native spellbook modal and temporarily makes DS:4C0C refer to the selected companion, so original spell Usecode Avatar references resolve to the caster. No simulation step runs in the book modal. The true Avatar is restored on return and before native save UI. Confirmed load clears caster state and prevents the old IBO being restored into the new world.

Companion mana occupies unused bytes +0D (80h initialization marker plus capacity) and +0E (current mana) in the original 105-byte NPC buffer. Native +0F/+10 are identity/flags and are never repurposed. Two native mana reads and the write in overlay 215 switch to +0E during a companion cast. The write hook uses retf 2 to consume the original pushed mana value exactly. FS/GS unreal-mode caches are preserved. Saved mana uses native U7NBUF.DAT serialization, without a new save format.

The added far calls exhaust overlay 215's original relocation tail. The bounded patcher relocates its entire unchanged-offset code image to the end of FBOV with a larger relocation table and repairs its descriptor. Overlay 336 remains the loader-owned extension. Hooks dispatch by guarded private return sites before adding a wrapper frame.

## v1.2 menu and merchant resources

The original v1.2 `menu/menu.asm` was a BIOS/DOS selector before the graphical menu. Version 1.2.1 replaces that source with a resident extension to MAINMENU's own graphical widget list. It adds a Difficulty text widget, retains the six original action IDs, and saves the same one-byte TACTIC.DIF preference. MAINMENU's original entry and self-size check remain active. The native CRT's BSS clear boundary is preserved while its near heap/stack boundary is moved above the appended payload. Explicit MZ relocations resolve the native function pointers. The detailed v1.2.1 hook notes below take precedence over any historical pre-entry-selector description.

`asset_patcher.py` preserves all original Usecode records except the six named merchants. It appends a string and an extern to each and inserts a self-contained conversation case. All original branch destinations are remapped by instruction boundary. Own function B00 calls the original Yes/No (90A) and purchase helper (8F8), charging 500 gold with native capacity and funds checks.

Every inserted Usecode byte shifts later file offsets. Both LINKDEP tables must therefore be rebuilt: sorted transitive extern closures, total body sizes and four-byte file offsets. Reconstructing the original tables matches both pristine files byte for byte. Shipping a modified USECODE with old LINKDEP tables crashes the DOS VM.

Fresh native spellbook allocations retain free-list bytes unless initialized. The guarded resident 86:1CDB hook initializes only newly allocated shape 761: circle 0 FF, circles 1..11 zero and bookmark zero, preserving linked block pointers and quality. Existing books are never cleared; native deserialization supplies existing learned data.

The distribution carries our code and resource algorithms, not original functions or tables. The installer validates all five original and output identities before mutations, makes exclusive verified backups, atomically replaces each file and rolls back earlier replacements if a later one fails. Abrupt process termination across five files cannot be made a single filesystem transaction; rerunning against verified backups repairs partial installation.

Tests are supplied under tests. `test_assets.py --game-root <pristine-folder>` checks preservation and dependency reconstruction. `test_install.py` accepts distribution, pristine original, a supported previous executable, pristine asset folder and report paths; `--previous-game` additionally checks the supplied v1.2 menu upgrade and exact game-file preservation. `test_native.py --executable <rebuilt-U7.EXE>` requires Python Unicorn and executes actual assembled 16-bit code with narrow native service stubs. `source/check_panel_geometry.py <game-folder> --nasm <nasm-path>` reads the game's real font metrics and checks assembled panel hit testing, drag limits, release/cancellation and text insets. Native DOSBox fixtures used during development are disposable and are excluded from the package.

## v1.2.1 native menu integration

The exact supported pristine MAINMENU.EXE is 127,116 bytes, SHA-256 `73d88ccdb103ee3c6ead70e64ed41eefa9312875ded98d93829979e2a511f43c`. Its MZ load image starts at file offset 0x2200. The original entry remains 0000:0000. `asset_patcher.patch_menu` guards every modified instruction and the original 2,112 relocation records before constructing the output.

`menu/menu.asm` carries a `U7NDIF2` version-2 manifest with creation, poll and cleanup entry offsets and nine native pointer segment locations. The payload is placed at load-image offset 0x1D830, after the old BSS boundary DS:5AA0 for data segment 17D9. Startup's BSS clear still ends at DS:5AA0. The CRT allocation operand at image offset 006B and the near heap break words at DS:009A and DS:009C move to the paragraph-aligned end of the payload. The stack/near heap reservation at DS:4D62 grows from 1000h to 4000h, which accommodates the original large menu frame, its child frames and the new widget. The initial MZ stack moves above the extension while preserving its original SP of 0080h. The MZ file size, minimum allocation and original executable self-size comparison are repaired together. Ten additional MZ relocations cover the new creation call and nine appended native pointers.

The original owner frame grows from 1DFCh to 1E60h at image offset 565A. DS equals SS in this native frame. The added 5Eh-byte text widget is at BP-1E60h, the parent screen is at BP-12D8h, and the original action list is at BP-1560h. Creation at image offset 5BEE uses the already loaded MAINSHP resource-9 font, the native text constructor/alignment/position methods and native action-list insertion. Difficulty uses action ID 14. All six existing action IDs and image resources are retained; their vertical positions become 115, 127, 139, 151, 163 and 175. The new text is centered at x159 with baseline y194, leaving the complete longest choice visible in the native 320 by 200 screen.

The poll hook at image offset 6203 intercepts action 14 only for the original main list. Other events return unchanged to native dispatch. A successful activation cycles the value modulo five, writes the existing one-byte TACTIC.DIF preference and updates the native text. The hook redraws the original parent screen using its native SCREEN,0,0 call before returning to the idle loop. The widget is hidden when another action opens a child screen. On returning from a canceled child, it is re-enabled and the same native parent redraw runs immediately. This explicit redraw fixes a tested case in which canceling character creation otherwise left the label invisible until another input caused painting.

The cleanup hook at image offset 6D8E calls the native text destructor and tail-calls the original palette destructor without changing the caller's arguments. Construction and cleanup preserve the required register/stack ABI. `source/check_menu.py` runs 20 actual assembled-hook scenarios with narrow DOS/native-service stubs, including original action dispatch, all values, file failures, explicit parent redraw and child return. With no `--payload` argument it reads and verifies the distributed payload from patch.json, so the checker does not depend on development files.

Preference values remain 0=Game Journalist, 1=Easy, 2=Normal, 3=Hard and 4=Avatar. A missing, unreadable, short or invalid setting defaults to Normal. Existing files are opened read/write without truncation. Creation is allowed only after DOS reports file-not-found and uses exclusive create. The write count and close result are checked; failures display `DIFFICULTY: SAVE FAILED` and retain the previous in-memory choice. A failed newly created file is removed. A close failure can occur after a byte reached disk, so its durability cannot be inferred from the error label.

The original native menu has an approximately 15-second, 900-tick idle attract timer that selects View Introduction. It is unchanged. When a mouse is detected, the original initial selection is View Introduction. The title-dismiss helper consumes one key; queuing extra Enter input can therefore activate that selection. Native list navigation uses Up/Down and Enter; mouse handling is also inherited from the real widget list. Account for the attract timer and title transition when automating menu tests. Do not diagnose an attract transition as a Difficulty action without observing the actual event or setting file.

## v1.2.1 tactical panel layout

`panel.inc` is the only gameplay overlay source changed from the supplied independent v1.2 build. The panel is 216 by 120 pixels, defaults to (4,76), and clamps its top-left to x0..104 and y0..80. Nine command controls use 64 by 14 rectangles in three columns at relative x6/76/146 and three rows at y64/82/100. Horizontal gaps are six pixels and vertical gaps are four pixels. Labels have a five-pixel horizontal inset; native font-2 measurements put `R Ranged` at 53 pixels and `T Target` at 52, leaving six and seven pixels on the right. Drawing and input use the same rectangle constants.

The 60 by 14 Hide control starts at relative (150,3). The hidden panel's 88 by 16 Show control is at screen (4,4). Party slots are 21 by 12 at relative (6,48), with a pitch of 22 and a maximum of nine slots. Unused slots and gaps do not generate commands. The geometry checker exercises 134,600 assembled hit-test points, native font fit, press/release cancellation, bounded dragging and the drawing helpers' exact fill/text coordinates.

The difficulty/magic implementation, command lifecycle, equipment validation and pause integration sources remain byte-identical to the supplied independent v1.2 files. Its USECODE and both LINKDEP outputs also remain byte-identical. The guarded v1.2 upgrade and the quick manual update consequently replace only U7.EXE and MAINMENU.EXE. Current release runtime observations and their limits are recorded in VALIDATION.txt and VALIDATION.json; historical gameplay observations elsewhere in this handover are not claims that every campaign flow was repeated for this UI change.


## v1.2.2 mouse and highlight correction

The accepted v1.2.1 game is the baseline for this correction. The user confirmed that keyboard cycling worked but reported that the visible Difficulty row could not be clicked and did not highlight like the other entries. Earlier center-point mouse tests did not establish coverage of its full visible label.

The native text widget inherits an image-frame hit test that does not follow its centered text width and baseline. Its original text renderer also ignores the selected byte used by the native list. This revision corrects the Difficulty widget's hit-test and rendering behavior while retaining the original action list's mouse/keyboard ownership, event 14, preference persistence and child-screen lifecycle. Current implementation details and focused native runtime results are recorded with this release's source and VALIDATION files.

Only MAINMENU.EXE changes from v1.2.1. U7.EXE, the larger tactical popup, gameplay code, USECODE, dependency tables, launcher, saves, preferences and verified pristine backups remain byte-identical. The quick update contains only MAINMENU.EXE. The guarded installer additionally recognizes the exact v1.2.1 menu hash and continues to reconstruct from the verified MAINMENU.ORI backup.

### Current native widget implementation

The owner frame remains 1E60h and the retained payload begins at the previous DS:5AA0 boundary. Construction copies the original 38h-byte native text virtual table at DS:1172 into a private retained table. The widget's near virtual-table pointer at +17h points to that DATA-relative copy. Only the renderer at table+4 and mouse predicate at table+0Ch are replaced; every other native method remains intact. The patcher verifies the entire pristine source table before installing the payload.

`hit_text_row(this,x,y)` derives the centered horizontal extent from native x at +33h and current measured width at +4Eh. It derives the vertical text extent from baseline y at +35h, height at +50h and baseline offset at +52h. Native set_text refreshes the measurements on each setting change, so short choices and Game Journalist use their correct visible widths. The original menu list still owns mouse hover, keyboard focus and event-14 activation.

The six original entries are derived image buttons with selected/unselected shape frames. Their selected appearance brightens the lettering. The custom Difficulty text renderer must honor the native selected byte at +14h and preserve the text glyphs. An ordinary filled rectangle over the text is incorrect; a rectangular border also differs from the original button appearance. See the final source and release validation for the selected text rendering used here.

The final renderer first calls the original text renderer 0BF5:0479. For a selected row it translates only pixels inside the measured text rectangle with the palette mapping observed in all six original normal/selected button frame pairs: 132 to 131, 133 to 132, 134 to 132, 135 to 133 and 136 to 133. All other indices remain unchanged, including background and 137. Decoding the actual difficulty/error label glyphs confirms that they use only 132, 133, 134 and 136, so no unobserved palette extension is needed. This reproduces the original brighter lettering without a box or altered glyph shape.

The native graphics context stores the buffer segment at +0, the flat row-pointer table at +2 and an inclusive clip rectangle at +6..+Ch. The pixel translator follows the original rectangle routine's row addressing and preserves all caller general registers, DS/ES and flags. The wrapper uses the existing selected byte and leaves the original drawing and input lifecycle in charge.

The original Return to Menu action composes and fades in its restored screen before the next event poll. A narrow wrapper at the existing native draw call, image offset 65ADh, enables the Difficulty widget before that first composition and tail-calls the original screen draw. The original arguments and return address remain on the stack. This makes the row visible immediately after returning from a child screen, without relying on hover or keyboard input. The hook reuses the existing relocation at 65B0h; its entry is stored in the manifest's previously reserved word at offset 24.

Final MAINMENU.EXE: 130,749 bytes, SHA-256 `d6ea3f7b4e2fea5d678a0113286ecaba9cf6bdd20b3446365bf9c29c6e40512e`. Ten native service segment pointers plus the new creation-call segment give eleven new MZ relocation records, for 2,123 total. The copied native vtable retains its existing relocated segment words; its two private hook entries receive the current CS when constructed. The 26-case checker includes real assembled palette translation and verifies unchanged exterior/background pixels, measured hit bounds, inherited virtual-method preservation and restoration before the native return-screen draw.
