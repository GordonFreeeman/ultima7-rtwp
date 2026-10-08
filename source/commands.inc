; Original U7BG companion orders. All native IBO arguments passed by reference
; are stack locals: overlay loading may evict this code, so no CS pointer is
; handed to the original engine. Runtime records live in an unused DS string.
%assign dseg_tactical_selected 0x1090
%assign dseg_tactical_magic    0x1091
%assign dseg_tactical_records  0x1092
%assign TacticalRecord_SIZE   10
%assign TacticalRecord_npc     0
%assign TacticalRecord_path    2
%assign TacticalRecord_target  4
%assign TacticalRecord_mode    6
%assign TacticalRecord_attack  7
%assign TacticalRecord_schedule 8
%assign TacticalRecord_flags   9
%assign TacticalMode_AUTO      0
%assign TacticalMode_HOLD      1
%assign TacticalMode_TARGET    2
%assign TacticalMode_MOVE      3

defineAddress 86, 0x0B73, tactical_native_set_quality
defineAddress 62, 0x02D9, tactical_native_reset_action
defineAddress 247, 0x006B, tactical_native_new_path
defineAddress 37, 0x0DA9, tactical_native_step_path
defineAddress 37, 0x07AD, tactical_native_delete_path

tactical_commands_init:
    cmp byte [dseg_tactical_magic], 0xAC
    je .ready
    call tactical_commands_reset
.ready:
    movzx ax, byte [dseg_tactical_selected]
    movzx dx, byte [dseg_partySize]
    cmp ax, dx
    jb .return
    mov byte [dseg_tactical_selected], 0
.return:
    retn

; Called after the native loader has replaced the heap/actors. Old route
; pointers cannot then be dereferenced or freed; reset simply forgets them.
tactical_commands_reset:
    push ax
    push cx
    push di
    push es
    push ds
    pop es
    cld
    mov di, dseg_tactical_records
    xor ax, ax
    mov cx, 9*TacticalRecord_SIZE/2
    rep stosw
    mov di, dseg_tactical_records
    mov cx, 9
.sentinels:
    mov word [di+TacticalRecord_npc], 0xFFFF
    mov word [di+TacticalRecord_target], 0xFFFF
    add di, TacticalRecord_SIZE
    loop .sentinels
    mov byte [dseg_tactical_selected], 0
    mov byte [dseg_tactical_magic], 0xAC
    call tactical_weapon_init
    pop es
    pop di
    pop cx
    pop ax
    retn

; AX=zero-based native party slot. Returns AX=current actor IBO or zero,
; BX=record. Native NPC number is retained, so IBO recycling cannot transfer
; orders to another NPC. SI/DI and DS are preserved by every public routine.
tactical_get_record_for_slot:
    push bp
    mov bp, sp
    sub sp, 4
    push si
    push di
    push es
    cmp ax, 9
    jae .missing
    movzx dx, byte [dseg_partySize]
    cmp ax, dx
    jae .missing
    mov bx, ax
    shl bx, 1
    mov dx, [dseg_partyMemberIbos+bx]
    mov [bp-2], dx
    mov dx, TacticalRecord_SIZE
    mul dx
    mov di, ax
    add di, dseg_tactical_records
    cmp word [bp-2], 0
    je .missing
    lea ax, [bp-2]
    push ax
    callFromOverlay Item_getNpcNumber
    pop cx
    mov [bp-4], ax
    cmp ax, [di+TacticalRecord_npc]
    je .same_actor
    ; Party order may change. Find the actor's existing order by stable NPC
    ; identity before allocating a record, so orders follow the companion.
    mov si, dseg_tactical_records
    mov cx, 9
.find_existing:
    cmp ax, [si+TacticalRecord_npc]
    je .found_existing
    add si, TacticalRecord_SIZE
    loop .find_existing
    mov si, dseg_tactical_records
    mov cx, 9
.find_empty:
    cmp word [si+TacticalRecord_npc], 0xFFFF
    je .allocate_here
    add si, TacticalRecord_SIZE
    loop .find_empty
    ; If the party is full and someone joins, prefer an automatic record.
    mov si, dseg_tactical_records
    mov cx, 9
.find_automatic:
    cmp byte [si+TacticalRecord_mode], TacticalMode_AUTO
    je .allocate_here
    add si, TacticalRecord_SIZE
    loop .find_automatic
    ; Every record has a manual order: restore the displaced record before
    ; reuse. No orders or path pointers are transferred to a new actor.
    push word [di+TacticalRecord_npc]
    lea ax, [bp-2]
    push ax
    callFromOverlay getNpcIbo
    add sp, 4
    mov ax, [bp-2]
    test ax, ax
    jz .reuse_preferred
    mov bx, di
    call tactical_restore_actor_defaults
.reuse_preferred:
    mov si, di
.allocate_here:
    mov di, si
    mov bx, di
    call tactical_cancel_path
    mov ax, [bp-4]
    mov [di+TacticalRecord_npc], ax
    mov word [di+TacticalRecord_target], 0xFFFF
    mov byte [di+TacticalRecord_mode], TacticalMode_AUTO
    mov byte [di+TacticalRecord_flags], 0
    jmp .same_actor
.found_existing:
    mov di, si
.same_actor:
    ; Re-resolve the stable NPC number through the original NPC lookup.
    push word [di+TacticalRecord_npc]
    lea ax, [bp-2]
    push ax
    callFromOverlay getNpcIbo
    add sp, 4
    mov ax, [bp-2]
    mov bx, di
    jmp .return
.missing:
    xor ax, ax
    xor bx, bx
.return:
    pop es
    pop di
    pop si
    mov sp, bp
    pop bp
    retn

tactical_get_selected_ibo:
    movzx ax, byte [dseg_tactical_selected]
    jmp tactical_get_record_for_slot

tactical_handle_key:
    push si
    push di
    cmp ax, '1'
    jb .other
    cmp ax, '9'
    ja .other
    sub ax, '1'
    mov si, ax
    call tactical_get_record_for_slot
    test ax, ax
    jz .handled
    mov ax, si
    mov [dseg_tactical_selected], al
    jmp .handled
.other:
    push ax
    call tactical_weapon_key
    test ax, ax
    pop dx
    jnz .handled
    mov ax, dx
    or al, 0x20
    cmp ax, 't'
    je .target
    cmp ax, 'h'
    je .hold
    cmp ax, 'g'
    je .move
    cmp ax, 'a'
    je .automatic
    cmp ax, 'i'
    je .inventory
    xor ax, ax
    jmp .return
.target:
    call tactical_order_target
    jmp .handled
.hold:
    call tactical_order_hold
    jmp .handled
.move:
    call tactical_order_move
    jmp .handled
.automatic:
    call tactical_order_automatic
    jmp .handled
.inventory:
    call tactical_open_inventory
.handled:
    mov ax, 1
.return:
    pop di
    pop si
    retn

; BX=record. The command owns exactly one path object. Clear ownership before
; invoking its destructor, avoiding a second free on nested calls/reassignment.
tactical_cancel_path:
    push bx
    mov ax, [bx+TacticalRecord_path]
    mov word [bx+TacticalRecord_path], 0
    test ax, ax
    jz .return
    push word 3
    push ax
    callFromOverlay tactical_native_delete_path
    add sp, 4
.return:
    pop bx
    retn

; AX=actor IBO, BX=record. Capture defaults once per manual-control interval.
tactical_prepare_manual:
    push bp
    mov bp, sp
    sub sp, 2
    mov [bp-2], ax
    push si
    push di
    push es
    mov di, bx
    cmp byte [di+TacticalRecord_mode], TacticalMode_AUTO
    jne .return
    lea ax, [bp-2]
    push ax
    callFromOverlay Item_getQuality
    pop cx
    mov [di+TacticalRecord_attack], al
    lea ax, [bp-2]
    push ax
    callFromOverlay getNpcBufferForIbo
    pop cx
    mov es, dx
    mov bx, ax
    mov al, [es:bx+0x0A]
    mov [di+TacticalRecord_schedule], al
.return:
    mov ax, [bp-2]
    mov bx, di
    pop es
    pop di
    pop si
    mov sp, bp
    pop bp
    retn

; Stop the native action stack without freezing strength/stat flags. Preserve
; the Avatar-specific native state byte that native reset(wait) clears.
tactical_apply_wait:
    push bp
    mov bp, sp
    sub sp, 4
    mov [bp-2], ax
    mov al, [0x77BC]
    mov [bp-4], al
    push si
    push di
    push es
    push word 15
    lea ax, [bp-2]
    push ax
    callFromOverlay tactical_native_reset_action
    add sp, 4
    mov al, [bp-4]
    mov [0x77BC], al
    lea ax, [bp-2]
    push ax
    callFromOverlay getNpcBufferForIbo
    pop cx
    mov es, dx
    mov bx, ax
    mov byte [es:bx+0x0A], 15
    mov word [es:bx+0x19], 0xFFFF
    mov word [es:bx+0x1B], 0xFFFF
    mov word [es:bx+0x1D], 0xFFFF
    push word 9
    lea ax, [bp-2]
    push ax
    callFromOverlay tactical_native_set_quality
    add sp, 4
    pop es
    pop di
    pop si
    mov sp, bp
    pop bp
    retn

tactical_order_hold:
    push si
    push di
    call tactical_get_selected_ibo
    test ax, ax
    jz .return
    call tactical_prepare_manual
    mov si, ax
    mov di, bx
    call tactical_cancel_path
    mov byte [di+TacticalRecord_mode], TacticalMode_HOLD
    mov word [di+TacticalRecord_target], 0xFFFF
    mov ax, si
    call tactical_apply_wait
.return:
    pop di
    pop si
    retn

; Clear the pause text before native crosshair selection. Input remains inside
; the original blocking picker; it never advances world simulation.
tactical_pick_world:
    push dseg_camera
    callFromOverlay drawWorld
    pop cx
    callFromOverlay copyFrameBuffer
    retn

tactical_order_target:
    push bp
    mov bp, sp
    sub sp, 10
    push si
    push di
    push es
    call tactical_get_selected_ibo
    test ax, ax
    jz .return
    mov [bp-2], ax
    mov di, bx
    call tactical_pick_world
    mov word [bp-4], 0
    lea ax, [bp-10]
    push ax
    lea ax, [bp-8]
    push ax
    lea ax, [bp-6]
    push ax
    lea ax, [bp-4]
    push ax
    callFromOverlay havePlayerSelect
    add sp, 8
    cmp word [bp-4], 0
    je .return
    lea ax, [bp-4]
    push ax
    callFromOverlay Item_isPartyMember
    pop cx
    test al, al
    jnz .return
    lea ax, [bp-4]
    push ax
    callFromOverlay Item_getNpcNumber
    pop cx
    cmp ax, 0xFFFF
    je .return
    mov si, ax
    ; Verify that the selected object has a valid NPC record.
    push si
    lea ax, [bp-4]
    push ax
    callFromOverlay getNpcIbo
    add sp, 4
    cmp word [bp-4], 0
    je .return
    ; Enter native combat before capturing the automatic baseline. Native
    ; beginCombat changes party schedules; later A/save should restore the
    ; normal combat schedule, not an obsolete pre-combat follow schedule.
    callFromOverlay isAvatarInCombat
    test ax, ax
    jnz .already_combat
    callFromOverlay beginCombat
    call tactical_combat_started
.already_combat:
    mov ax, [bp-2]
    mov bx, di
    call tactical_prepare_manual
    call tactical_cancel_path
    mov [di+TacticalRecord_target], si
    mov byte [di+TacticalRecord_mode], TacticalMode_TARGET
    push word 0
    lea ax, [bp-2]
    push ax
    callFromOverlay tactical_native_reset_action
    add sp, 4
    push word 1
    push si
    lea ax, [bp-2]
    push ax
    callFromOverlay Item_setNpcTarget
    add sp, 6
    mov ax, [bp-2]
    mov bx, di
    call tactical_apply_target
.return:
    pop es
    pop di
    pop si
    mov sp, bp
    pop bp
    retn

; AX=actor IBO, BX=record. Explicit target fields are reasserted before each
; world step. Quality9 bypasses the companions' tactic0..8 selector. The
; Avatar's native manual9 branch returns before attacking, so his explicit
; primary target uses quality0; an existing primary bypasses foe selection.
tactical_apply_target:
    push bp
    mov bp, sp
    sub sp, 2
    mov [bp-2], ax
    push si
    push di
    push es
    mov di, bx
    lea ax, [bp-2]
    push ax
    callFromOverlay getNpcBufferForIbo
    pop cx
    mov es, dx
    mov bx, ax
    mov byte [es:bx+0x0A], 0
    mov ax, [di+TacticalRecord_target]
    mov [es:bx+0x19], ax
    mov [es:bx+0x1D], ax
    mov word [es:bx+0x1B], 0xFFFF
    or byte [es:bx+0x28], 1
    mov ax, 9
    mov dx, [bp-2]
    cmp dx, [dseg_avatarIbo]
    jne .quality_ready
    xor ax, ax
.quality_ready:
    push ax
    lea ax, [bp-2]
    push ax
    callFromOverlay tactical_native_set_quality
    add sp, 4
    pop es
    pop di
    pop si
    mov sp, bp
    pop bp
    retn

tactical_order_move:
    push bp
    mov bp, sp
    sub sp, 12
    push si
    push di
    push es
    call tactical_get_selected_ibo
    test ax, ax
    jz .return
    mov [bp-2], ax
    mov di, bx
    call tactical_pick_world
    mov word [bp-4], 0
    mov word [bp-6], 0xFFFF
    mov word [bp-8], 0xFFFF
    lea ax, [bp-10]
    push ax
    lea ax, [bp-8]
    push ax
    lea ax, [bp-6]
    push ax
    lea ax, [bp-4]
    push ax
    callFromOverlay havePlayerSelect
    add sp, 8
    cmp word [bp-6], 0xFFFF
    je .return
    cmp word [bp-8], 0xFFFF
    je .return
    mov ax, [bp-2]
    mov bx, di
    call tactical_prepare_manual
    call tactical_cancel_path
    mov ax, [bp-2]
    call tactical_apply_wait
    mov word [bp-12], 0
    ; Same constructor arguments as native Avatar autoroute, with our actor.
    push word 0
    lea ax, [bp-12]
    push ax
    push word -1
    push word 0
    push word 1
    push word [bp-10]
    lea ax, [bp-8]
    push ax
    lea ax, [bp-6]
    push ax
    lea ax, [bp-2]
    push ax
    push word 0
    callFromOverlay tactical_native_new_path
    add sp, 20
    mov [di+TacticalRecord_path], ax
    mov word [di+TacticalRecord_target], 0xFFFF
    mov byte [di+TacticalRecord_mode], TacticalMode_HOLD
    test ax, ax
    jz .return
    mov bx, ax
    cmp byte [bx+0x17], 0
    je .invalid_path
    mov byte [di+TacticalRecord_mode], TacticalMode_MOVE
    jmp .return
.invalid_path:
    mov bx, di
    call tactical_cancel_path
.return:
    pop es
    pop di
    pop si
    mov sp, bp
    pop bp
    retn

tactical_order_automatic:
    push bp
    mov bp, sp
    sub sp, 2
    push si
    push di
    push es
    call tactical_get_selected_ibo
    test ax, ax
    jz .return
    mov [bp-2], ax
    mov di, bx
    call tactical_weapon_clear_selected
    call tactical_cancel_path
    cmp byte [di+TacticalRecord_mode], TacticalMode_AUTO
    je .return
    lea ax, [bp-2]
    push ax
    callFromOverlay getNpcBufferForIbo
    pop cx
    mov es, dx
    mov bx, ax
    mov al, [di+TacticalRecord_schedule]
    mov [es:bx+0x0A], al
    mov word [es:bx+0x19], 0xFFFF
    mov word [es:bx+0x1B], 0xFFFF
    mov word [es:bx+0x1D], 0xFFFF
    xor ah, ah
    push ax
    lea ax, [bp-2]
    push ax
    callFromOverlay tactical_native_reset_action
    add sp, 4
    movzx ax, byte [di+TacticalRecord_attack]
    push ax
    lea ax, [bp-2]
    push ax
    callFromOverlay tactical_native_set_quality
    add sp, 4
    mov byte [di+TacticalRecord_mode], TacticalMode_AUTO
    mov word [di+TacticalRecord_target], 0xFFFF
.return:
    pop es
    pop di
    pop si
    mov sp, bp
    pop bp
    retn

; AX=actor IBO, BX=record. Temporarily return serialized native fields to
; their pre-order values. The command record and owned path stay intact.
tactical_restore_actor_defaults:
    push bp
    mov bp, sp
    sub sp, 4
    mov [bp-2], ax
    mov al, [0x77BC]
    mov [bp-4], al
    push si
    push di
    push es
    mov di, bx
    cmp byte [di+TacticalRecord_mode], TacticalMode_AUTO
    je .return
    lea ax, [bp-2]
    push ax
    callFromOverlay getNpcBufferForIbo
    pop cx
    mov es, dx
    mov bx, ax
    mov al, [di+TacticalRecord_schedule]
    mov [es:bx+0x0A], al
    mov word [es:bx+0x19], 0xFFFF
    mov word [es:bx+0x1B], 0xFFFF
    mov word [es:bx+0x1D], 0xFFFF
    xor ah, ah
    push ax
    lea ax, [bp-2]
    push ax
    callFromOverlay tactical_native_reset_action
    add sp, 4
    movzx ax, byte [di+TacticalRecord_attack]
    push ax
    lea ax, [bp-2]
    push ax
    callFromOverlay tactical_native_set_quality
    add sp, 4
    mov al, [bp-4]
    mov [0x77BC], al
.return:
    pop es
    pop di
    pop si
    mov sp, bp
    pop bp
    retn

; Save lifecycle callbacks use stable NPC identity and do not depend on the
; current roster order. Suspension writes only original-compatible fields.
tactical_commands_suspend_all:
    cmp byte [dseg_tactical_magic], 0xAC
    jne .uninitialized
    call tactical_prune_departed_orders
    push bp
    mov bp, sp
    sub sp, 2
    push si
    push di
    mov di, dseg_tactical_records
    mov si, 9
.next:
    cmp byte [di+TacticalRecord_mode], TacticalMode_AUTO
    je .advance
    push word [di+TacticalRecord_npc]
    lea ax, [bp-2]
    push ax
    callFromOverlay getNpcIbo
    add sp, 4
    mov ax, [bp-2]
    test ax, ax
    jz .advance
    mov bx, di
    call tactical_restore_actor_defaults
.advance:
    add di, TacticalRecord_SIZE
    dec si
    jnz .next
    pop di
    pop si
    mov sp, bp
    pop bp
.uninitialized:
    retn

tactical_commands_resume_all:
    cmp byte [dseg_tactical_magic], 0xAC
    jne .uninitialized
    push bp
    mov bp, sp
    sub sp, 2
    push si
    push di
    mov di, dseg_tactical_records
    mov si, 9
.next:
    cmp byte [di+TacticalRecord_mode], TacticalMode_AUTO
    je .advance
    push word [di+TacticalRecord_npc]
    lea ax, [bp-2]
    push ax
    callFromOverlay getNpcIbo
    add sp, 4
    mov ax, [bp-2]
    test ax, ax
    jz .advance
    cmp byte [di+TacticalRecord_mode], TacticalMode_TARGET
    jne .wait
    mov bx, di
    call tactical_apply_target
    jmp .advance
.wait:
    call tactical_apply_wait
.advance:
    add di, TacticalRecord_SIZE
    dec si
    jnz .next
    pop di
    pop si
    mov sp, bp
    pop bp
.uninitialized:
    retn

; Native beginCombat skips actors held on wait15. Keep their saved Automatic
; baseline in the same combat phase as the ordinary party without changing
; any explicit order, target or owned route. Non-party schedule types remain
; native-owned; only normal party combat0/follow31 baselines are exchanged.
tactical_combat_started:
    cmp byte [dseg_tactical_magic], 0xAC
    jne .uninitialized
    push si
    push di
    call tactical_prune_departed_orders
    mov di, dseg_tactical_records
    mov si, 9
.next:
    cmp byte [di+TacticalRecord_mode], TacticalMode_AUTO
    je .advance
    cmp byte [di+TacticalRecord_schedule], 31
    jne .advance
    mov byte [di+TacticalRecord_schedule], 0
.advance:
    add di, TacticalRecord_SIZE
    dec si
    jnz .next
    pop di
    pop si
.uninitialized:
    retn

; Called only after the original breakOffCombat has executed, through its
; three guarded native callers. Its real transition to ordinary follow must
; update the saved Automatic baseline even for HOLD/MOVE actors: native
; breakOffCombat deliberately skips their wait15 schedule. Do not infer this
; event from the Avatar's wait15 schedule, since he can be held while a
; companion executes an explicit attack. A native combat end cancels TARGET;
; existing HOLD orders and owned G routes retain their explicit ownership.
tactical_combat_ended:
    cmp byte [dseg_tactical_magic], 0xAC
    jne .uninitialized
    push bp
    mov bp, sp
    sub sp, 2
    push si
    push di
    push es
    call tactical_prune_departed_orders
    mov di, dseg_tactical_records
    mov si, 9
.next:
    cmp byte [di+TacticalRecord_mode], TacticalMode_AUTO
    je .advance
    cmp byte [di+TacticalRecord_schedule], 0
    jne .baseline_ready
    mov byte [di+TacticalRecord_schedule], 31
.baseline_ready:
    cmp byte [di+TacticalRecord_mode], TacticalMode_TARGET
    jne .advance
    mov byte [di+TacticalRecord_mode], TacticalMode_HOLD
    mov word [di+TacticalRecord_target], 0xFFFF
    mov bx, di
    call tactical_cancel_path
    push word [di+TacticalRecord_npc]
    lea ax, [bp-2]
    push ax
    callFromOverlay getNpcIbo
    add sp, 4
    cmp word [bp-2], 0
    je .advance
    lea ax, [bp-2]
    push ax
    callFromOverlay isNpcUnconscious
    pop cx
    test al, al
    jnz .advance
    mov ax, [bp-2]
    call tactical_apply_wait
.advance:
    add di, TacticalRecord_SIZE
    dec si
    jnz .next
    pop es
    pop di
    pop si
    mov sp, bp
    pop bp
.uninitialized:
    retn

; AX=actor IBO. Return AX=1 only for an explicitly commanded companion.
; The native Avatar movement owner (resident4:07AB) normally resets the whole
; party to follow31 when moving an Avatar on a nonstandard schedule. Its
; guarded wrapper uses this predicate to keep companion HOLD/MOVE/TARGET
; ownership, while Avatar movement and ordinary Automatic followers stay
; under the unchanged native reset. Do not allocate records in this callback.
tactical_preserve_manual_follow:
    cmp byte [dseg_tactical_magic], 0xAC
    jne .automatic_uninitialized
    cmp ax, [dseg_avatarIbo]
    je .automatic_uninitialized
    push bp
    mov bp, sp
    sub sp, 2
    mov [bp-2], ax
    push si
    push di
    lea ax, [bp-2]
    push ax
    callFromOverlay Item_getNpcNumber
    pop cx
    mov di, dseg_tactical_records
    mov si, 9
.next:
    cmp ax, [di+TacticalRecord_npc]
    je .found
    add di, TacticalRecord_SIZE
    dec si
    jnz .next
.automatic:
    xor ax, ax
    jmp .return
.found:
    cmp byte [di+TacticalRecord_mode], TacticalMode_AUTO
    je .automatic
    mov ax, 1
.return:
    pop di
    pop si
    mov sp, bp
    pop bp
    retn
.automatic_uninitialized:
    xor ax, ax
    retn

tactical_commands_release_all:
    cmp byte [dseg_tactical_magic], 0xAC
    jne .uninitialized
    push si
    push di
    call tactical_commands_suspend_all
    mov di, dseg_tactical_records
    mov si, 9
.next:
    mov bx, di
    call tactical_cancel_path
    mov byte [di+TacticalRecord_mode], TacticalMode_AUTO
    mov word [di+TacticalRecord_target], 0xFFFF
    add di, TacticalRecord_SIZE
    dec si
    jnz .next
    call tactical_weapon_init
    pop di
    pop si
.uninitialized:
    retn

tactical_open_inventory:
    push bp
    mov bp, sp
    sub sp, 2
    push si
    push di
    call tactical_get_selected_ibo
    test ax, ax
    jz .return
    mov [bp-2], ax
    push word DialogState_INVENTORY
    callFromOverlay startNumberedDialog
    pop cx
    push word 0
    lea ax, [bp-2]
    push ax
    callFromOverlay displayItemDialog
    add sp, 4
    callFromOverlay redrawDialogs
    callFromOverlay copyFrameBuffer
    callFromOverlay itemDialogInputLoop
.return:
    pop di
    pop si
    mov sp, bp
    pop bp
    retn

tactical_command_tick:
    cmp byte [dseg_tactical_magic], 0xAC
    jne .return_uninitialized
    cmp byte [dseg_playerActionSuspended], 0
    jne .return_uninitialized
    push bp
    mov bp, sp
    sub sp, 4
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push es
    call tactical_prune_departed_orders
    xor si, si
.next:
    cmp si, 9
    jae .return
    mov ax, si
    call tactical_get_record_for_slot
    test ax, ax
    jz .advance
    mov [bp-2], ax
    mov di, bx
    cmp byte [di+TacticalRecord_mode], TacticalMode_AUTO
    je .advance
    ; A dead/unconscious commanded actor is governed by the native engine.
    lea ax, [bp-2]
    push ax
    callFromOverlay isNpcUnconscious
    pop cx
    test al, al
    jnz .advance
    cmp byte [di+TacticalRecord_mode], TacticalMode_TARGET
    jne .wait_or_move
    push word [di+TacticalRecord_target]
    lea ax, [bp-4]
    push ax
    callFromOverlay getNpcIbo
    add sp, 4
    cmp word [bp-4], 0
    je .finished_target
    lea ax, [bp-4]
    push ax
    callFromOverlay isNpcUnconscious
    pop cx
    test al, al
    jnz .finished_target
    mov ax, [bp-2]
    mov bx, di
    call tactical_apply_target
    jmp .advance
.finished_target:
    mov byte [di+TacticalRecord_mode], TacticalMode_HOLD
    mov word [di+TacticalRecord_target], 0xFFFF
.wait_or_move:
    mov ax, [bp-2]
    call tactical_apply_wait
    cmp byte [di+TacticalRecord_mode], TacticalMode_MOVE
    jne .advance
    cmp word [di+TacticalRecord_path], 0
    je .finished_move
    push word 1
    push word [di+TacticalRecord_path]
    callFromOverlay tactical_native_step_path
    add sp, 4
    cmp al, 1
    je .advance
    mov bx, di
    call tactical_cancel_path
.finished_move:
    mov byte [di+TacticalRecord_mode], TacticalMode_HOLD
.advance:
    inc si
    jmp .next
.return:
    pop es
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    mov sp, bp
    pop bp
.return_uninitialized:
    retn

; A dialogue can remove a commanded companion before the next world step.
; Give the native departure schedule priority: only restore a quality still
; equal to our manual9, never restore the old party follow/combat schedule or
; overwrite targets that native Usecode has changed. Own routes are canceled.
tactical_prune_departed_orders:
    push bp
    mov bp, sp
    sub sp, 2
    push si
    push di
    push es
    mov di, dseg_tactical_records
    mov si, 9
.next:
    cmp byte [di+TacticalRecord_mode], TacticalMode_AUTO
    je .advance
    push word [di+TacticalRecord_npc]
    lea ax, [bp-2]
    push ax
    callFromOverlay getNpcIbo
    add sp, 4
    cmp word [bp-2], 0
    je .forget
    lea ax, [bp-2]
    push ax
    callFromOverlay Item_isPartyMember
    pop cx
    test al, al
    jnz .advance
    lea ax, [bp-2]
    push ax
    callFromOverlay Item_getQuality
    pop cx
    cmp al, 9
    jne .forget
    movzx ax, byte [di+TacticalRecord_attack]
    push ax
    lea ax, [bp-2]
    push ax
    callFromOverlay tactical_native_set_quality
    add sp, 4
.forget:
    mov bx, di
    call tactical_cancel_path
    mov word [di+TacticalRecord_npc], 0xFFFF
    mov word [di+TacticalRecord_target], 0xFFFF
    mov byte [di+TacticalRecord_mode], TacticalMode_AUTO
    mov byte [di+TacticalRecord_flags], 0
.advance:
    add di, TacticalRecord_SIZE
    dec si
    jnz .next
    pop es
    pop di
    pop si
    mov sp, bp
    pop bp
    retn

; Selected actor name comes from the original 105-byte NPC record's 16-byte
; name field. Display copies are bounded and terminated inside DS/SS locals.
tactical_draw_status:
    push bp
    mov bp, sp
    sub sp, 96
    push si
    push di
    push es
    call tactical_get_selected_ibo
    test ax, ax
    jz .return
    mov [bp-2], ax
    mov di, bx
    lea ax, [bp-2]
    push ax
    callFromOverlay getNpcBufferForIbo
    pop cx
    mov es, dx
    mov bx, ax
    lea si, [bp-94]
    mov byte [si], 'S'
    mov byte [si+1], 'e'
    mov byte [si+2], 'l'
    mov byte [si+3], 'e'
    mov byte [si+4], 'c'
    mov byte [si+5], 't'
    mov byte [si+6], 'e'
    mov byte [si+7], 'd'
    mov byte [si+8], ' '
    mov al, [dseg_tactical_selected]
    add al, '1'
    mov [si+9], al
    mov byte [si+10], ':'
    mov byte [si+11], ' '
    xor cx, cx
.name:
    mov al, [es:bx+0x59]
    mov [si+12], al
    inc bx
    inc si
    inc cx
    test al, al
    jz .name_done
    cmp cx, 16
    jb .name
    mov byte [si+12], 0
.name_done:
    lea ax, [bp-94]
    mov bx, 8
    mov dx, 52
    call pause_print_line
    mov al, [di+TacticalRecord_mode]
    mov si, offsetInCodeSegment(tactical_status_auto)
    mov cx, tactical_status_auto_end-tactical_status_auto
    cmp al, TacticalMode_HOLD
    jne .not_hold
    mov si, offsetInCodeSegment(tactical_status_hold)
    mov cx, tactical_status_hold_end-tactical_status_hold
.not_hold:
    cmp al, TacticalMode_TARGET
    jne .not_target
    mov si, offsetInCodeSegment(tactical_status_target)
    mov cx, tactical_status_target_end-tactical_status_target
.not_target:
    cmp al, TacticalMode_MOVE
    jne .status_chosen
    mov si, offsetInCodeSegment(tactical_status_move)
    mov cx, tactical_status_move_end-tactical_status_move
.status_chosen:
    push di
    push ds
    pop es
    lea di, [bp-94]
    push ds
    push cs
    pop ds
    cld
    rep movsb
    pop ds
    pop di
    lea ax, [bp-94]
    mov bx, 8
    mov dx, 64
    call pause_print_line
    cmp byte [di+TacticalRecord_mode], TacticalMode_TARGET
    jne .weapon_status
    push word [di+TacticalRecord_target]
    lea ax, [bp-2]
    push ax
    callFromOverlay getNpcIbo
    add sp, 4
    cmp word [bp-2], 0
    je .weapon_status
    lea ax, [bp-2]
    push ax
    callFromOverlay getNpcBufferForIbo
    pop cx
    mov es, dx
    mov bx, ax
    lea si, [bp-94]
    mov word [si], 'Ta'
    mov word [si+2], 'rg'
    mov word [si+4], 'et'
    mov word [si+6], ': '
    cmp byte [es:bx+0x59], 0
    jne .target_named
    ; Generated monsters have no NPC name. Native display-name output is
    ; bounded to 80 bytes, including NUL; BP-86..BP-7 is inside this buffer.
    mov es, [dseg_itemBufferSegment]
    mov bx, [bp-2]
    mov ax, [es:bx+4]
    mov dx, ax
    and ax, 0x7C00
    shr ax, 10
    push ax
    push word 0
    and dx, 0x03FF
    push dx
    lea ax, [bp-86]
    push ax
    callFromOverlay produceItemDisplayName
    add sp, 8
    jmp .target_name_done
.target_named:
    xor cx, cx
.target_name:
    mov al, [es:bx+0x59]
    mov [si+8], al
    inc bx
    inc si
    inc cx
    test al, al
    jz .target_name_done
    cmp cx, 16
    jb .target_name
    mov byte [si+8], 0
.target_name_done:
    lea ax, [bp-94]
    mov bx, 8
    mov dx, 76
    call pause_print_line
.weapon_status:
    call tactical_weapon_draw_status
.return:
    pop es
    pop di
    pop si
    mov sp, bp
    pop bp
    retn

tactical_status_auto: db 'Order: automatic companion behavior', 0
tactical_status_auto_end:
tactical_status_hold: db 'Order: hold position  |  G: move', 0
tactical_status_hold_end:
tactical_status_target: db 'Order: attack selected target', 0
tactical_status_target_end:
tactical_status_move: db 'Order: move to selected position, then hold', 0
tactical_status_move_end:

%include "weapons.inc"
