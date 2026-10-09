"""Hash-guarded native MAINMENU and Usecode edits, using only original files.

The package contains our menu code and Usecode insertion algorithm, not any
original game function or resource. Native branch destinations are relocated
by instruction boundary, retaining every original function and quest branch.
"""
from __future__ import annotations
import hashlib
import struct

MENU_HASH = '73d88ccdb103ee3c6ead70e64ed41eefa9312875ded98d93829979e2a511f43c'
USECODE_HASH = '49a3fcaf8a763972d0a6006571e8d8eef11eb1602f88898808b520523d0a8576'
MERCHANTS = {0x418:'Nystul', 0x44A:'Rudyom', 0x466:'Nicodemus',
             0x499:'Mariah', 0x4D8:'Wis-Sur', 0x4BC:'Sarpling'}
SHOP_ID = 0xB00
PRICE = 500
LENGTHS = {2:10,4:2,5:2,6:2,7:4,9:0,10:0,11:0,12:0,13:0,14:0,
           15:0,16:0,18:2,19:0,20:0,22:0,23:0,24:0,25:0,26:0,
           28:2,29:2,30:2,31:2,33:2,34:0,36:2,37:0,38:2,44:0,
           45:0,46:0,47:2,48:0,49:4,50:0,51:0,56:3,57:3,
           62:0,63:0,64:0,66:2,67:2,68:1,70:2,71:2,72:0,
           74:0,75:0}
BRANCHES = {2,4,5,6,7,49}

def require(condition, message):
    if not condition:
        raise ValueError(message)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def patch_menu(original, payload):
    """Install the resident extension in the actual native graphical menu.

    The supported Borland CRT reserves a near data/heap/stack arena. Merely
    appending a hook below its old stack would not make that hook resident.
    We reserve the extension between the original BSS end and the relocated
    near heap/stack boundary, retain the original BSS clear range, and give
    the original menu's 0x1DFC-byte frame a 0x4000-byte stack/near heap arena.
    """
    require(sha(original) == MENU_HASH, 'Unsupported MAINMENU.EXE')
    require(payload[:8] == b'U7NDIF2\0', 'Unsupported native menu payload')
    version, header, create, poll, cleanup, table, count, size = struct.unpack_from('<8H', payload, 8)
    return_draw = struct.unpack_from('<H', payload, 24)[0]
    require(version == 2 and header == 32 and size == len(payload), 'Invalid menu manifest')
    require(all(header <= entry < table for entry in (create, poll, cleanup, return_draw)), 'Invalid menu hooks')
    require(count == 10 and table + count*2 == len(payload), 'Invalid menu relocation table')
    reloc_words = struct.unpack_from('<'+'H'*count, payload, table)
    require(len(set(reloc_words)) == count and all(header <= at < table-1 for at in reloc_words),
            'Invalid menu segment locations')
    b = bytearray(original)
    load = struct.unpack_from('<H', b, 8)[0] * 16
    ip, cs = struct.unpack_from('<HH', b, 20)
    require(load == 0x2200 and (ip, cs) == (0, 0), 'Unexpected native menu layout')
    reloc_count = struct.unpack_from('<H', b, 6)[0]
    reloc_start = struct.unpack_from('<H', b, 24)[0]
    require((reloc_count, reloc_start) == (2112, 0x3E), 'Unexpected menu relocation header')
    relocations = [struct.unpack_from('<HH', b, reloc_start+i*4) for i in range(reloc_count)]
    locations = {segment*16+offset for offset, segment in relocations}
    require(len(locations) == reloc_count, 'Duplicate original menu relocation')

    def guard(image_offset, expected, replacement):
        at = load + image_offset
        require(b[at:at+len(expected)] == expected, f'Unexpected native menu bytes at {image_offset:05X}')
        require(len(expected) == len(replacement), 'Native menu edit changes instruction span')
        b[at:at+len(expected)] = replacement

    data_segment = 0x17D9
    old_bss_end = 0x5AA0
    # The new row inherits all native text virtual methods except its renderer
    # and pointer predicate. Validate the near-DATA vtable copied by the hook.
    require(b[load+data_segment*16+0x1172:load+data_segment*16+0x11AA] ==
            bytes.fromhex('1e 04 f5 0b 79 04 f5 0b 05 05 f5 0b bd 08 d5 09 '
                          '85 02 d5 09 8c 02 d5 09 93 02 d5 09 76 01 f5 0b '
                          '34 05 d5 09 e9 05 d5 09 5a 03 f5 0b 83 03 f5 0b '
                          'd3 03 f5 0b 88 03 f5 0b'),
            'Unexpected native text-widget virtual table')
    relative = data_segment*16 + old_bss_end
    require(len(b)-load < relative, 'Native menu payload overlaps file-backed original')
    segment = relative//16
    new_bss_end = ((old_bss_end+len(payload)+15)//16)*16
    require(new_bss_end+0x4000 < 0xFF00, 'Menu near arena overflow')
    require(b[load+0xC4:load+0xCA] == bytes.fromhex('bf fc 50 b9 a0 5a'),
            'Unexpected native BSS clear range')
    # DOS startup computes allocation/stack top from this end. The clear loop
    # deliberately keeps its old end: our file-backed reservation stays intact.
    guard(0x6B, bytes.fromhex('81 c7 a0 5a'), b'\x81\xC7'+struct.pack('<H',new_bss_end))
    for at in (0x9A, 0x9C):
        guard(data_segment*16+at, struct.pack('<H',old_bss_end), struct.pack('<H',new_bss_end))
    guard(data_segment*16+0x4D62, b'\x00\x10', b'\x00\x40')
    # The original self-size warning remains operative for this deliberate size.
    require(b[0x9A20:0x9A2B] == bytes.fromhex('83 7e ee 01 75 07 81 7e ec 8c f0'),
            'Unexpected native menu size check')
    # Extra text widget belongs to the original owner frame and is never a
    # dangling pointer to an appended segment interpreted as native near data.
    guard(0x565A, bytes.fromhex('c8 fc 1d 00'), bytes.fromhex('c8 60 1e 00'))
    for image_offset, expected, entry, existing in (
            (0x5BEE, bytes.fromhex('8a 46 ff b4 00'), create, False),
            (0x6203, bytes.fromhex('9a 2a 03 75 09'), poll, True),
            (0x65AD, bytes.fromhex('9a 38 0d d5 09'), return_draw, True),
            (0x6D8E, bytes.fromhex('9a 36 02 ea 0d'), cleanup, True)):
        word_at = image_offset+3
        require((word_at in locations) == existing, 'Unexpected native hook relocation')
        guard(image_offset, expected, b'\x9A'+struct.pack('<HH',entry,segment))
        if not existing:
            relocations.append((word_at%16,word_at//16))
            locations.add(word_at)
    # Retain all six native actions, names, image resources and original IDs.
    # Seven eight-pixel rows fit under the title at a twelve-pixel pitch.
    for at, old, new in ((0x5B7D,115,115), (0x5B8F,130,127),
                         (0x5BA2,145,139), (0x5BB5,160,151),
                         (0x5BC8,175,163), (0x5BDB,190,175)):
        expected = bytes([0x6A,old]) if old < 128 else b'\x68'+struct.pack('<H',old)
        replacement = bytes([0x6A,new]) if old < 128 else b'\x68'+struct.pack('<H',new)
        guard(at,expected,replacement)
    b.extend(b'\0'*(load+relative-len(b)))
    b.extend(payload)
    for at in reloc_words:
        address = relative+at
        require(address not in locations, 'Duplicate appended menu relocation')
        relocations.append((address%16,address//16))
        locations.add(address)
    require(reloc_start+len(relocations)*4 <= load, 'Menu relocation header has no capacity')
    for i, record in enumerate(relocations):
        struct.pack_into('<HH',b,reloc_start+i*4,*record)
    struct.pack_into('<H',b,6,len(relocations))
    require(len(b)//65536 < 128, 'Menu exceeds compact size-check range')
    b[0x9A23] = len(b)//65536
    struct.pack_into('<H',b,0x9A29,len(b)&65535)
    # Native entry is untouched. The initial DOS stack is above the extension;
    # the CRT then installs its retained 0x4000-byte near arena and stack.
    struct.pack_into('<H', b, 10, 0x400)
    struct.pack_into('<HH', b, 14, data_segment+new_bss_end//16, 0x80)
    struct.pack_into('<HH', b, 2, len(b)%512, (len(b)+511)//512)
    require(struct.unpack_from('<HH',b,20) == (0,0), 'Native menu entry changed')
    return bytes(b)

def functions(data):
    out = []
    pos = 0
    seen = set()
    while pos < len(data):
        require(pos+4 <= len(data), 'Truncated Usecode header')
        fid, size = struct.unpack_from('<HH', data, pos)
        require(fid not in seen and pos+4+size <= len(data), 'Invalid Usecode record')
        seen.add(fid)
        out.append((fid, data[pos+4:pos+4+size]))
        pos += 4+size
    return out

def decode(code):
    instructions = []
    pos = 0
    while pos < len(code):
        op = code[pos]
        require(op in LENGTHS, f'Unsupported native Usecode opcode {op:02x}')
        end = pos+1+LENGTHS[op]
        require(end <= len(code), 'Truncated Usecode instruction')
        target = None
        if op in BRANCHES:
            target = end + struct.unpack_from('<h',code,end-2)[0]
        instructions.append((pos,end,op,target))
        pos = end
    bounds = {x[0] for x in instructions} | {len(code)}
    require(all(x[3] is None or x[3] in bounds for x in instructions), 'Usecode branch splits instruction')
    return instructions

def word(op, value):
    return bytes([op])+struct.pack('<H',value&65535)

class Script:
    def __init__(self):
        self.code = bytearray()
        self.data = bytearray()
        self.labels = {}
        self.fixups = []
    def emit(self, data):
        self.code.extend(data)
    def label(self, name):
        self.labels[name] = len(self.code)
    def jump(self, op, name):
        self.emit(bytes([op])+b'\0\0')
        self.fixups.append((len(self.code)-2,name))
    def text(self, text):
        offset = len(self.data)
        self.data.extend(text.encode('ascii')+b'\0')
        self.emit(word(0x1C,offset)+b'\x33')
    def finish(self):
        for at,name in self.fixups:
            struct.pack_into('<h',self.code,at,self.labels[name]-(at+2))
        return bytes(self.code)

def shop_function():
    s = Script()
    s.text('"A spellbook costs 500 gold. Advanced spells must be bought separately. Buy one?"')
    s.emit(word(0x24,0)) # native Yes/No dialog, preserving outer answers
    s.jump(5,'end')
    # Native buy helper: shape, frame, base quantity, price, max/min quantity,
    # and flag, pushed in the native reverse argument order. max=0 buys one
    # directly. The original transaction checks gold and carry capacity.
    s.emit(b'\x14')
    for value in [1,0,PRICE,1,0,761]:
        s.emit(word(0x1F,value))
    s.emit(word(0x24,1)+word(0x12,0))
    for status,message in [(1,'"The spellbook is thine."'),
                           (2,'"Thou cannot carry the spellbook."'),
                           (3,'"Thou dost not have enough gold."')]:
        s.emit(word(0x21,0)+word(0x1F,status)+b'\x22')
        s.jump(5,f'next{status}')
        s.text(message)
        s.jump(6,'end')
        s.label(f'next{status}')
    s.label('end')
    s.emit(b'\x25')
    code = s.finish()
    return (struct.pack('<H',len(s.data))+s.data+
            struct.pack('<HHHHH',0,1,2,0x90A,0x8F8)+code)

def patch_merchant(body):
    size = struct.unpack_from('<H',body)[0]
    data = body[2:2+size]
    header = 2+size
    argc,locals_,count = struct.unpack_from('<HHH',body,header)
    externs = list(struct.unpack_from('<'+'H'*count,body,header+6))
    code = body[header+6+count*2:]
    instructions = decode(code)
    require(any(x[2]==4 for x in instructions), 'Merchant has no conversation')
    string_offset = len(data)
    data += b'spellbook\0'
    ext_index = len(externs)
    externs.append(SHOP_ID)
    mapping = {}
    output = bytearray()
    pending = []
    for pos,end,op,target in instructions:
        mapping[pos] = len(output)
        if op == 4:
            start = len(output)
            output.extend(word(0x1D,string_offset)+b'\x39\x05\x00\x01')
            actual = len(output)
            output.extend(code[pos:end])
            pending.append((len(output)-2,target))
            output.extend(word(0x1D,string_offset))
            # Skip this case when another answer was selected.
            output.extend(b'\x07\x01\x00\x06\x00')
            output.extend(word(0x24,ext_index))
            output.extend(word(6,start-(len(output)+3)))
        else:
            output.extend(code[pos:end])
            if target is not None:
                pending.append((len(output)-2,target))
    mapping[len(code)] = len(output)
    for at,target in pending:
        delta = mapping[target]-(at+2)
        require(-32768 <= delta <= 32767, 'Merchant branch overflow')
        struct.pack_into('<h',output,at,delta)
    decode(output)
    return (struct.pack('<H',len(data))+data+
            struct.pack('<HHH',argc,locals_,len(externs))+
            struct.pack('<'+'H'*len(externs),*externs)+output)

def patch_usecode(original):
    require(sha(original) == USECODE_HASH, 'Unsupported STATIC/USECODE')
    records = functions(original)
    require(SHOP_ID not in dict(records), 'Spellbook function ID already used')
    changed = set()
    output = bytearray()
    for fid,body in records:
        if fid in MERCHANTS:
            body = patch_merchant(body)
            changed.add(fid)
        require(len(body)<65536, 'Usecode function too large')
        output.extend(struct.pack('<HH',fid,len(body))+body)
    require(changed == set(MERCHANTS), 'Missing reagent merchant')
    body = shop_function()
    output.extend(struct.pack('<HH',SHOP_ID,len(body))+body)
    functions(output)
    return bytes(output)

def link_dependencies(usecode):
    """Native LINKDEP1/2: sorted transitive extern closures and file offsets.

    The DOS VM loads a function and its entire extern closure as one block.
    Every Usecode insertion therefore requires rebuilding both lookup files.
    """
    records = functions(usecode)
    by_id, position = {}, 0
    for fid, body in records:
        header = 2 + struct.unpack_from('<H', body)[0]
        count = struct.unpack_from('<H', body, header+4)[0]
        externs = struct.unpack_from('<'+'H'*count, body, header+6)
        by_id[fid] = (position, len(body), externs)
        position += 4+len(body)
    index, pointers = bytearray(), bytearray()
    for fid in range(max(by_id)+1):
        first = len(pointers)//4
        if fid not in by_id:
            index.extend(struct.pack('<HH', first, 65535))
            continue
        closure, pending = set(), [fid]
        while pending:
            item = pending.pop()
            if item in closure:
                continue
            require(item in by_id, f'Missing native extern {item:04x}')
            closure.add(item)
            pending.extend(by_id[item][2])
        total = sum(by_id[item][1] for item in closure)
        require(total < 65535 and first < 65536, 'Native dependency table overflow')
        index.extend(struct.pack('<HH', first, total))
        for item in sorted(closure):
            pointers.extend(struct.pack('<I', by_id[item][0]))
    require(len(pointers)//4 < 65536, 'Native dependency pointer overflow')
    index.extend(struct.pack('<HH', len(pointers)//4, 0))
    return bytes(index), bytes(pointers)
