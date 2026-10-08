#!/usr/bin/env python3
"""Bounded MZ/FBOV patcher for the supplied Ultima VII Black Gate 3.4.

The FBOV layout and NASM block footer format are documented in John Glassmyer's
MIT-licensed UltimaHacks. This implementation deliberately supports only the
hash-identified input, retains loader-managed overlays, and rejects unsafe edits.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

BASELINE_SHA256 = '4d588b12c775927c77c221531be4910eaf413864a8e2ec3f6f0d7a9c302b6e54'
BASELINE_SIZE = 0xA8460
ORIGINAL_HOOKS = (
    (86, 0x1CDB, '8b 1c 8e 06 36 4b'),
    (219, 0x0008, '8b 7e 06 8b 76 08'),
    (219, 0x280F, '9a 65 00 58 01'),
    (219, 0x285D, '9a 65 00 58 01'),
    (219, 0x3B89, '9a 65 00 58 01'),
    (219, 0x2187, '9a 65 00 58 01'),
    (219, 0x2978, '9a 65 00 58 01'),
    (219, 0x29E7, '9a 65 00 58 01'),
    (215, 0x01BC, '26 8a 47 10 b4 00'),
    (215, 0x0339, '26 8a 47 10 b4 00'),
    (215, 0x035E, '58 26 88 47 10'),
    (30, 0x0084, '9a c2 02 3e 1c'),
    (31, 0x0FAB, '9a 61 01 3e 1c'),
    # All native combat-end owners: world input, scripted action, and UI.
    (31, 0x0A0B, '9a 20 00 2a 3d'),
    (318, 0x0346, '9a 20 00 d0 06'),
    (342, 0x165E, '9a 20 00 d0 06'),
    # Symmetric native combat-start owners keep saved command defaults current.
    (31, 0x0A1F, '9a 25 00 2a 3d'),
    (219, 0x301D, '9a 25 00 d0 06'),
    (342, 0x1682, '9a 25 00 d0 06'),
    # Native Avatar movement must not reset a manually controlled companion.
    (4, 0x07AB, '9a d9 02 fd 1f'),
    # Original world-picker poll and event dispatch; tactical cancellation
    # restores its cursor and leaves uncommitted output arguments untouched.
    (234, 0x0039,
     '8d 46 e6 50 9a ff 06 c0 01 44 44 80 7e ed 00 74 05 '
     'b8 01 00 eb 02 33 c0 0a c0 75 03 e9 a1 00 80 7e ed '
     '04 75 05 b8 01 00 eb 02 33 c0 b4 00 0b c0 74 03 e9 8b 00'),
    (340, 0x0304, 'b8 0c 10 50 90 0e e8 09 0e'),
    (340, 0x1454, 'b8 0c 10 50 0e e8 ba fc'),
    (340, 0x1700, 'b8 0c 10 50 0e e8 0e fa'),
    (344, 0x0FB3, '9a 2a 00 f0 07'),
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


@dataclasses.dataclass
class Segment:
    index: int
    table: int
    base: int
    lo: int
    hi: int
    flags: int
    resident: int
    start: int
    size: int
    relpos: int = 0
    relcount: int = 0
    procs: int = 0

    @property
    def overlay(self):
        return bool(self.flags & 2)


class Executable:
    def __init__(self, data):
        self.data = bytearray(data)
        self.changes = []
        self.parse()

    def u16(self, at):
        require(0 <= at <= len(self.data) - 2, f'Word outside file: {at:#x}')
        return struct.unpack_from('<H', self.data, at)[0]

    def u32(self, at):
        require(0 <= at <= len(self.data) - 4, f'Dword outside file: {at:#x}')
        return struct.unpack_from('<I', self.data, at)[0]

    def parse(self):
        b = self.data
        require(b[:2] == b'MZ', 'Not an MZ executable')
        self.load = self.u16(8) * 16
        self.mzend = (self.u16(4) - 1) * 512 + (self.u16(2) or 512)
        require(b[self.mzend:self.mzend + 4] == b'FBOV', 'Missing FBOV header')
        self.fbovend = self.mzend + 16
        self.table = self.u32(self.mzend + 8)
        count = self.u32(self.mzend + 12)
        require(1 <= count <= 4096, 'Invalid segment count')
        require(self.table + count * 8 <= self.mzend, 'Segment table outside resident image')
        require(self.fbovend + self.u32(self.mzend + 4) == len(b), 'FBOV byte count mismatch')
        self.mzrelpos = self.u16(0x18)
        self.mzrelcount = self.u16(6)
        require(self.mzrelpos + self.mzrelcount * 4 <= self.load, 'MZ relocations overlap code')
        self.segments = []
        for i in range(count):
            t = self.table + i * 8
            base, hi, flags, lo = struct.unpack_from('<4H', b, t)
            resident = self.load + 16 * base
            # Non-code descriptors also describe BSS and empty linker ranges:
            # e.g. native segments 200-204 have a FFFF end; 350-358 end below
            # their start. These descriptors are retained, never materialized.
            if flags & 1:
                require(lo <= hi and resident + hi <= self.mzend,
                        f'Code segment {i} exceeds MZ image')
            file_size = max(0, min(hi, self.mzend - resident)) if lo <= hi else 0
            s = Segment(i, t, base, lo, hi, flags, resident, resident, file_size)
            if s.overlay:
                require(lo == 0 and hi >= 32, f'Invalid overlay stub {i}')
                s.start = self.fbovend + self.u32(resident + 4)
                s.size = self.u16(resident + 8)
                s.relcount = self.u16(resident + 10) // 2
                s.procs = self.u16(resident + 12)
                s.relpos = s.start + s.size
                require(self.u16(resident + 10) % 2 == 0, f'Odd relocation length {i}')
                require(32 + s.procs * 5 <= hi, f'Invalid procedure count {i}')
                require(self.fbovend <= s.start <= s.relpos <= len(b), f'Invalid overlay {i}')
                require(s.relpos + s.relcount * 2 <= len(b), f'Invalid relocations {i}')
                for n in range(s.relcount):
                    require(self.u16(s.relpos + n * 2) + 1 < s.size,
                            f'Overlay relocation outside code {i}')
                for n in range(s.procs):
                    require(self.u16(resident + 32 + n * 5 + 2) < s.size,
                            f'Overlay entry outside code {i}')
            self.segments.append(s)

    def write(self, at, data, description):
        data = bytes(data)
        require(0 <= at <= len(self.data) - len(data), f'Out of bounds write: {description}')
        before = bytes(self.data[at:at + len(data)])
        if before == data:
            return
        self.changes.append({'description': description, 'offset': at, 'length': len(data),
                             'before_sha256': hashlib.sha256(before).hexdigest(),
                             'after_sha256': hashlib.sha256(data).hexdigest()})
        self.data[at:at + len(data)] = data

    def expand(self, index=336, code_size=0x5000, relocation_reserve=0x1000):
        s = self.segments[index]
        require(s.overlay and s.lo == 0, 'Expansion target must be an overlay')
        require(s.size <= code_size < 0x10000, 'Invalid expanded code size')
        require(s.relcount * 2 <= relocation_reserve, 'Insufficient relocation reservation')
        next_start = min(x.resident + x.lo for x in self.segments
                         if x.resident + x.lo > s.resident)
        require(next_start - (s.resident + s.hi) >= 15, 'No room for three stub entries')
        old_code = bytes(self.data[s.start:s.start + s.size])
        old_reloc = bytes(self.data[s.relpos:s.relpos + 2 * s.relcount])
        new_start = len(self.data)
        extra = code_size + relocation_reserve
        self.data.extend(b'\0' * extra)
        self.write(new_start, old_code, f'Copy original overlay {index} code')
        self.write(new_start + code_size, old_reloc, f'Copy overlay {index} relocations')
        self.write(self.mzend + 4, struct.pack('<I', len(self.data) - self.fbovend), 'FBOV byte count')
        self.write(s.table + 2, struct.pack('<H', s.hi + 15), 'Expanded resident stub bound')
        self.write(s.resident + 4, struct.pack('<IHHH', new_start - self.fbovend,
                   code_size, s.relcount * 2, s.procs + 3), 'Expanded overlay metadata')
        for i in range(3):
            entry = s.size + 5 * i
            self.write(s.resident + 32 + (s.procs + i) * 5,
                       b'\xcd\x3f' + struct.pack('<H', entry) + b'\0', f'New tactical entry {i}')
            self.write(new_start + entry, b'\xcb', f'Default RETF for entry {i}')
        self.parse()

    def patch(self, objects):
        mz_original = [(self.u16(self.mzrelpos + i * 4), self.u16(self.mzrelpos + i * 4 + 2))
                       for i in range(self.mzrelcount)]
        mzrels = {seg * 16 + off for off, seg in mz_original}
        ovrels = {s.index: {self.u16(s.relpos + i * 2) for i in range(s.relcount)}
                  for s in self.segments if s.overlay}
        old_ovrels = {k: set(v) for k, v in ovrels.items()}
        occupied = {}
        manifest = []
        for objpath in objects:
            desc, target, blocks = read_patch(Path(objpath).read_bytes())
            require(target == len(self.data), f'Patch {desc} expects a different executable length')
            for index, start, payload, relocations in blocks:
                require(0 <= index < len(self.segments), f'Invalid segment index {index}')
                s = self.segments[index]
                end = start + len(payload)
                require(s.lo <= start < end <= s.size, f'Patch outside segment: {desc} {index}:{start:x}')
                for a, z in occupied.setdefault(index, []):
                    require(end <= a or start >= z, f'Overlapping patches in segment {index}')
                occupied[index].append((start, end))
                require(all(0 <= r and r + 1 < len(payload) for r in relocations), 'Invalid block relocation')
                base = 0 if s.overlay else s.base * 16
                relset = ovrels[index] if s.overlay else mzrels
                a, z = base + start, base + end
                require(a - 1 not in relset, f'Patch splits a relocation at {a - 1:x}')
                require(z - 1 not in relset, f'Patch splits a relocation at {z - 1:x}')
                relset.difference_update([x for x in relset if a <= x < z])
                relset.update(a + x for x in relocations)
                self.write(s.start + start, payload, f'{desc}: {index}:{start:04X}')
                manifest.append({'patch': desc, 'segment': index, 'offset': start,
                                 'file_offset': s.start + start, 'length': len(payload),
                                 'relocations': sorted(relocations)})
        # Retain the original representation/order of unchanged DOS relocations.
        mz_out, seen = [], set()
        for off, seg in mz_original:
            linear = seg * 16 + off
            if linear in mzrels:
                mz_out.append(struct.pack('<HH', off, seg))
                seen.add(linear)
        for linear in sorted(mzrels - seen):
            mz_out.append(struct.pack('<HH', linear & 15, linear >> 4))
        mzbytes = b''.join(mz_out)
        require(self.mzrelpos + len(mzbytes) <= self.load, 'Expanded MZ relocation table exceeds header')
        self.write(6, struct.pack('<H', len(mz_out)), 'MZ relocation count')
        self.write(self.mzrelpos, mzbytes, 'MZ relocation table')
        for index, relset in ovrels.items():
            if relset == old_ovrels[index]:
                continue
            s = self.segments[index]
            next_start = min([x.start for x in self.segments if x.overlay and x.start > s.start]
                             + [len(self.data)])
            payload = b''.join(struct.pack('<H', x) for x in sorted(relset))
            if s.relpos + len(payload) > next_start:
                # A native overlay with no relocation slack is moved whole.
                # Code and entry offsets stay unchanged; only its FBOV locator
                # and relocation count change. No neighboring overlay moves.
                code = bytes(self.data[s.start:s.start + s.size])
                new_start = len(self.data)
                self.data.extend(b'\0' * (s.size + len(payload)))
                self.write(new_start, code, f'Relocate overlay {index} for extra far-call relocations')
                self.write(s.resident + 4, struct.pack('<I', new_start - self.fbovend),
                           f'Overlay {index} FBOV locator')
                for record in manifest:
                    if record['segment'] == index:
                        record['file_offset'] = new_start + record['offset']
                s.start = new_start
                s.relpos = new_start + s.size
            self.write(s.resident + 10, struct.pack('<H', len(payload)), f'Overlay {index} relocation byte count')
            self.write(s.relpos, payload, f'Overlay {index} relocation table')
        self.write(self.mzend + 4, struct.pack('<I', len(self.data) - self.fbovend), 'Final FBOV byte count')
        self.parse()
        return manifest


def read_patch(data):
    """Read the backwards NASM metadata without executing any input."""
    cursor = len(data)

    def take(n):
        nonlocal cursor
        require(0 <= n <= cursor, 'Truncated NASM patch object')
        cursor -= n
        return data[cursor:cursor + n]

    def dword():
        return struct.unpack('<I', take(4))[0]

    desc = take(dword()).decode('utf-8')
    target = dword()
    count = dword()
    require(0 < count <= 4096, 'Invalid block count')
    blocks = []
    for _ in range(count):
        segment = dword()
        start = dword()
        nrel = dword()
        require(nrel <= 32768, 'Invalid relocation count')
        rel = [dword() for _ in range(nrel)]
        payload = take(dword())
        blocks.append((segment, start, payload, rel))
    require(cursor == 0, 'Extra bytes before patch metadata')
    return desc, target, list(reversed(blocks))


def build(original, output, nasm, source_dir):
    original, output, source_dir = Path(original), Path(output), Path(source_dir)
    data = original.read_bytes()
    require(len(data) == BASELINE_SIZE and hashlib.sha256(data).hexdigest() == BASELINE_SHA256,
            'Unknown U7.EXE. This patch requires the exact supplied Black Gate 3.4 executable.')
    require(original.resolve() != output.resolve(), 'Build to a separate output, never over the baseline')
    exe = Executable(data)
    for segment, offset, expected_hex in ORIGINAL_HOOKS:
        expected = bytes.fromhex(expected_hex)
        start = exe.segments[segment].start + offset
        require(data[start:start + len(expected)] == expected,
                f'Original instruction guard failed at {segment}:{offset:04X}')
    exe.expand()
    sources = sorted(source_dir.glob('*.asm'))
    require(sources, 'No patch assembly sources')
    with tempfile.TemporaryDirectory(prefix='u7-tactical-') as temp:
        objects = []
        for src in sources:
            obj = Path(temp) / (src.stem + '.o')
            subprocess.run([str(nasm), str(src.resolve()), '-o', str(obj)],
                           cwd=source_dir, check=True)
            objects.append(obj)
        blocks = exe.patch(objects)
    output.parent.mkdir(parents=True, exist_ok=True)
    tempout = output.with_suffix(output.suffix + '.tmp')
    tempout.write_bytes(exe.data)
    require(Executable(tempout.read_bytes()).data == exe.data, 'Output verification failed')
    tempout.replace(output)
    report = {'input_sha256': BASELINE_SHA256,
              'output_sha256': hashlib.sha256(exe.data).hexdigest(),
              'input_size': len(data), 'output_size': len(exe.data),
              'blocks': blocks, 'changes': exe.changes}
    output.with_suffix(output.suffix + '.build.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('original')
    parser.add_argument('output')
    parser.add_argument('--nasm', default=shutil.which('nasm') or 'nasm')
    parser.add_argument('--source', default=str(Path(__file__).resolve().parent))
    args = parser.parse_args()
    result = build(args.original, args.output, args.nasm, args.source)
    print(json.dumps({k: result[k] for k in ('input_sha256', 'output_sha256', 'output_size')}, indent=2))
