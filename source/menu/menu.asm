; Native graphical MAINMENU difficulty extension for the hash-identified DOS EXE.
; This is a resident data/code reservation below the original CRT stack/heap.
; asset_patcher reads the manifest and adds explicit MZ relocation records.
; The original entry, resource loader, widget/event owners and action dispatch stay.
bits 16
org 0
%define WIDGET -0x1E60
%define SCREEN -0x12D8
%define LIST -0x1560
%define EVENT 14

db 'U7NDIF2',0
dw 2, 32
dw create_hook, poll_hook, cleanup_hook
dw relocation_table, (relocation_end-relocation_table)/2, payload_end
dw return_draw_hook
times 32-($-$$) db 0

; This hook is after the six original main-menu widgets have been constructed.
; BP is deliberately the native menu frame. DS == SS is its original data segment.
create_hook:
    pushfd
    pushad
    push ds
    push es
    call read_setting
    lea di, [bp+WIDGET]
    mov [cs:widget], di
    ; Native text-widget constructor: this, far font, backing-store flag,
    ; parent screen, shadow flag. MAINSHP resource 9 is already the menu font.
    push word 0
    lea ax, [bp+SCREEN]
    push ax
    push word 1
    push word [0x7DF]
    push word [0x7DD]
    push di
    call far [cs:text_constructor]
    add sp, 12
    ; Text and image widgets share the native image hit-test, but a centered
    ; text label has its own measured width and baseline. Its renderer also
    ; ignores the selected flag used by image rows. Give only this widget a
    ; private copy of the original text vtable, correcting those two methods.
    ; The copy lives in our retained DATA reservation, so its near pointer is
    ; valid for the original Borland virtual dispatch (DS, not CS).
    push di
    mov si, 0x1172
    mov di, text_vtable
    push cs
    pop es
    mov cx, 0x1C
    cld
    rep movsw
    pop di
    mov word [cs:text_vtable+4], draw_text_row
    mov word [cs:text_vtable+12], hit_text_row
    mov ax, cs
    mov [cs:text_vtable+6], ax
    mov [cs:text_vtable+14], ax
    mov word [di+0x17], 0x5AA0+text_vtable
    ; Center the label with the original native text alignment routine.
    push word 1
    push di
    call far [cs:text_align]
    add sp, 4
    call update_label
    push word 194
    push word 159
    push di
    call far [cs:position_widget]
    add sp, 6
    ; The real list still owns keyboard focus, mouse hover, selection and click.
    push word 0
    push word 0
    push word 0
    push word EVENT
    push di
    lea ax, [bp+LIST]
    push ax
    call far [cs:add_action]
    add sp, 12
    pop es
    pop ds
    popad
    popfd
    ; Replay the two original instructions replaced by the five-byte hook.
    mov al, [bp-1]
    mov ah, 0
    retf

; Called in place of the native event-list poll. Its original list argument is
; still on the caller's stack, and the caller's BP remains the menu owner frame.
poll_hook:
    push bx
    push dx
    push si
    push di
    push es
    lea ax, [bp+LIST]
    cmp si, ax
    jne .child
    ; A canceled child screen returns to this same native list.
    mov di, [cs:widget]
    cmp word [di+0x12], 0
    jne .poll
    mov word [di+0x12], 1
    mov word [di+0x10], 0
    ; The native event poll can wait before the owner repaints. Repaint the
    ; original screen immediately so returning from a child reveals this row
    ; without requiring input over an invisible hit rectangle.
    call redraw_root
    jmp .poll
.child:
    mov di, [cs:widget]
    mov word [di+0x12], 0
    mov word [di+0x10], 0
.poll:
    push si
    call far [cs:native_poll]
    add sp, 2
    cmp ax, EVENT
    jne .native_action
    lea bx, [bp+LIST]
    cmp si, bx
    jne .native_action
    mov al, [cs:difficulty]
    mov [cs:previous], al
    inc al
    cmp al, 5
    jb .store
    xor al, al
.store:
    mov [cs:difficulty], al
    call save_setting
    jnc .label
    mov al, [cs:previous]
    mov [cs:difficulty], al
    mov byte [cs:save_error], 1
.label:
    call update_label
    call redraw_root
    ; No native action was selected; keep the original modal idle loop active.
    xor ax, ax
    jmp .done
.native_action:
    or ax, ax
    jz .done
    ; Other actions can open the original child UI or return to the launcher.
    ; Hide our control before the original action draws a child screen.
    mov di, [cs:widget]
    mov word [di+0x12], 0
    mov word [di+0x10], 0
.done:
    pop es
    pop di
    pop si
    pop dx
    pop bx
    retf

; The original palette destructor call is replaced with this tail-call wrapper.
; Free the native text widget's string/backing store and detach its parent before
; the native frame disappears. The original palette argument stays untouched.
cleanup_hook:
    pushfd
    pushad
    push ds
    push es
    push word 0
    push word [cs:widget]
    call far [cs:text_destructor]
    add sp, 4
    pop es
    pop ds
    popad
    popfd
    jmp far [cs:palette_destructor]

; Original Return to Menu composes its first restored canvas before the next
; event poll, then fades that already-composed canvas in. Restore our row here
; so it is included immediately, without relying on a later mouse/key event.
; The original SCREEN,0,0 arguments and far return address remain untouched.
return_draw_hook:
    pushfd
    pushad
    mov di, [cs:widget]
    mov word [di+0x12], 1
    mov word [di+0x10], 0
    popad
    popfd
    jmp far [cs:draw_screen]

read_setting:
    push ds
    push cs
    pop ds
    mov byte [difficulty], 2
    mov byte [save_error], 0
    mov dx, config
    mov ax, 0x3D00
    int 0x21
    jc .done
    mov bx, ax
    mov cx, 1
    mov dx, difficulty
    mov ah, 0x3F
    int 0x21
    pushf
    push ax
    mov ah, 0x3E
    int 0x21
    pop ax
    popf
    jc .normal
    cmp ax, 1
    jne .normal
    cmp byte [difficulty], 4
    jbe .done
.normal:
    mov byte [difficulty], 2
.done:
    pop ds
    ret

save_setting:
    push ds
    push cs
    pop ds
    mov byte [save_error], 0
    mov byte [created], 0
    mov dx, config
    mov ax, 0x3D02              ; Existing one-byte file: no truncation.
    int 0x21
    jnc .opened
    cmp ax, 2                  ; Create only when the file does not exist.
    jne .failed
    xor cx, cx
    mov ax, 0x5B00             ; Exclusive DOS 3+ create; never overwrite.
    int 0x21
    jc .failed
    mov byte [created], 1
.opened:
    mov bx, ax
    mov dx, difficulty
    mov cx, 1
    mov ah, 0x40
    int 0x21
    mov si, 0
    jc .close
    cmp ax, 1
    jne .close
    inc si
.close:
    mov ah, 0x3E
    int 0x21
    jc .failed
    cmp si, 1
    jne .failed
    clc
    jmp .done
.failed:
    ; A failed zero-byte write never destroys an existing setting. Remove an
    ; incomplete file created during this attempt, so the native default applies.
    cmp byte [created], 0
    je .carry
    mov dx, config
    mov ah, 0x41
    int 0x21
.carry:
    stc
.done:
    pop ds
    ret

update_label:
    mov di, [cs:widget]
    xor bx, bx
    mov bl, [cs:difficulty]
    shl bx, 1
    mov ax, [cs:labels+bx]
    cmp byte [cs:save_error], 0
    je .text
    mov ax, error_label
.text:
    push word -1
    push cs
    push ax
    push di
    call far [cs:set_text]
    add sp, 8
    ret

redraw_root:
    push word 0
    push word 0
    lea ax, [bp+SCREEN]
    push ax
    call far [cs:draw_screen]
    add sp, 6
    ret

; Virtual mouse predicate: this, x, y. Match the full rendered label with a
; one-pixel click margin, rather than the font's unrelated image-frame bounds.
; The native set_text routine refreshes +4E on every difficulty label change.
hit_text_row:
    push bp
    mov bp, sp
    push bx
    push dx
    push si
    mov si, [bp+6]
    mov ax, [si+0x4E]
    sar ax, 1
    mov bx, [si+0x33]
    sub bx, ax
    mov dx, bx
    dec bx
    cmp [bp+8], bx
    jl .outside
    add dx, [si+0x4E]
    cmp [bp+8], dx
    jg .outside
    mov dx, [si+0x35]
    add dx, [si+0x52]
    mov bx, dx
    sub bx, [si+0x50]
    dec bx
    cmp [bp+10], bx
    jl .outside
    inc dx
    cmp [bp+10], dx
    jg .outside
    mov ax, 1
    jmp .done
.outside:
    xor ax, ax
.done:
    pop si
    pop dx
    pop bx
    pop bp
    retf

; Virtual renderer: this. The original menu button's frame1 has exactly the
; same glyph coordinates as frame0, with its blue palette ramp brightened.
; Keep the original text renderer, then apply that observed palette mapping
; only to this measured label's pixels. No border or background fill is added.
draw_text_row:
    push bp
    mov bp, sp
    sub sp, 14
    push si
    push di
    push es
    mov si, [bp+6]
    push si
    call far [cs:text_draw]
    add sp, 2
    cmp byte [si+0x14], 0
    je .done
    push si
    push ss
    pop es
    lea di, [bp-14]
    mov cx, 7
    cld
    rep movsw
    pop si
    mov ax, [si+0x4E]
    sar ax, 1
    mov dx, [si+0x33]
    sub dx, ax
    mov [bp-8], dx
    add dx, [si+0x4E]
    dec dx
    mov [bp-4], dx
    mov ax, [si+0x35]
    add ax, [si+0x52]
    mov [bp-2], ax
    sub ax, [si+0x50]
    mov [bp-6], ax
    lea bx, [bp-14]
    call brighten_glyphs
.done:
    pop es
    pop di
    pop si
    mov sp, bp
    pop bp
    retf

; Native graphics context: buffer segment at +0, flat row-pointer table +2,
; inclusive clip rectangle +6..+C. Follow exactly the original rectangle
; primitive's row addressing. Preserve all caller registers, segments and flags.
brighten_glyphs:
    pushfd
    pushad
    push ds
    push es
    movzx edx, word [bx+10]
    movzx eax, word [bx+6]
    sub edx, eax
    inc edx
    mov ebp, eax
    movzx esi, word [bx+12]
    movzx ecx, word [bx+8]
    sub esi, ecx
    inc esi
    mov edi, [bx+2]
    shl ecx, 2
    add edi, ecx
    mov ax, [bx]
    mov es, ax
    xor ax, ax
    mov ds, ax
.row:
    push edi
    mov edi, [edi]
    add edi, ebp
    mov ecx, edx
.pixel:
    mov al, [es:edi]
    cmp al, 132
    jb .next
    cmp al, 136
    ja .next
    sub al, 132
    movzx bx, al
    mov al, [cs:highlight_ramp+bx]
    mov [es:edi], al
.next:
    inc edi
    dec ecx
    jnz .pixel
    pop edi
    add edi, 4
    dec esi
    jnz .row
    pop es
    pop ds
    popad
    popfd
    ret

; Observed in every original MAINSHP menu button frame0/frame1 pair.
; All glyphs used by the six difficulty/error labels use only 132/133/134/136.
; Other palette indices, including137, remain unchanged.
highlight_ramp: db 131, 132, 132, 133, 133

widget: dw 0
difficulty: db 2
previous: db 2
save_error: db 0
created: db 0
config: db 'TACTIC.DIF',0
labels: dw journalist, easy, normal, hard, avatar
journalist: db 'DIFFICULTY: GAME JOURNALIST',0
easy: db 'DIFFICULTY: EASY',0
normal: db 'DIFFICULTY: NORMAL',0
hard: db 'DIFFICULTY: HARD',0
avatar: db 'DIFFICULTY: AVATAR',0
error_label: db 'DIFFICULTY: SAVE FAILED',0
text_vtable: times 0x38 db 0

; Every segment word below receives a real DOS MZ relocation. There are no
; unlisted immediate native segments or runtime paragraph-delta guesses.
text_constructor: dw 0x011D, 0x0BF5
set_text: dw 0x01C6, 0x0BF5
text_align: dw 0x0608, 0x0BF5
position_widget: dw 0x09D2, 0x09D5
add_action: dw 0x0062, 0x09CA
native_poll: dw 0x032A, 0x0975
text_destructor: dw 0x0176, 0x0BF5
palette_destructor: dw 0x0236, 0x0DEA
draw_screen: dw 0x0D38, 0x09D5
text_draw: dw 0x0479, 0x0BF5
relocation_table:
    dw text_constructor+2, set_text+2, text_align+2, position_widget+2
    dw add_action+2, native_poll+2, text_destructor+2, palette_destructor+2
    dw draw_screen+2
    dw text_draw+2
relocation_end:
payload_end:
