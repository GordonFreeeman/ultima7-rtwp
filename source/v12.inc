; v1.2: native damage policy, native spellbook companion context and saved mana.
v12_init:
    cmp byte [dseg_v12_magic], 0xD2
    je .done
    mov byte [dseg_v12_magic], 0xD2
    mov byte [dseg_v12_difficulty], 2
    mov word [dseg_v12_ledger], 0
    mov word [dseg_v12_caster], 0
    mov byte [dseg_v12_loaded], 0
    mov ax, [0x1516]
    mov [dseg_v12_mana_tick], ax
    push ds
    push cs
    pop ds
    mov dx, offsetInCodeSegment(v12_config)
    mov ax, 0x3D00
    int 0x21
    pop ds
    jc .done
    mov bx, ax
    push bx
    mov dx, dseg_v12_difficulty
    mov cx, 1
    mov ah, 0x3F
    int 0x21
    pop bx
    push ax
    mov ah, 0x3E
    int 0x21
    pop ax
    cmp ax, 1
    jne .default
    cmp byte [dseg_v12_difficulty], 4
    jbe .done
.default:
    mov byte [dseg_v12_difficulty], 2
.done:
    retn

v12_before_restore:
    call v12_suspend_caster
    mov word [dseg_v12_caster], 0
    mov byte [dseg_v12_loaded], 1
    cmp byte [dseg_v12_magic], 0xD2
    jne .done
    mov ax, [dseg_v12_ledger]
    mov word [dseg_v12_ledger], 0
    test ax, ax
    jz .done
    push ax
    callFromOverlay deallocateNearMemory
    pop cx
.done:
    retn

v12_suspend_caster:
    cmp word [dseg_v12_caster], 0
    je .done
    mov ax, [dseg_v12_original_avatar]
    mov [dseg_avatarIbo], ax
.done:
    retn

v12_resume_caster:
    mov ax, [dseg_v12_caster]
    test ax, ax
    jz .done
    mov [dseg_avatarIbo], ax
.done:
    retn

; AX=IBO -> AX=1 if in the actual native party, otherwise zero.
v12_is_party:
    push bx
    push cx
    cmp ax, [dseg_avatarIbo]
    je .yes
    mov cx, [dseg_partySize]
    cmp cx, 9
    ja .no
    mov bx, dseg_partyMemberIbos
.next:
    jcxz .no
    cmp ax, [bx]
    je .yes
    add bx, 2
    loop .next
.no:
    xor ax, ax
    jmp .done
.yes:
    mov ax, 1
.done:
    pop cx
    pop bx
    retn

; SI points at the freshly allocated IBO. The native class-8 allocation has
; a primary block plus two linked eight-byte spellbook data blocks.
v12_new_book_dispatch:
    pop bx
    pushfd
    pushad
    push es
    mov bx, [si]
    mov es, [dseg_itemBufferSegment]
    mov ax, [es:bx+4]
    and ax, 0x3FF
    cmp ax, 761
    jne .done
    mov bx, [es:bx+6]
    test bx, bx
    jz .done
    mov byte [es:bx], 0xFF ; the eight ordinary linear spells
    mov word [es:bx+1], 0
    mov word [es:bx+3], 0
    mov bx, [es:bx+6]
    test bx, bx
    jz .done
    mov dword [es:bx], 0
    mov dword [es:bx+4], 0
.done:
    pop es
    popad
    popfd
    mov bx, [si]
    mov es, [dseg_itemBufferSegment]
    retf

v12_damage_dispatch:
    pop bx
    pushfd
    pushad
    push ds
    push es
    call v12_init
    cmp byte [dseg_v12_difficulty], 2
    je .done
    cmp byte [ss:bp+10], 0
    jle .done
    mov bx, [ss:bp+6]
    mov ax, [bx]
    test ax, ax
    jz .done
    call v12_is_party
    mov si, ax
    mov bx, [ss:bp+8]
    mov ax, [bx]
    call v12_is_party
    cmp ax, si
    je .done
    movzx bx, byte [dseg_v12_difficulty]
    shl bx, 1
    mov cx, [cs:bx+offsetInCodeSegment(v12_factors)]
    movzx ax, byte [ss:bp+10]
    test si, si
    jnz .durability
    ; Enemy -> party: native signed damage remains within 0..127.
    mul cx
    mov cx, 100
    add ax, 50
    adc dx, 0
    div cx
    test ax, ax
    jnz .clamp
    inc ax
    jmp .clamp
.durability:
    ; Party -> enemy: inverse HP factor. A per-NPC remainder makes even
    ; repeated one-point hits count at Hard/Avatar without signed HP overflow.
    mov si, cx
    mov cx, 100
    mul cx
    push ax
    push dx
    mov ax, [dseg_v12_ledger]
    test ax, ax
    jnz .ledger
    push word V12_NPCS*2
    callFromOverlay allocateNearMemory
    pop cx
    mov [dseg_v12_ledger], ax
    test ax, ax
    jz .ledger
    push ds
    pop es
    mov di, ax
    mov cx, V12_NPCS
    xor ax, ax
    cld
    rep stosw
.ledger:
    mov bx, [ss:bp+8]
    push bx
    callFromOverlay Item_getNpcNumber
    pop cx
    mov di, ax
    pop dx
    pop ax
    xor bx, bx
    cmp di, V12_NPCS
    jae .divide
    mov bx, [dseg_v12_ledger]
    test bx, bx
    jz .divide
    shl di, 1
    add bx, di
    add ax, [bx]
    adc dx, 0
.divide:
    div si
    test bx, bx
    jnz .remember
    ; Actors without an indexed NPC record, or a failed ledger allocation,
    ; still take at least one point rather than becoming immune to small hits.
    test ax, ax
    jnz .clamp
    inc ax
    jmp .clamp
.remember:
    mov [bx], dx
.clamp:
    cmp ax, 127
    jbe .store
    mov ax, 127
.store:
    mov [ss:bp+10], al
.done:
    pop es
    pop ds
    popad
    popfd
    ; Replay the two overwritten native instructions exactly.
    mov di, [bp+6]
    mov si, [bp+8]
    retf

; Original RNG ABI, preserving Normal's exact bound and random stream.
v12_rng_dispatch:
    pop bx
    push bp
    mov bp, sp
    push bx
    push cx
    push dx
    push si
    push di
    push es
    call v12_init
    mov si, [bp+6]
    cmp byte [dseg_v12_difficulty], 0
    je .disabled
    call v12_magic_restored
    test ax, ax
    jz .native
    mov al, [dseg_v12_difficulty]
    cmp al, 1
    je .easy
    cmp al, 3
    je .hard
    cmp al, 4
    je .avatar
    jmp .native
.easy:
    shl si, 1
    jmp .native
.hard:
    mov ax, si
    mov bx, 2
    mul bx
    mov bx, 3
    div bx
    mov si, ax
    jmp .native
.avatar:
    mov ax, si
    mov bx, 2
    mul bx
    mov bx, 5
    div bx
    mov si, ax
.native:
    push si
    callFromOverlay generateRandomIntegerInRange
    pop cx
    jmp .return
.disabled:
    mov ax, 0x7FFF
.return:
    pop es
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop bp
    retf

; Saved original global flag 3, bit 4, with native lazy flags already loaded.
v12_magic_restored:
    push bx
    push es
    mov bx, 0x5F9C
    cmp word [bx+8], 3
    jbe .no
    les bx, [bx+4]
    xor ax, ax
    test byte [es:bx], 0x10
    jz .done
    inc ax
    jmp .done
.no:
    xor ax, ax
.done:
    pop es
    pop bx
    retn

; Native book mana operations borrow the book's selected caster context.
; +0F/+10 are NPC identity/flags in the original save format, never repurposed.
v12_mana_read_dispatch:
    pop bx
    mov al, [es:bx+0x10]
    cmp word [dseg_v12_caster], 0
    je .native
    mov al, [es:bx+NPC_MANA]
.native:
    mov ah, 0
    retf

v12_mana_write_dispatch:
    pop bx
    push bp
    mov bp, sp
    mov ax, [bp+6]
    cmp word [dseg_v12_caster], 0
    je .native
    mov [es:bx+NPC_MANA], al
    jmp .done
.native:
    mov [es:bx+0x10], al
.done:
    pop bp
    retf 2

; Jaana is the recruitable native druid. Mariah is also a canonical mage,
; supported if already in a party, without altering her original recruitment.
v12_caster_eligible:
    cmp ax, 5
    je .yes
    cmp ax, 153
    je .yes
    xor ax, ax
    retn
.yes:
    mov ax, 1
    retn

; Called only outside the modal. Saved mana regenerates one point per sixteen
; native game-clock units, never from wall time while tactical pause is open.
v12_tick:
    call v12_init
    mov ax, [0x1516]
    sub ax, [dseg_v12_mana_tick]
    cmp ax, 16
    jb .done
    mov ax, [0x1516]
    mov [dseg_v12_mana_tick], ax
    call v12_magic_restored
    test ax, ax
    jz .done
    push bp
    mov bp, sp
    sub sp, 2
    xor si, si
.next:
    cmp si, [dseg_partySize]
    jae .return
    cmp si, 9
    jae .return
    mov bx, si
    shl bx, 1
    mov ax, [dseg_partyMemberIbos+bx]
    mov [bp-2], ax
    lea ax, [bp-2]
    push ax
    callFromOverlay Item_getNpcNumber
    pop cx
    call v12_caster_eligible
    test ax, ax
    jz .advance
    lea ax, [bp-2]
    push ax
    callFromOverlay getNpcBufferForIbo
    pop cx
    mov bx, ax
    mov es, dx
    call v12_mana_init
    mov al, [es:bx+NPC_MAGIC]
    and al, 0x1F
    cmp [es:bx+NPC_MANA], al
    jae .advance
    inc byte [es:bx+NPC_MANA]
.advance:
    inc si
    jmp .next
.return:
    mov sp, bp
    pop bp
.done:
    retn

v12_mana_init:
    test byte [es:bx+NPC_MAGIC], 0x80
    jnz .done
    mov al, [es:bx+8]
    and al, 0x1F
    cmp al, 8
    jae .capacity
    mov al, 8
.capacity:
    mov [es:bx+NPC_MANA], al
    or al, 0x80
    mov [es:bx+NPC_MAGIC], al
.done:
    retn

v12_open_spellbook:
    push bp
    mov bp, sp
    sub sp, 64
    push si
    push di
    push es
    call v12_init
    call tactical_get_selected_ibo
    test ax, ax
    jz .done
    mov [bp-2], ax
    cmp ax, [dseg_avatarIbo]
    je .find_book
    call v12_magic_restored
    test ax, ax
    jz .locked
    lea ax, [bp-2]
    push ax
    callFromOverlay Item_getNpcNumber
    pop cx
    call v12_caster_eligible
    test ax, ax
    jz .ineligible
    lea ax, [bp-2]
    push ax
    callFromOverlay isNpcUnconscious
    pop cx
    test al, al
    jnz .done
    lea ax, [bp-2]
    push ax
    callFromOverlay getNpcBufferForIbo
    pop cx
    mov bx, ax
    mov es, dx
    call v12_mana_init
.find_book:
    ; Native recursive find: output, owner, flags, shape, quality, frame.
    push word 0xFF
    push word 0xFF
    push word 761
    push word 0
    lea ax, [bp-2]
    push ax
    lea ax, [bp-62]
    push ax
    callFromOverlay findItemInContainer
    add sp, 12
    test al, al
    jz .no_book
    mov ax, [dseg_avatarIbo]
    mov [bp-4], ax
    mov [dseg_v12_original_avatar], ax
    mov byte [dseg_v12_loaded], 0
    mov ax, [bp-2]
    cmp ax, [bp-4]
    je .open
    mov [dseg_v12_caster], ax
    ; Native usecode's Avatar references must resolve to this spell's caster.
    ; This synchronous modal never calls gameStep. Restore before returning.
    mov [dseg_avatarIbo], ax
.open:
    push word DialogState_INVENTORY
    callFromOverlay startNumberedDialog
    pop cx
    push word 0
    lea ax, [bp-62]
    push ax
    callFromOverlay displayItemDialog
    add sp, 4
    callFromOverlay redrawDialogs
    callFromOverlay copyFrameBuffer
    callFromOverlay itemDialogInputLoop
    cmp byte [dseg_v12_loaded], 0
    jne .context_done
    mov ax, [bp-4]
    mov [dseg_avatarIbo], ax
.context_done:
    mov word [dseg_v12_caster], 0
    jmp .done
.locked:
    mov ax, offsetInCodeSegment(v12_locked)
    jmp .message
.ineligible:
    mov ax, offsetInCodeSegment(v12_ineligible)
    jmp .message
.no_book:
    mov ax, offsetInCodeSegment(v12_no_book)
.message:
    ; Reuse the modal's native text renderer; no borrowed CS string survives
    ; an overlay callback.
    mov bx, 5
    push ax
    mov ax, 137
    mov bx, 3
    mov dx, 26
    mov si, 174
    mov di, 14
    call panel_fill_relative
    pop ax
    mov bx, 5
    mov dx, 28
    call panel_text
    callFromOverlay copyFrameBuffer
.wait:
    push word 1
    callFromOverlay pollKey
    pop cx
    test ax, ax
    jz .wait
.done:
    pop es
    pop di
    pop si
    mov sp, bp
    pop bp
    retn

v12_config: db 'TACTIC.DIF', 0
v12_factors: dw 25, 75, 100, 125, 200
v12_locked: db 'Magic unrestored. Any key.', 0
v12_ineligible: db 'Not a mage. Any key.', 0
v12_no_book: db 'Needs spellbook. Any key.', 0

; Addresses for reproducible machine-code verification and future handover.
v12_symbols:
    db 'U7T12SYM'
    dw offsetInCodeSegment(v12_init)
    dw offsetInCodeSegment(v12_damage_dispatch)
    dw offsetInCodeSegment(v12_rng_dispatch)
    dw offsetInCodeSegment(v12_magic_restored)
    dw offsetInCodeSegment(v12_mana_read_dispatch)
    dw offsetInCodeSegment(v12_mana_write_dispatch)
    dw offsetInCodeSegment(v12_caster_eligible)
    dw offsetInCodeSegment(v12_tick)
    dw offsetInCodeSegment(v12_mana_init)
    dw offsetInCodeSegment(v12_open_spellbook)
    dw offsetInCodeSegment(v12_new_book_dispatch)
