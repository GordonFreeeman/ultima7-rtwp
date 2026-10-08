# Programmer handover: tactical orders and pause lifecycle

This native DOS modification demonstrates a tactical command layer for individual party members in Ultima VII: The Black Gate. Anthony can inspect `commands.inc` for the order state model, `panel.inc` for the pause interface, and `pause.asm` for lifecycle ownership, then implement those behaviors through the remake's actor, path, combat, UI, and save/load APIs. The executable addresses, segmented-memory conventions, register preservation, and Borland overlay hooks are specific to the supported DOS build.

## Player-visible contract

The world can be paused for issuing commands to individual party members. A member has one current order: automatic behavior, hold, attack a selected actor, or move to a selected position and then hold. Assigning another order replaces that member's current order. Other members keep their own orders.

Selection numbers are presentation: they refer to the current party roster. An order belongs to an actor identity, so party reordering cannot transfer a command to a different actor. Names and equipment come from live game state.

Equipment selection uses the existing inventory interface. Melee and ranged commands validate what the member actually has equipped; they do not spawn equipment or ammunition. The general attack command retains the native handling of hybrid weapons. Esc or a right-button press cancels a tactical target/destination picker and retains the prior valid order. The order should be committed only after its selection and validation succeed.

The pause UI lets the player inspect and assign orders while simulation time is stopped. Inventory and interface timing can continue using a separate wall clock. Resuming permits normal simulation to execute all assigned orders. Native reach, collision, ammunition, damage, and actor status rules remain authoritative.

The native panel is 180 by 94 pixels within the 320 by 200 game screen. Its default position is x=4, y=106 at the bottom left, leaving the screen center accessible. It shows the selected member, current order, target when applicable, equipment hint, party selection buttons, and command buttons. Left-button press and release over the same control activates it; release elsewhere cancels the click. Dragging the title moves the panel within screen bounds, with its position remembered while the process runs. Tab or Hide removes the panel while keeping simulation paused; the small Paused Show control or Tab reopens it. Space/Resume resumes the world. In a remake, keep panel visibility and simulation pause as separate state variables.

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

The patch does not replace usecode, assets, pathfinding, save files, the original combat calculation, or the game launcher. Its native code references documented routines and fixed addresses for one hash-identified executable. Porting those offsets to another executable or treating them as stable interfaces is unsafe.

## Useful acceptance scenarios in another engine

Pause after issuing a move and confirm that world positions, projectiles, and simulation ticks stop while interface timers remain usable. Hide and reopen the panel with Tab and mouse controls, and verify that hiding never resumes the world. Drag the panel and confirm bounded placement without a world action. Issue different commands to multiple members and verify independent execution after resume. Reorder the party and confirm that orders remain attached to the same actors. Cancel target and destination pickers with Esc and with a right-button press; confirm that each returns to the paused interface, restores the cursor, and retains the prior command.

Hold a companion, resume, and move the Avatar with the ordinary right-mouse input. Observe the companion over individual updates and confirm it never takes an uncommanded step. Repeat with an owned move and an explicit attack to confirm that the Avatar's movement does not replace those orders with automatic following.

Exercise attack orders separately for the Avatar and companions, with melee and ranged equipment. Confirm actual damage/ammunition use and target continuity, not just an attack animation or a displayed status. Test a moving target, a dead/unconscious target, no ammunition, inaccessible terrain, and a changed weapon.

Start and end ordinary combat while an actor holds or moves. Returning it to automatic afterward must use the current ordinary policy. Confirm that an actual combat end cancels attack into hold while an owned move route and an explicit hold remain in place.

Save and cancel while moving and attacking; pending session commands should resume. Load both through the inventory/save modal and a fresh launcher process; commands should clear and no old-world route may be released after the heap has been replaced. Remove a commanded companion through a native story event and verify that the script's departure behavior remains in control.

The distribution's build identity does not substitute for these runtime observations. Review the release's separate validation report if provided by its author.
