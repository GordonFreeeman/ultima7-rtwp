#!/usr/bin/env python3
"""Check native panel font fit and execute its assembled UI geometry routines.

Requires NASM and Unicorn. This is isolated 16-bit execution of the actual
assembled panel code, not a DOS/gameplay test. The native mouse poll is stubbed
only to supply controlled native MouseState events; drawing calls are observed
at their existing near helper boundary. Run in addition to native DOS review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

from native_patcher import BASELINE_SHA256, Executable, read_patch


EXPORTS = (
    'offsetInCodeSegment(tactical_panel_init)',
    'offsetInCodeSegment(tactical_panel_mouse)',
    'offsetInCodeSegment(tactical_panel_hit)',
    'offsetInCodeSegment(panel_buttons)',
    'offsetInCodeSegment(panel_draw_button)',
    'offsetInCodeSegment(panel_fill_relative)',
    'offsetInCodeSegment(panel_text)',
    'Panel_WIDTH', 'Panel_HEIGHT', 'Panel_INITIAL_X', 'Panel_INITIAL_Y',
    'Panel_TITLE_X', 'Panel_TITLE_Y', 'Panel_TITLE_HEIGHT',
    'Panel_HIDE_X', 'Panel_HIDE_WIDTH',
    'Panel_PARTY_X', 'Panel_PARTY_Y', 'Panel_PARTY_WIDTH',
    'Panel_PARTY_HEIGHT', 'Panel_PARTY_PITCH', 'Panel_PARTY_COUNT',
    'Panel_BUTTON_TEXT_X', 'Panel_BUTTON_TEXT_Y',
    'Panel_REOPEN_X', 'Panel_REOPEN_Y', 'Panel_REOPEN_WIDTH',
    'Panel_REOPEN_HEIGHT', 'panel_button_count',
    'dseg_panel_magic', 'dseg_panel_visible', 'dseg_panel_dragging',
    'dseg_panel_x', 'dseg_panel_y', 'dseg_panel_drag_x',
    'dseg_panel_drag_y', 'dseg_panel_pending', 'dseg_partySize',
    'segmentFromOverlay_updateAndGetMouseState',
    'off_updateAndGetMouseState',
    'offsetInCodeSegment(panel_hide)',
    'offsetInCodeSegment(panel_reopen)',
)


def check(game: Path, nasm: str):
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE
    from unicorn.x86_const import (
        UC_X86_REG_AX, UC_X86_REG_BX, UC_X86_REG_CX, UC_X86_REG_DX,
        UC_X86_REG_SI, UC_X86_REG_DI, UC_X86_REG_BP, UC_X86_REG_SP,
        UC_X86_REG_CS, UC_X86_REG_DS, UC_X86_REG_SS, UC_X86_REG_IP,
    )

    original = (game / 'TACTICAL-PATCH' / 'U7.ORI').read_bytes()
    assert hashlib.sha256(original).hexdigest() == BASELINE_SHA256
    native = Executable(original)
    dseg = native.segments[349]
    spacing = struct.unpack_from('<h', original, dseg.start + 0x3753 + 2*2)[0]
    assert spacing == 0, 'The verified native small-font spacing must be zero'

    source = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='u7-panel-check-') as temp:
        wrapper = Path(temp) / 'panel-check.asm'
        obj = Path(temp) / 'panel-check.o'
        wrapper.write_text('%include "pause.asm"\n' + '\n'.join(
            'dw ' + name for name in EXPORTS) + '\n')
        subprocess.run([nasm, str(wrapper), '-o', str(obj)], cwd=source, check=True)
        assembled = obj.read_bytes()
    n = 2 * len(EXPORTS)
    values = struct.unpack('<' + 'H'*len(EXPORTS), assembled[-n:])
    g = dict(zip(EXPORTS, values))
    _, _, blocks = read_patch(assembled[:-n])
    overlay = next(b for b in blocks if b[0] == 336 and b[1] == 0x0D80)
    _, start, code, _ = overlay

    def address(name):
        return g['offsetInCodeSegment(' + name + ')']

    def cstring(at):
        lo = at - start
        return code[lo:code.index(0, lo)].decode('ascii')

    buttons = [struct.unpack_from('<6H', code, address('panel_buttons')-start+i*12)
               for i in range(g['panel_button_count'])]
    assert [b[4] for b in buttons] == list(map(ord, 'tmrghaic '))
    fontfile = (game / 'STATIC' / 'FONTS.VGA').read_bytes()
    font_at, font_size = struct.unpack_from('<II', fontfile, 0x80 + 2*8)
    font = fontfile[font_at:font_at+font_size]
    assert struct.unpack_from('<I', font)[0] == len(font)

    def metrics(text):
        glyphs = []
        for ch in text:
            off = struct.unpack_from('<I', font, 4+ord(ch)*4)[0]
            assert 0 <= off <= len(font)-8
            glyphs.append(struct.unpack_from('<4h', font, off))
        return (sum(right+left+1+spacing for right, left, _, _ in glyphs),
                max(above for _, _, above, _ in glyphs),
                max(below for _, _, _, below in glyphs))

    labels = []
    controls = [(cstring(b[5]), b[2], b[3], g['Panel_BUTTON_TEXT_X'],
                 g['Panel_BUTTON_TEXT_Y']) for b in buttons]
    controls += [(cstring(address('panel_hide')), g['Panel_HIDE_WIDTH'],
                  g['Panel_TITLE_HEIGHT'], g['Panel_BUTTON_TEXT_X'],
                  g['Panel_BUTTON_TEXT_Y']),
                 (cstring(address('panel_reopen')), g['Panel_REOPEN_WIDTH'],
                  g['Panel_REOPEN_HEIGHT'], 5, 3)]
    for text, width, height, tx, ty in controls:
        pixels, above, below = metrics(text)
        assert tx >= 3 and width-tx-pixels >= 3, (text, pixels, width)
        # panel_print_small translates top position to the native baseline +7.
        assert ty+7-above >= 3 and height-1-(ty+7+below) >= 3
        labels.append({'label': text, 'font_width': pixels,
                       'control': [width, height],
                       'horizontal_padding': [tx, width-tx-pixels]})
    for x, y, width, height, _, _ in buttons:
        assert x >= 3 and y >= 3
        assert x+width <= g['Panel_WIDTH']-3
        assert y+height <= g['Panel_HEIGHT']-3
    for i, a in enumerate(buttons):
        for b in buttons[i+1:]:
            assert (a[0]+a[2] <= b[0] or b[0]+b[2] <= a[0]
                    or a[1]+a[3] <= b[1] or b[1]+b[3] <= a[1])

    uc = Uc(UC_ARCH_X86, UC_MODE_16)
    uc.mem_map(0, 0x100000)
    cs, ds = 0x3000, 0x2000
    uc.mem_write(cs*16+start, code)
    uc.reg_write(UC_X86_REG_CS, cs)
    uc.reg_write(UC_X86_REG_DS, ds)
    uc.reg_write(UC_X86_REG_SS, ds)
    sentinel, mouse = 0xFFF0, 0x9000
    poll = g['segmentFromOverlay_updateAndGetMouseState']*16 + g['off_updateAndGetMouseState']
    uc.mem_write(poll, b'\xB8' + struct.pack('<H', mouse) + b'\xCB')

    def byte(name, value):
        uc.mem_write(ds*16+g[name], bytes([value]))

    def word(name, value):
        uc.mem_write(ds*16+g[name], struct.pack('<H', value & 0xFFFF))

    def readword(name):
        return struct.unpack('<H', uc.mem_read(ds*16+g[name], 2))[0]

    def run(name, ax=0, dx=0):
        uc.reg_write(UC_X86_REG_AX, ax & 0xFFFF)
        uc.reg_write(UC_X86_REG_DX, dx & 0xFFFF)
        uc.reg_write(UC_X86_REG_SP, 0xFF00)
        uc.mem_write(ds*16+0xFF00, struct.pack('<H', sentinel))
        uc.emu_start(cs*16+address(name), cs*16+sentinel, count=2000)
        assert uc.reg_read(UC_X86_REG_IP) == sentinel
        return uc.reg_read(UC_X86_REG_AX)

    def contains(x, y, rect):
        rx, ry, width, height = rect
        return rx <= x < rx+width and ry <= y < ry+height

    def expected(x, y, px, py, party):
        x, y = x-px, y-py
        if contains(x, y, [g['Panel_TITLE_X'], g['Panel_TITLE_Y'],
                           g['Panel_WIDTH']-2*g['Panel_TITLE_X'], g['Panel_TITLE_HEIGHT']]):
            return 9 if contains(x, y, [g['Panel_HIDE_X'], g['Panel_TITLE_Y'],
                                       g['Panel_HIDE_WIDTH'], g['Panel_TITLE_HEIGHT']]) else 0xFFFE
        for i in range(party):
            if contains(x, y, [g['Panel_PARTY_X']+i*g['Panel_PARTY_PITCH'],
                               g['Panel_PARTY_Y'], g['Panel_PARTY_WIDTH'], g['Panel_PARTY_HEIGHT']]):
                return ord('1')+i
        for bx, by, width, height, key, _ in buttons:
            if contains(x, y, [bx, by, width, height]):
                return key
        return 0

    byte('dseg_panel_visible', 1)
    points = 0
    positions = [(g['Panel_INITIAL_X'], g['Panel_INITIAL_Y'], party) for party in [1, 3, 9]]
    positions += [(0, 0, 9), (320-g['Panel_WIDTH'], 200-g['Panel_HEIGHT'], 9)]
    for px, py, party in positions:
        word('dseg_panel_x', px)
        word('dseg_panel_y', py)
        byte('dseg_partySize', party)
        for y in range(-1, g['Panel_HEIGHT']+1):
            for x in range(-1, g['Panel_WIDTH']+1):
                actual = run('tactical_panel_hit', x+px, y+py)
                assert actual == expected(x+px, y+py, px, py, party), (x, y, actual)
                points += 1

    byte('dseg_panel_visible', 0)
    reopen = [g['Panel_REOPEN_X'], g['Panel_REOPEN_Y'],
              g['Panel_REOPEN_WIDTH'], g['Panel_REOPEN_HEIGHT']]
    for y in range(reopen[1]-1, reopen[1]+reopen[3]+1):
        for x in range(reopen[0]-1, reopen[0]+reopen[2]+1):
            assert run('tactical_panel_hit', x, y) == (9 if contains(x, y, reopen) else 0)
            points += 1

    byte('dseg_panel_magic', 0)
    run('tactical_panel_init')
    assert [readword('dseg_panel_x'), readword('dseg_panel_y')] == [g['Panel_INITIAL_X'], g['Panel_INITIAL_Y']]
    for x, y in [(-1, -1), (319, 199), (104, 80), (4, 76)]:
        word('dseg_panel_x', x)
        word('dseg_panel_y', y)
        run('tactical_panel_init')
        assert readword('dseg_panel_x') == max(0, min(x, 320-g['Panel_WIDTH']))
        assert readword('dseg_panel_y') == max(0, min(y, 200-g['Panel_HEIGHT']))

    byte('dseg_panel_visible', 1)
    byte('dseg_partySize', 9)
    def event(x, y, action, bits, button=1):
        uc.mem_write(ds*16+mouse, struct.pack('<BBhhBBI', 0, button, x*2, y, bits, action, 0))
        return run('tactical_panel_mouse')

    # Check real doubled native X coordinates, release activation and cancellation.
    word('dseg_panel_x', g['Panel_INITIAL_X'])
    word('dseg_panel_y', g['Panel_INITIAL_Y'])
    for bx, by, _, _, key, _ in buttons:
        x, y = bx+g['Panel_INITIAL_X']+2, by+g['Panel_INITIAL_Y']+2
        assert event(x, y, 1, 1) == 0
        assert event(x, y, 3, 0) == key
        assert event(x, y, 1, 1) == 0
        assert event(319, 199, 3, 0) == 0
    # A held title drag keeps the entire panel inside all four screen edges.
    word('dseg_panel_x', 4)
    word('dseg_panel_y', 76)
    assert event(14, 84, 1, 1) == 0
    assert event(-50, -50, 4, 1) == 0xFFFF
    assert [readword('dseg_panel_x'), readword('dseg_panel_y')] == [0, 0]
    assert event(400, 300, 4, 1) == 0xFFFF
    assert [readword('dseg_panel_x'), readword('dseg_panel_y')] == [320-g['Panel_WIDTH'], 200-g['Panel_HEIGHT']]
    assert event(400, 300, 3, 0) == 0

    # Observe the actual button helper's fill rectangles and text inset.
    observed = []
    def observe(machine, at, size, user):
        if at not in [cs*16+address('panel_fill_relative'), cs*16+address('panel_text')]:
            return
        observed.append((at, [machine.reg_read(reg) for reg in
                             [UC_X86_REG_AX, UC_X86_REG_BX, UC_X86_REG_DX, UC_X86_REG_SI, UC_X86_REG_DI]]))
        sp = machine.reg_read(UC_X86_REG_SP)
        ret = struct.unpack('<H', machine.mem_read(ds*16+sp, 2))[0]
        machine.reg_write(UC_X86_REG_SP, sp+2)
        machine.reg_write(UC_X86_REG_IP, ret)
    hook = uc.hook_add(UC_HOOK_CODE, observe)
    for bx, by, width, height, _, label in buttons:
        observed.clear()
        uc.reg_write(UC_X86_REG_BX, bx)
        uc.reg_write(UC_X86_REG_SI, width)
        uc.reg_write(UC_X86_REG_DI, height)
        run('panel_draw_button', label, by)
        assert len(observed) == 3
        assert observed[0][1] == [141, bx, by, width, height]
        assert observed[1][1] == [134, bx+1, by+1, width-2, height-2]
        assert observed[2][1][:3] == [label, bx+g['Panel_BUTTON_TEXT_X'], by+g['Panel_BUTTON_TEXT_Y']]
    uc.hook_del(hook)
    return {'panel_size': [g['Panel_WIDTH'], g['Panel_HEIGHT']],
            'default_position': [g['Panel_INITIAL_X'], g['Panel_INITIAL_Y']],
            'drag_limits': [320-g['Panel_WIDTH'], 200-g['Panel_HEIGHT']],
            'labels': labels, 'assembled_hit_points_checked': points,
            'checks': ['native font fit', 'assembled hitboxes and inert gaps',
                       'hidden Show hitbox', 'initial/remembered position clamping',
                       'native mouse command release/cancellation', 'four-edge drag bounds',
                       'assembled button fill/text geometry'],
            'scope': 'isolated assembled UI routines; native DOS visual review is separate'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('game', type=Path, help='Blackgat directory containing native fonts and TACTICAL-PATCH/U7.ORI')
    parser.add_argument('--nasm', default=shutil.which('nasm') or 'nasm')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = check(args.game, args.nasm)
    encoded = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.write_text(encoded)
    print(encoded)
