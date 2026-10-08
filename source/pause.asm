; Native U7BG 3.4 tactical pause. No replacement engine or resource edits.
; The wrapper owns only the world keyboard/mouse poll call (31:0FAB).
; Ordinary keys still run the original native reader without consumption.
%include "include/common.asm"

[bits 16]

; Independently guarded UI state inside the audited unused build stamp.
%assign dseg_panel_magic       0x1055
%assign dseg_panel_visible     0x1056
%assign dseg_panel_dragging    0x1057
%assign dseg_panel_x           0x1058
%assign dseg_panel_y           0x105A
%assign dseg_panel_drag_x      0x105C
%assign dseg_panel_drag_y      0x105E
%assign dseg_panel_buttons     0x1060
%assign dseg_panel_pending     0x1061
%assign dseg_panel_active      0x1063

defineAddress 340, 0x00B1, tactical_native_save_ui
defineAddress 254, 0x002A, tactical_native_restore
defineAddress 62, 0x02D9, panel_native_reset_action

startPatch EXE_LENGTH, native-tactical-pause

  ; Replace the game's per-step keyboard discard with the command-policy tick.
  ; An opening Space survives until the original world input owner gets it.
  startBlockAt 30, 0x0084
    callFromLoadModule tactical_tick_entry
  endBlockOfLength 5

  ; Original three by-reference arguments and caller cleanup are retained.
  startBlockAt 31, 0x0FAB
    callFromLoadModule tactical_input_entry
  endBlockOfLength 5

  ; The original save/load modal has three owners: world key, dialog key,
  ; and inventory disk interaction. Preserve the original near flag pointer.
  startBlockAt 340, 0x0304
    push word 0x100C
    callFromOverlay tactical_modal_entry
    nop
  endBlockOfLength 9

  startBlockAt 340, 0x1454
    push word 0x100C
    callFromOverlay tactical_modal_entry
  endBlockOfLength 8

  startBlockAt 340, 0x1700
    push word 0x100C
    callFromOverlay tactical_modal_entry
  endBlockOfLength 8

  ; Confirmed native SaveUI restore call: near save descriptor DS:784C,
  ; slot number. The old native heap still exists on entry to this owner.
  startBlockAt 344, 0x0FB3
    callFromOverlay tactical_modal_entry
  endBlockOfLength 5

  ; The existing third export also owns the native end-combat transitions.
  startBlockAt 31, 0x0A0B
    callFromLoadModule tactical_tick_entry
  endBlockOfLength 5

  startBlockAt 318, 0x0346
    callFromOverlay tactical_tick_entry
  endBlockOfLength 5

  startBlockAt 342, 0x165E
    callFromOverlay tactical_tick_entry
  endBlockOfLength 5

  startBlockAt 31, 0x0A1F
    callFromLoadModule tactical_tick_entry
  endBlockOfLength 5

  startBlockAt 219, 0x301D
    callFromOverlay tactical_tick_entry
  endBlockOfLength 5

  startBlockAt 342, 0x1682
    callFromOverlay tactical_tick_entry
  endBlockOfLength 5

  ; Native follow fan-out must not overwrite manually owned companions.
  startBlockAt 4, 0x07AB
    callFromLoadModule tactical_tick_entry
  endBlockOfLength 5

  ; Keep the original native picker and object/coordinate selection path.
  ; Only paused tactical selection gains a clean Escape/right-click cancel.
  startBlockAt 234, 0x0039
    lea ax, [bp-0x1A]
    push ax
    callFromOverlay tactical_modal_entry
    pop cx
    test ax, ax
    jz .picker_native_event
    mov al, [bp-7]
    push ax
    callFromOverlay selectMouseCursor
    pop cx
    xor ax, ax
    jmp calcJump(0x01AD)
.picker_native_event:
    cmp byte [bp-0x13], MouseAction_NONE
    je calcJump(0x00F9)
    cmp byte [bp-0x13], MouseAction_MOVE
    je calcJump(0x00F9)
    jmp calcJump(0x006E)
    times (0x006E - block_currentOffset) nop
  endBlockOfLength 53

  startBlockAt 336, 0x0D80
    jmp pause_input_wrapper
    times (0x0D85 - block_currentOffset) nop
    jmp pause_save_ui_far
    times (0x0D8A - block_currentOffset) nop
    jmp pause_tick_far
    times (0x0DA0 - block_currentOffset) nop

pause_input_wrapper:
    push bp
    mov bp, sp
    push bx
    push cx
    push dx
    push si
    push di
    push es
    ; Respect the native transition/input suspension owner.
    cmp byte [dseg_playerActionSuspended], 0
    jne .original_reader
    ; Borland's one-byte ungetch buffer is checked before the BIOS queue.
    cmp byte [0x7320], 0
    je .peek_bios
    cmp byte [0x7321], ' '
    jne .original_reader
    mov byte [0x7320], 0
    jmp .open_pause
.peek_bios:
    mov ah, 1
    int 0x16
    jz .original_reader
    cmp al, ' '
    jne .original_reader
    ; Consume through the game's original DOS reader, with its original
    ; discard-following-keys semantics. No extended-key pushback is used.
    push word 1
    callFromOverlay pollKey
    pop cx
.open_pause:
    call pause_modal
    ; Consumed Space cannot start native key-mouse or movement on return.
    xor ax, ax
    mov bx, [bp+6]
    mov [bx], ax
    mov bx, [bp+8]
    mov [bx], ax
    mov bx, [bp+10]
    mov [bx], ax
    jmp .return
.original_reader:
    push word [bp+10]
    push word [bp+8]
    push word [bp+6]
    callFromOverlay pollKeyAndTranslateWithMouse
    add sp, 6
.return:
    pop es
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    mov sp, bp
    pop bp
    retf

; Exactly the original SaveUI ABI: one near, by-reference exit flag. Restore
; native actor state before serialization; pending orders stay in our runtime
; records and are reapplied after Save/Cancel. A requested exit releases them.
pause_save_ui_far:
    push bp
    mov bp, sp
    cmp word [bp+2], 0x0042
    je pause_picker_poll_far_body
    ; The guarded SaveUI owners pass 100C; the guarded restore owner passes
    ; 784C. These are two private entry ABIs with distinct first arguments.
    cmp word [bp+6], 0x784C
    je pause_restore_far_body
    pushfd
    pushad
    push ds
    push es
    call tactical_commands_suspend_all
    pop es
    pop ds
    popad
    popfd
    push word [bp+6]
    callFromOverlay tactical_native_save_ui
    ; Drop only our inner argument without changing native return flags.
    lea sp, [bp]
    pushfd
    pushad
    push ds
    push es
    mov bx, [bp+6]
    cmp byte [bx], 0
    jne .release
    call tactical_commands_resume_all
    jmp .restored
.release:
    call tactical_commands_release_all
.restored:
    pop es
    pop ds
    popad
    popfd
    mov sp, bp
    pop bp
    retf

pause_restore_far_body:
    pushfd
    pushad
    push ds
    push es
    ; Free only our old routes while the old world still owns the heap.
    call tactical_commands_release_all
    pop es
    pop ds
    popad
    popfd
    push word [bp+8]
    push word [bp+6]
    callFromOverlay tactical_native_restore
    lea sp, [bp]
    pushfd
    pushad
    push ds
    push es
    ; Restore rebuilt the native world in place. Never dereference/free an
    ; old route now; reset only clears extension records and mode hints.
    call tactical_commands_reset
    pop es
    pop ds
    popad
    popfd
    mov sp, bp
    pop bp
    retf

pause_tick_far:
    push bp
    mov bp, sp
    pushfd
    ; The guarded gameStep call returns0089. The three guarded native combat
    ; endings return0A10/034B/1663 through this same loader-managed export.
    cmp word [bp+2], 0x0089
    je .tick
    cmp word [bp+2], 0x07B0
    je .native_follow
    cmp word [bp+2], 0x0A24
    je .combat_start
    cmp word [bp+2], 0x3022
    je .combat_start
    cmp word [bp+2], 0x1687
    je .combat_start
    jmp .combat_end
.tick:
    popfd
    pop bp
    pushfd
    pushad
    push ds
    push es
    ; Do not reload FS/GS: Ultima's unreal-mode cached segment limits belong
    ; to its native Voodoo manager. The tick uses native memory access helpers.
    call tactical_command_tick
    pop es
    pop ds
    popad
    popfd
    retf
.native_follow:
    popfd
    pop bp
    push bp
    mov bp, sp
    pushfd
    pushad
    push ds
    push es
    mov bx, [bp+6]
    mov ax, [bx]
    call tactical_preserve_manual_follow
    test ax, ax
    jnz .follow_owned
    pop es
    pop ds
    popad
    popfd
    push word [bp+8]
    push word [bp+6]
    callFromOverlay panel_native_reset_action
    lea sp, [bp]
    pop bp
    retf
.follow_owned:
    pop es
    pop ds
    popad
    popfd
    mov sp, bp
    pop bp
    retf
.combat_start:
    popfd
    pop bp
    callFromOverlay beginCombat
    pushfd
    pushad
    push ds
    push es
    call tactical_combat_started
    pop es
    pop ds
    popad
    popfd
    retf
.combat_end:
    popfd
    pop bp
    callFromOverlay breakOffCombat
    pushfd
    pushad
    push ds
    push es
    call tactical_combat_ended
    pop es
    pop ds
    popad
    popfd
    retf

 ; The modal never calls gameStep; hiding the panel only changes drawing.
pause_modal:
    push bp
    mov bp, sp
    push bx
    push cx
    push dx
    push si
    push di
    push es
    call tactical_commands_init
    call tactical_panel_init
    mov byte [dseg_panel_active], 1
    mov byte [dseg_panel_visible], 1
    call tactical_panel_sync_mouse
    call pause_redraw
.poll:
    push word 1
    callFromOverlay pollKey
    pop cx
    test ax, ax
    jnz .key
    call tactical_panel_mouse
    test ax, ax
    jz .idle
.key:
    cmp ax, ' '
    je .resume
    cmp ax, 27
    je .resume
    cmp ax, 9
    je .toggle
    cmp ax, 0xFFFF
    je .redraw
    ; A mouse command is dispatched after its release event. Keyboard commands
    ; also wait out any held button, so native child pickers receive no opener.
    push ax
    call tactical_panel_sync_mouse
    pop ax
    call tactical_handle_key
    test ax, ax
    jz .poll
    call tactical_panel_sync_mouse
.redraw:
    call pause_redraw
    jmp .poll
.toggle:
    xor byte [dseg_panel_visible], 1
    mov byte [dseg_panel_dragging], 0
    mov word [dseg_panel_pending], 0
    jmp .redraw
.idle:
    callFromOverlay cyclePalette
    jmp .poll
.resume:
    call tactical_panel_sync_mouse
    mov byte [dseg_panel_active], 0
    push dseg_camera
    callFromOverlay drawWorld
    pop cx
    callFromOverlay copyFrameBuffer
    pop es
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    mov sp, bp
    pop bp
    retn

pause_redraw:
    push bp
    mov bp, sp
    push bx
    push cx
    push dx
    push si
    push di
    push es
    ; Preserve the camera's native lighting. Tactical pause adds no darkening.
    push dseg_camera
    callFromOverlay drawWorld
    pop cx
    call tactical_panel_draw
    callFromOverlay copyFrameBuffer
    pop es
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    mov sp, bp
    pop bp
    retn

; AX=near string, BX=x, DX=y. Callers may use stack strings because the
; original Borland near data and stack share the runtime segment.
; Construct the native proportional TextPrinter without extending its heap.
pause_print_line:
    push bp
    mov bp, sp
    sub sp, 24
    mov [bp-18], ax
    mov [bp-20], bx
    mov [bp-22], dx
    push si
    push di
    lea si, [bp-16]
    push si
    callFromOverlay TextPrinter_new
    pop cx
    mov word [si+TextPrinter_pn_vtable], dseg_pn_ProportionalTextPrinter_vtable
    mov word [si+TextPrinter_pn_viewport], dseg_viewport
    mov ax, [bp-20]
    mov [si+TextPrinter_x], ax
    mov ax, [bp-22]
    mov [si+TextPrinter_y], ax
    push Font_YELLOW
    push si
    callFromOverlay TextPrinter_setFont
    add sp, 4
    push word [bp-18]
    push si
    callFromOverlay TextPrinter_printString
    add sp, 4
    pop di
    pop si
    mov sp, bp
    pop bp
    retn

%include "commands.inc"
%include "panel.inc"

  endBlock
endPatch
