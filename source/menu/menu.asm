; DOS boot menu extension. Executed before the unmodified native menu entry.
; Flat binary appended in a separate paragraph beyond native data and BSS.
bits 16
org 0
start:
    pushfd
    pushad
    push ds
    push es
    push cs
    pop ds
    mov byte [difficulty], 2
    mov dx, config
    mov ax, 0x3D00
    int 0x21
    jc draw
    mov bx, ax
    mov cx, 1
    mov dx, difficulty
    mov ah, 0x3F
    int 0x21
    mov ah, 0x3E
    int 0x21
    cmp byte [difficulty], 4
    jbe draw
    mov byte [difficulty], 2
draw:
    mov ax, 3
    int 0x10
    mov dx, title
    mov ah, 9
    int 0x21
    mov al, [difficulty]
    add al, '1'
    mov dl, al
    mov ah, 2
    int 0x21
    mov dx, prompt
    mov ah, 9
    int 0x21
poll:
    xor ah, ah
    int 0x16
    cmp al, 13
    je save
    cmp al, 27
    je save
    cmp al, '1'
    jb poll
    cmp al, '5'
    ja poll
    sub al, '1'
    mov [difficulty], al
    jmp draw
save:
    mov dx, config
    xor cx, cx
    mov ax, 0x3C00
    int 0x21
    jc failed
    mov bx, ax
    mov dx, difficulty
    mov cx, 1
    mov ah, 0x40
    int 0x21
    pushf
    push ax
    mov ah, 0x3E
    int 0x21
    pop ax
    popf
    jc failed
    cmp ax, 1
    jne failed
continue:
    pop es
    pop ds
    popad
    popfd
    ; Patcher replaces this paragraph delta. Native CS:IP was 0000:0000.
    pushf
    push ax
    mov ax, cs
    sub ax, strict word 0xABCD
    mov [cs:original_cs], ax
    pop ax
    popf
    jmp far [cs:original_ip]
failed:
    mov dx, error
    mov ah, 9
    int 0x21
    xor ah, ah
    int 0x16
    jmp draw
difficulty: db 2
original_ip: dw 0
original_cs: dw 0
config: db 'TACTIC.DIF', 0
title: db 13,10,'ULTIMA VII TACTICAL PATCH v1.2',13,10
       db '==============================',13,10,13,10
       db 'Select difficulty before starting or loading a game.',13,10,13,10
       db '  1  Game Journalist   Enemy HP / damage: 25%',13,10
       db '  2  Easy              Enemy HP / damage: 75%',13,10
       db '  3  Normal            Original balance',13,10
       db '  4  Hard              Enemy HP / damage: 125%',13,10
       db '  5  Avatar            Enemy HP / damage: 200%',13,10,13,10
       db 'Current selection: $'
prompt: db 13,10,13,10,'Press 1-5 to change. Enter continues to the original main menu.',13,10,'$'
error: db 13,10,'Could not save TACTIC.DIF. Check that the game folder is writable.',13,10,'Press a key to try again.$'
