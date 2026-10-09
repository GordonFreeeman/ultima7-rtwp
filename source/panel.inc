; Native tactical window. Every pixel and glyph is drawn by the game's
; native surface/text consumers. No custom INT33 coordinate conversion, shape
; replacement, simulation step, or FS/GS manipulation is introduced here.
; FONTS.VGA font 2 has zero native character spacing. Its widest command labels
; are "T Target" (52 px) and "R Ranged" (53 px); use 64 px framed controls with
; 5 px text insets. The 8 px glyph cell is clear of both borders in 14 px rows.
%assign Panel_WIDTH 216
%assign Panel_HEIGHT 120
%assign Panel_INITIAL_X 4
%assign Panel_INITIAL_Y (200-Panel_HEIGHT-4)
%assign Panel_TITLE_X 3
%assign Panel_TITLE_Y 3
%assign Panel_TITLE_HEIGHT 14
%assign Panel_HIDE_WIDTH 60
%assign Panel_HIDE_X (Panel_WIDTH-6-Panel_HIDE_WIDTH)
%assign Panel_PARTY_X 6
%assign Panel_PARTY_Y 48
%assign Panel_PARTY_WIDTH 21
%assign Panel_PARTY_HEIGHT 12
%assign Panel_PARTY_PITCH 22
%assign Panel_PARTY_COUNT 9
%assign Panel_BUTTON_WIDTH 64
%assign Panel_BUTTON_HEIGHT 14
%assign Panel_BUTTON_TEXT_X 5
%assign Panel_BUTTON_TEXT_Y 2
%assign Panel_BUTTON_COLUMN_PITCH 70
%assign Panel_BUTTON_ROW_PITCH 18
%assign Panel_BUTTON_X 6
%assign Panel_BUTTON_Y 64
%assign Panel_REOPEN_X 4
%assign Panel_REOPEN_Y 4
%assign Panel_REOPEN_WIDTH 88
%assign Panel_REOPEN_HEIGHT 16

; Resident27:06F4 fills a bounded near Viewport. Unlike169:0006 it does not
; borrow FS/GS as pixel counts, and it enters the native Voodoo access owner
; (175:0008, guarded byDS6F2A&1) before using linear surface row addresses.
defineAddress 27, 0x06F4, panel_native_fill_viewport

; Shared modal export's private234:0042 ABI: one near12-byte MouseState
; pointer. Unrelated native pickers retain their original mouse behavior.
pause_picker_poll_far_body:
    push si
    push di
    cmp byte [dseg_panel_active], 1
    jne .native_poll
.keyboard:
    ; The native virtual mouse can consume arbitrary keys. Peek before its
    ; next update and consume onlyEscape through the game's own key reader.
    cmp byte [0x7320], 0
    je .bios
    cmp byte [0x7321], 27
    jne .native_poll
    mov byte [0x7320], 0
    jmp .cancel
.bios:
    mov ah, 1
    int 0x16
    jz .native_poll
    cmp al, 27
    jne .native_poll
    push word 1
    callFromOverlay pollKey
    pop cx
    jmp .cancel
.native_poll:
    push word [bp+6]
    callFromOverlay updateAndCopyMouseState
    pop cx
    cmp byte [dseg_panel_active], 1
    jne .native_only
    mov si, [bp+6]
    cmp byte [si+MouseState_button], 2
    jne .native_only
    cmp byte [si+MouseState_action], MouseAction_PRESS
    je .cancel
    cmp byte [si+MouseState_action], MouseAction_DOUBLE_CLICK
    jne .native_only
.cancel:
    ; G's by-reference coordinates remain its initializedFFFF values; T's
    ; IBO stays the native zero. The inline caller restores its saved cursor
    ; then takes the original epilogue, so no world selection is synthesized.
    mov byte [dseg_isKeyMouseEnabled], 0
    mov ax, 1
    jmp .return
.native_only:
    xor ax, ax
.return:
    pop di
    pop si
    mov sp, bp
    pop bp
    retf

tactical_panel_init:
    cmp byte [dseg_panel_magic], 0xD8
    je .ready
    mov byte [dseg_panel_magic], 0xD8
    mov word [dseg_panel_x], Panel_INITIAL_X
    mov word [dseg_panel_y], Panel_INITIAL_Y
.ready:
    ; Keep a remembered position valid for the complete current-size window.
    cmp word [dseg_panel_x], 0
    jge .x_nonnegative
    mov word [dseg_panel_x], 0
.x_nonnegative:
    cmp word [dseg_panel_x], 320-Panel_WIDTH
    jle .x_clamped
    mov word [dseg_panel_x], 320-Panel_WIDTH
.x_clamped:
    cmp word [dseg_panel_y], 0
    jge .y_nonnegative
    mov word [dseg_panel_y], 0
.y_nonnegative:
    cmp word [dseg_panel_y], 200-Panel_HEIGHT
    jle .y_clamped
    mov word [dseg_panel_y], 200-Panel_HEIGHT
.y_clamped:
    mov byte [dseg_panel_dragging], 0
    mov word [dseg_panel_pending], 0
    retn

; Drain the native mouse queue and wait out held buttons before transferring
; ownership to a child picker, equipment dialog, or the world. The consumed
; click cannot select a world object or start an inventory drag on return.
tactical_panel_sync_mouse:
    push ax
    push bx
.drain:
    callFromOverlay updateAndGetMouseState
    mov bx, ax
    mov al, [bx+MouseState_buttonBits]
    mov [dseg_panel_buttons], al
    test al, al
    jnz .drain
    cmp byte [bx+MouseState_action], MouseAction_NONE
    jne .drain
    mov byte [dseg_panel_dragging], 0
    mov word [dseg_panel_pending], 0
    pop bx
    pop ax
    retn

; Native MouseState_xx is doubled horizontally (56:0759 usesSAR1); y is
; already a screen coordinate. The native queue/cursor remains its owner.
; ReturnAX=key, FFFF=redraw after drag, zero=no panel event.
tactical_panel_mouse:
    push bp
    mov bp, sp
    sub sp, 10
    push bx
    push cx
    push dx
    push si
    push di
    callFromOverlay updateAndGetMouseState
    mov si, ax
    mov ax, [si+MouseState_xx]
    sar ax, 1
    mov [bp-2], ax
    mov ax, [si+MouseState_y]
    mov [bp-4], ax
    mov al, [si+MouseState_buttonBits]
    mov [dseg_panel_buttons], al
    cmp byte [dseg_panel_dragging], 0
    jne .drag
    cmp byte [si+MouseState_button], 1
    jne .none
    mov al, [si+MouseState_action]
    cmp al, MouseAction_PRESS
    je .press
    cmp al, MouseAction_DOUBLE_CLICK
    je .press
    cmp al, MouseAction_RELEASE
    jne .none
    mov ax, [bp-2]
    mov dx, [bp-4]
    call tactical_panel_hit
    cmp ax, [dseg_panel_pending]
    jne .cancel
    mov word [dseg_panel_pending], 0
    jmp .done
.cancel:
    mov word [dseg_panel_pending], 0
    jmp .none
.press:
    mov ax, [bp-2]
    mov dx, [bp-4]
    call tactical_panel_hit
    mov [dseg_panel_pending], ax
    cmp ax, 0xFFFE
    jne .none
    mov byte [dseg_panel_dragging], 1
    mov ax, [bp-2]
    sub ax, [dseg_panel_x]
    mov [dseg_panel_drag_x], ax
    mov ax, [bp-4]
    sub ax, [dseg_panel_y]
    mov [dseg_panel_drag_y], ax
    jmp .none
.drag:
    test byte [dseg_panel_buttons], 1
    jnz .position
    mov byte [dseg_panel_dragging], 0
    mov word [dseg_panel_pending], 0
    jmp .none
.position:
    mov ax, [bp-2]
    sub ax, [dseg_panel_drag_x]
    cmp ax, 0
    jge .x_nonnegative
    xor ax, ax
.x_nonnegative:
    cmp ax, 320-Panel_WIDTH
    jle .x_clamped
    mov ax, 320-Panel_WIDTH
.x_clamped:
    mov [bp-6], ax
    mov dx, [bp-4]
    sub dx, [dseg_panel_drag_y]
    cmp dx, 0
    jge .y_nonnegative
    xor dx, dx
.y_nonnegative:
    cmp dx, 200-Panel_HEIGHT
    jle .y_clamped
    mov dx, 200-Panel_HEIGHT
.y_clamped:
    cmp ax, [dseg_panel_x]
    jne .moved
    cmp dx, [dseg_panel_y]
    je .none
.moved:
    mov [dseg_panel_x], ax
    mov [dseg_panel_y], dx
    mov ax, 0xFFFF
    jmp .done
.none:
    xor ax, ax
.done:
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    mov sp, bp
    pop bp
    retn

; AX=screenX, DX=screenY. A title press starts a drag; actionable buttons
; return the exact existing native keyboard command. Hidden control isTab.
tactical_panel_hit:
    push bx
    push cx
    push si
    cmp byte [dseg_panel_visible], 0
    jne .window
    sub ax, Panel_REOPEN_X
    sub dx, Panel_REOPEN_Y
    cmp ax, Panel_REOPEN_WIDTH
    jae .miss
    cmp dx, Panel_REOPEN_HEIGHT
    jae .miss
    mov ax, 9
    jmp .return
.window:
    sub ax, [dseg_panel_x]
    sub dx, [dseg_panel_y]
    cmp ax, Panel_WIDTH
    jae .miss
    cmp dx, Panel_HEIGHT
    jae .miss
    cmp dx, Panel_TITLE_Y
    jb .miss
    cmp dx, Panel_TITLE_Y+Panel_TITLE_HEIGHT
    jae .party
    cmp ax, Panel_TITLE_X
    jb .miss
    cmp ax, Panel_WIDTH-Panel_TITLE_X
    jae .miss
    cmp ax, Panel_HIDE_X
    jb .drag_title
    cmp ax, Panel_HIDE_X+Panel_HIDE_WIDTH
    jb .hide
.drag_title:
    mov ax, 0xFFFE
    jmp .return
.hide:
    mov ax, 9
    jmp .return
.party:
    cmp dx, Panel_PARTY_Y
    jb .miss
    cmp dx, Panel_PARTY_Y+Panel_PARTY_HEIGHT
    jae .commands
    sub ax, Panel_PARTY_X
    cmp ax, Panel_PARTY_COUNT*Panel_PARTY_PITCH
    jae .miss
    xor dx, dx
    mov bx, Panel_PARTY_PITCH
    div bx
    cmp dx, Panel_PARTY_WIDTH
    jae .miss
    movzx bx, byte [dseg_partySize]
    cmp ax, bx
    jae .miss
    add ax, '1'
    jmp .return
.commands:
    ; Geometry follows the rendered table: x,y,w,h,key,string pointer.
    mov si, offsetInCodeSegment(panel_buttons)
    mov cx, panel_button_count
.button:
    mov bx, ax
    sub bx, [cs:si]
    cmp bx, [cs:si+4]
    jae .next
    mov bx, dx
    sub bx, [cs:si+2]
    cmp bx, [cs:si+6]
    jae .next
    mov ax, [cs:si+8]
    jmp .return
.next:
    add si, 12
    loop .button
.miss:
    xor ax, ax
.return:
    pop si
    pop cx
    pop bx
    retn

; AX=color BX=x DX=y SI=width DI=height, absolute screen coordinates.
; Copy native Viewport's selector and DWORD row table into DS/SS locals.
; Fill bounds are inclusive and already clamped to the320x200 native screen.
panel_fill_rect:
    push bp
    mov bp, sp
    sub sp, 18
    pushad
    push es
    mov [bp-18], ax
    mov [bp-10], bx
    mov [bp-8], dx
    dec si
    add si, bx
    mov [bp-6], si
    dec di
    add di, dx
    mov [bp-4], di
    mov ax, [dseg_viewport]
    mov [bp-16], ax
    mov eax, [dseg_viewport+2]
    mov [bp-14], eax
    push word [bp-18]
    lea ax, [bp-16]
    push ax
    callFromOverlay panel_native_fill_viewport
    add sp, 4
    pop es
    popad
    mov sp, bp
    pop bp
    retn

; Relative rectangle helper using the remembered window position.
panel_fill_relative:
    add bx, [dseg_panel_x]
    add dx, [dseg_panel_y]
    call panel_fill_rect
    sub bx, [dseg_panel_x]
    sub dx, [dseg_panel_y]
    retn

; AX=overlay string offset, BX/DX=relative text position. All strings are
; copied into DS/SS before any native far call can evict the overlay.
panel_text:
    push bp
    mov bp, sp
    sub sp, 64
    push si
    push di
    push es
    mov si, ax
    push ds
    pop es
    lea di, [bp-64]
    push ds
    push cs
    pop ds
    mov cx, 63
    cld
.copy:
    lodsb
    stosb
    test al, al
    jz .copied
    loop .copy
    mov byte [es:di], 0
.copied:
    pop ds
    lea ax, [bp-64]
    call panel_text_near
    pop es
    pop di
    pop si
    mov sp, bp
    pop bp
    retn

; AX=near string, BX/DX=relative position. Small native black SaveUI font.
panel_text_near:
    add bx, [dseg_panel_x]
    add dx, [dseg_panel_y]
panel_print_small:
    push bp
    mov bp, sp
    sub sp, 40
    mov [bp-18], ax
    mov [bp-20], bx
    ; Native font2 stores glyphs above its baseline; convert our top edge to
    ; that baseline so labels remain inside their native framed controls.
    add dx, 7
    mov [bp-22], dx
    push si
    push di
    lea si, [bp-16]
    push si
    callFromOverlay TextPrinter_new
    pop cx
    mov word [si+TextPrinter_pn_vtable], dseg_pn_ProportionalTextPrinter_vtable
    ; Bound native font drawing to the actual panel/reopen control, including
    ; generated monster names. The original row-table/selector are preserved.
    mov ax, [dseg_viewport]
    mov [bp-38], ax
    mov eax, [dseg_viewport+2]
    mov [bp-36], eax
    cmp byte [dseg_panel_visible], 0
    je .reopen_clip
    mov ax, [dseg_panel_x]
    add ax, 3
    mov [bp-32], ax
    add ax, Panel_WIDTH-7
    mov [bp-28], ax
    mov ax, [dseg_panel_y]
    add ax, 2
    mov [bp-30], ax
    add ax, Panel_HEIGHT-5
    mov [bp-26], ax
    jmp .clip_ready
.reopen_clip:
    mov word [bp-32], Panel_REOPEN_X+2
    mov word [bp-28], Panel_REOPEN_X+Panel_REOPEN_WIDTH-3
    mov word [bp-30], Panel_REOPEN_Y+1
    mov word [bp-26], Panel_REOPEN_Y+Panel_REOPEN_HEIGHT-2
.clip_ready:
    lea ax, [bp-38]
    mov [si+TextPrinter_pn_viewport], ax
    mov ax, [bp-20]
    mov [si+TextPrinter_x], ax
    mov ax, [bp-22]
    mov [si+TextPrinter_y], ax
    push Font_SMALL_BLACK
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

; AX=CS label BX/DX=relative position SI/DI=button size.
panel_draw_button:
    push ax
    mov ax, 141
    call panel_fill_relative
    inc bx
    inc dx
    sub si, 2
    sub di, 2
    mov ax, 134
    call panel_fill_relative
    add bx, Panel_BUTTON_TEXT_X-1
    add dx, Panel_BUTTON_TEXT_Y-1
    pop ax
    call panel_text
    retn

tactical_panel_draw:
    push bp
    mov bp, sp
    sub sp, 80
    pushad
    push es
    cmp byte [dseg_panel_visible], 0
    je .hidden
    xor bx, bx
    xor dx, dx
    mov si, Panel_WIDTH
    mov di, Panel_HEIGHT
    mov ax, 141
    call panel_fill_relative
    mov bx, 1
    mov dx, 1
    mov si, Panel_WIDTH-2
    mov di, Panel_HEIGHT-2
    mov ax, 134
    call panel_fill_relative
    mov bx, 2
    mov dx, 2
    mov si, Panel_WIDTH-4
    mov di, Panel_HEIGHT-4
    mov ax, 135
    call panel_fill_relative
    mov bx, Panel_TITLE_X
    mov dx, Panel_TITLE_Y
    mov si, Panel_WIDTH-2*Panel_TITLE_X
    mov di, Panel_TITLE_HEIGHT
    mov ax, 137
    call panel_fill_relative
    mov ax, offsetInCodeSegment(panel_title)
    mov bx, 7
    mov dx, Panel_TITLE_Y+Panel_BUTTON_TEXT_Y
    call panel_text
    mov ax, offsetInCodeSegment(panel_hide)
    mov bx, Panel_HIDE_X
    mov dx, Panel_TITLE_Y
    mov si, Panel_HIDE_WIDTH
    mov di, Panel_TITLE_HEIGHT
    call panel_draw_button
    call panel_draw_actor
    xor di, di
.party:
    mov ax, di
    mov bx, Panel_PARTY_PITCH
    mul bx
    mov bx, ax
    add bx, Panel_PARTY_X
    mov dx, Panel_PARTY_Y
    mov si, Panel_PARTY_WIDTH
    push di
    mov di, Panel_PARTY_HEIGHT
    mov ax, 137
    call panel_fill_relative
    pop di
    movzx ax, byte [dseg_tactical_selected]
    cmp ax, di
    jne .slot_text
    push di
    mov di, Panel_PARTY_HEIGHT
    mov ax, 3
    call panel_fill_relative
    pop di
.slot_text:
    movzx ax, byte [dseg_partySize]
    cmp di, ax
    jae .blank_slot
    mov ax, di
    add al, '1'
    mov [bp-2], al
    mov byte [bp-1], 0
    lea ax, [bp-2]
    add bx, 7
    mov dx, Panel_PARTY_Y+1
    call panel_text_near
.blank_slot:
    inc di
    cmp di, Panel_PARTY_COUNT
    jb .party
    mov si, offsetInCodeSegment(panel_buttons)
    mov di, panel_button_count
.buttons:
    push si
    push di
    mov bx, [cs:si]
    mov dx, [cs:si+2]
    mov ax, [cs:si+10]
    mov di, [cs:si+6]
    mov si, [cs:si+4]
    call panel_draw_button
    pop di
    pop si
    add si, 12
    dec di
    jnz .buttons
    jmp .return
.hidden:
    mov ax, 141
    mov bx, Panel_REOPEN_X
    mov dx, Panel_REOPEN_Y
    mov si, Panel_REOPEN_WIDTH
    mov di, Panel_REOPEN_HEIGHT
    call panel_fill_rect
    mov ax, 134
    inc bx
    inc dx
    sub si, 2
    sub di, 2
    call panel_fill_rect
    lea di, [bp-80]
    mov si, offsetInCodeSegment(panel_reopen)
    push ds
    pop es
    push ds
    push cs
    pop ds
    mov cx, panel_reopen_end-panel_reopen
    cld
    rep movsb
    pop ds
    lea ax, [bp-80]
    mov bx, Panel_REOPEN_X+5
    mov dx, Panel_REOPEN_Y+3
    call panel_print_small
.return:
    pop es
    popad
    mov sp, bp
    pop bp
    retn

panel_draw_actor:
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
    mov al, [dseg_tactical_selected]
    add al, '1'
    mov [si], al
    mov word [si+1], ': '
    add si, 3
    xor cx, cx
.name:
    mov al, [es:bx+0x59]
    mov [si], al
    inc bx
    inc si
    inc cx
    test al, al
    jz .named
    cmp cx, 16
    jb .name
    mov byte [si], 0
.named:
    lea ax, [bp-94]
    mov bx, 7
    mov dx, 19
    call panel_text_near
    mov ax, offsetInCodeSegment(panel_auto)
    cmp byte [di+TacticalRecord_mode], TacticalMode_HOLD
    jne .not_hold
    mov ax, offsetInCodeSegment(panel_hold)
.not_hold:
    cmp byte [di+TacticalRecord_mode], TacticalMode_MOVE
    jne .not_move
    mov ax, offsetInCodeSegment(panel_move)
.not_move:
    cmp byte [di+TacticalRecord_mode], TacticalMode_TARGET
    jne .print_order
    ; Keep the selected target visible with a bounded native actor/shape name.
    push word [di+TacticalRecord_target]
    lea ax, [bp-2]
    push ax
    callFromOverlay getNpcIbo
    add sp, 4
    cmp word [bp-2], 0
    je .generic_attack
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
    mov byte [bp-62], 0
    jmp .print_target
.target_named:
    xor cx, cx
.target_name:
    mov al, [es:bx+0x59]
    mov [si+8], al
    inc bx
    inc si
    inc cx
    test al, al
    jz .print_target
    cmp cx, 16
    jb .target_name
    mov byte [si+8], 0
.print_target:
    lea ax, [bp-94]
    mov bx, 7
    mov dx, 28
    call panel_text_near
    jmp .weapon
.generic_attack:
    mov ax, offsetInCodeSegment(panel_attack)
.print_order:
    mov bx, 7
    mov dx, 28
    call panel_text
.weapon:
    ; Target-name drawing reusesBP-2, so resolve the selected companion again.
    ; A requested M/R is only labelled ready when the actual primary hand
    ; matches; native equipment remains the owner of changing that hand.
    call tactical_get_selected_ibo
    test ax, ax
    jz .return
    call tactical_weapon_class_for_actor
    mov dx, ax
    movzx bx, byte [dseg_tactical_selected]
    mov al, [dseg_tactical_weapon_modes+bx]
    mov si, offsetInCodeSegment(panel_native_weapon)
    cmp al, 1
    jne .ranged
    mov si, offsetInCodeSegment(panel_melee_weapon)
    cmp dx, 0
    je .weapon_text
    mov si, offsetInCodeSegment(panel_melee_hint)
    jmp .weapon_text
.ranged:
    cmp al, 2
    jne .weapon_text
    mov si, offsetInCodeSegment(panel_ranged_weapon)
    cmp dx, 3
    je .weapon_text
    mov si, offsetInCodeSegment(panel_ranged_hint)
.weapon_text:
    mov ax, si
    mov bx, 7
    mov dx, 37
    call panel_text
.return:
    pop es
    pop di
    pop si
    mov sp, bp
    pop bp
    retn

panel_title: db 'TACTICAL PAUSE', 0
panel_hide: db 'Tab Hide', 0
panel_reopen: db 'Paused Show', 0
panel_reopen_end:
panel_auto: db 'Order: Automatic', 0
panel_hold: db 'Order: Hold position', 0
panel_move: db 'Order: Move, then hold', 0
panel_attack: db 'Order: Attack target', 0
panel_native_weapon: db 'Weapon: Current equipment', 0
panel_melee_weapon: db 'Melee ready', 0
panel_ranged_weapon: db 'Ranged ready', 0
panel_melee_hint: db 'Equip melee in left hand', 0
panel_ranged_hint: db 'Equip ranged in left hand', 0
panel_target_button: db 'T Target', 0
panel_melee_button: db 'M Melee', 0
panel_ranged_button: db 'R Ranged', 0
panel_move_button: db 'G Move', 0
panel_hold_button: db 'H Hold', 0
panel_auto_button: db 'A Auto', 0
panel_inventory_button: db 'I Gear', 0
panel_resume_button: db 'Resume', 0
panel_cast_button: db 'C Cast', 0
align 2
panel_buttons:
    ; Rendering and hit testing consume these same rectangles. 6 px column
    ; gaps, 4 px row gaps, and 6 px outer insets remain inert between controls.
    dw Panel_BUTTON_X, Panel_BUTTON_Y, Panel_BUTTON_WIDTH, Panel_BUTTON_HEIGHT, 't', offsetInCodeSegment(panel_target_button)
    dw Panel_BUTTON_X+Panel_BUTTON_COLUMN_PITCH, Panel_BUTTON_Y, Panel_BUTTON_WIDTH, Panel_BUTTON_HEIGHT, 'm', offsetInCodeSegment(panel_melee_button)
    dw Panel_BUTTON_X+2*Panel_BUTTON_COLUMN_PITCH, Panel_BUTTON_Y, Panel_BUTTON_WIDTH, Panel_BUTTON_HEIGHT, 'r', offsetInCodeSegment(panel_ranged_button)
    dw Panel_BUTTON_X, Panel_BUTTON_Y+Panel_BUTTON_ROW_PITCH, Panel_BUTTON_WIDTH, Panel_BUTTON_HEIGHT, 'g', offsetInCodeSegment(panel_move_button)
    dw Panel_BUTTON_X+Panel_BUTTON_COLUMN_PITCH, Panel_BUTTON_Y+Panel_BUTTON_ROW_PITCH, Panel_BUTTON_WIDTH, Panel_BUTTON_HEIGHT, 'h', offsetInCodeSegment(panel_hold_button)
    dw Panel_BUTTON_X+2*Panel_BUTTON_COLUMN_PITCH, Panel_BUTTON_Y+Panel_BUTTON_ROW_PITCH, Panel_BUTTON_WIDTH, Panel_BUTTON_HEIGHT, 'a', offsetInCodeSegment(panel_auto_button)
    dw Panel_BUTTON_X, Panel_BUTTON_Y+2*Panel_BUTTON_ROW_PITCH, Panel_BUTTON_WIDTH, Panel_BUTTON_HEIGHT, 'i', offsetInCodeSegment(panel_inventory_button)
    dw Panel_BUTTON_X+Panel_BUTTON_COLUMN_PITCH, Panel_BUTTON_Y+2*Panel_BUTTON_ROW_PITCH, Panel_BUTTON_WIDTH, Panel_BUTTON_HEIGHT, 'c', offsetInCodeSegment(panel_cast_button)
    dw Panel_BUTTON_X+2*Panel_BUTTON_COLUMN_PITCH, Panel_BUTTON_Y+2*Panel_BUTTON_ROW_PITCH, Panel_BUTTON_WIDTH, Panel_BUTTON_HEIGHT, ' ', offsetInCodeSegment(panel_resume_button)
panel_button_count equ (($-panel_buttons)/12)
