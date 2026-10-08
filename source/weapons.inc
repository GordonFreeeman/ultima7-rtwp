; Per-companion melee/ranged command validation. The game's equipment UI
; remains the owner of ready-slot, two-hand, container and ammunition updates.
; Native combat resolver219:0337 reads slot1 (LEFT_HAND) as primary weapon.
%assign dseg_tactical_weapon_modes 0x10EE

; AX=native key. AX=1 handled, 0 unrelated. M/R validate actual equipment,
; ask for native equipment changes if needed, then queue a target command.
tactical_weapon_key:
    cmp ax, 'M'
    je .melee
    cmp ax, 'm'
    je .melee
    cmp ax, 'R'
    je .ranged
    cmp ax, 'r'
    je .ranged
    xor ax, ax
    retn
.melee:
    mov dx, 1
    jmp .requested
.ranged:
    mov dx, 2
.requested:
    push bp
    mov bp, sp
    sub sp, 4
    mov [bp-2], dx
    push si
    push di
    push es
    call tactical_get_selected_ibo
    test ax, ax
    jz .return_handled
    mov [bp-4], ax
    movzx bx, byte [dseg_tactical_selected]
    mov dx, [bp-2]
    mov [dseg_tactical_weapon_modes+bx], dl
    call tactical_weapon_class_for_actor
    call .matches_request
    test ax, ax
    jnz .attack
    ; Show the requested mode and precise ready-slot hint before opening the
    ; native inventory; commands stay paused during the equipment operation.
    call pause_redraw
    call tactical_open_inventory
    call tactical_get_selected_ibo
    test ax, ax
    jz .return_handled
    call tactical_weapon_class_for_actor
    call .matches_request
    test ax, ax
    jz .return_handled
.attack:
    call tactical_order_target
.return_handled:
    mov ax, 1
    pop es
    pop di
    pop si
    mov sp, bp
    pop bp
    retn
.matches_request:
    cmp word [bp-2], 1
    jne .expect_ranged
    cmp ax, 0
    je .match
    xor ax, ax
    retn
.expect_ranged:
    cmp ax, 3
    je .match
    xor ax, ax
    retn
.match:
    mov ax, 1
    retn

; AX=actor IBO, output AX=0 melee/fists,1/2 throwable,3 missile,FFFF unknown.
; Classification is built from the supplied native WEAPONS.DAT, unchanged.
tactical_weapon_class_for_actor:
    push si
    push di
    push es
    push InventorySlot_LEFT_HAND
    push ax
    callFromOverlay getItemInSlot
    add sp, 4
    test ax, ax
    jz .fists
    mov bx, ax
    mov es, [dseg_itemBufferSegment]
    mov ax, [es:bx+4]
    and ax, 0x03FF
    mov si, offsetInCodeSegment(weapon_type_table)
    mov cx, weapon_type_count
.next:
    cmp ax, [cs:si]
    je .known
    add si, 4
    loop .next
    mov ax, 0xFFFF
    jmp .done
.known:
    mov ax, [cs:si+2]
    jmp .done
.fists:
    xor ax, ax
.done:
    pop es
    pop di
    pop si
    retn

; Called by the selected actor's Automatic order to remove the mode hint.
tactical_weapon_clear_selected:
    push bx
    movzx bx, byte [dseg_tactical_selected]
    mov byte [dseg_tactical_weapon_modes+bx], 0
    pop bx
    retn

; Called at new command-state initialization; the parent owns signature guard.
tactical_weapon_init:
    push bx
    xor bx, bx
.next:
    mov byte [dseg_tactical_weapon_modes+bx], 0
    inc bx
    cmp bx, 9
    jb .next
    pop bx
    retn

tactical_weapon_draw_status:
    push bp
    mov bp, sp
    sub sp, 96
    push si
    push di
    push es
    call tactical_get_selected_ibo
    test ax, ax
    jz .done
    call tactical_weapon_class_for_actor
    mov dx, ax
    movzx bx, byte [dseg_tactical_selected]
    movzx ax, byte [dseg_tactical_weapon_modes+bx]
    cmp ax, 1
    je .want_melee
    cmp ax, 2
    je .want_ranged
    mov si, offsetInCodeSegment(weapon_status_native)
    jmp .copy
.want_melee:
    mov si, offsetInCodeSegment(weapon_status_melee)
    cmp dx, 0
    je .copy
    mov si, offsetInCodeSegment(weapon_hint_melee)
    jmp .copy
.want_ranged:
    mov si, offsetInCodeSegment(weapon_status_ranged)
    cmp dx, 3
    je .copy
    mov si, offsetInCodeSegment(weapon_hint_ranged)
.copy:
    push ds
    pop es
    lea di, [bp-96]
    cld
    ; Copy one short null-terminated overlay string without a far pointer.
    push ds
    push cs
    pop ds
    mov cx, 95
.char:
    lodsb
    stosb
    test al, al
    jz .copied
    loop .char
    xor al, al
    stosb
.copied:
    pop ds
    lea ax, [bp-96]
    mov bx, 8
    mov dx, 104
    call pause_print_line
.done:
    pop es
    pop di
    pop si
    mov sp, bp
    pop bp
    retn

weapon_status_native: db 'T: attack with the currently equipped weapon', 0
weapon_status_melee: db 'Melee ready: weapon or fists', 0
weapon_status_ranged: db 'Ranged ready: missile weapon', 0
weapon_hint_melee: db 'Equip melee weapon in left hand, then press M', 0
weapon_hint_ranged: db 'Equip bow, crossbow or wand in left hand; press R', 0

%include "include/weapon_types.inc"
