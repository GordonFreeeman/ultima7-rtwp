#!/usr/bin/env python3
"""Execute the actual compiled menu hooks with narrow native/DOS service stubs.

Without --payload, verify the compiled menu payload in the distributed
patch.json. To test edited source, assemble menu/menu.asm with NASM and pass
that binary explicitly. This does not replace native DOS menu verification.
"""
from pathlib import Path
import base64,hashlib,struct,json,zlib
from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE, UC_HOOK_INTR
from unicorn.x86_const import *
import argparse
parser=argparse.ArgumentParser(description='Execute the assembled native menu hook with narrowly scoped DOS/native service stubs.')
parser.add_argument('--payload',type=Path,help='NASM-assembled menu payload; defaults to verified patch.json payload')
parser.add_argument('--report',type=Path)
args=parser.parse_args()
if args.payload:
 payload=bytearray(args.payload.read_bytes())
else:
 record=json.loads((Path(__file__).resolve().parent.parent/'patch.json').read_text())['menu_payload']
 payload=bytearray(zlib.decompress(base64.b64decode(record['zlib_base64'],validate=True)))
 assert len(payload)==record['size'] and hashlib.sha256(payload).hexdigest()==record['sha256']
assert payload[:8]==b'U7NDIF2\0', 'Unsupported native graphical menu payload'
_,_,create,poll,cleanup,table,count,_=struct.unpack_from('<8H',payload,8)
return_hook=struct.unpack_from('<H',payload,24)[0]
for at in struct.unpack_from('<'+'H'*count,payload,table):struct.pack_into('<H',payload,at,struct.unpack_from('<H',payload,at)[0]+0x1000)
regs={'ax':UC_X86_REG_AX,'bx':UC_X86_REG_BX,'cx':UC_X86_REG_CX,'dx':UC_X86_REG_DX,'si':UC_X86_REG_SI,'di':UC_X86_REG_DI,'sp':UC_X86_REG_SP,'bp':UC_X86_REG_BP,'cs':UC_X86_REG_CS,'ds':UC_X86_REG_DS,'ss':UC_X86_REG_SS,'es':UC_X86_REG_ES}
payload_segment=0x45aa # Native retained DATA+5AA0 relation, not an unrelated CS.
payload_address=payload_segment*16

def scenario(event,write='ok',close='ok',exists=True,read=2,child_return=False,virtual_checks=False,return_draw=False):
 u=Uc(UC_ARCH_X86,UC_MODE_16);u.mem_map(0,0x100000);u.mem_write(payload_address,bytes(payload))
 for k,v in {'cs':payload_segment,'ds':0x4000,'ss':0x4000,'es':0x4000,'bp':0xe000,'si':0xe000-0x1560,'sp':0xb000}.items():u.reg_write(regs[k],v)
 native_vtable=bytearray.fromhex('1e 04 f5 0b 79 04 f5 0b 05 05 f5 0b bd 08 d5 09 85 02 d5 09 8c 02 d5 09 93 02 d5 09 76 01 f5 0b 34 05 d5 09 e9 05 d5 09 5a 03 f5 0b 83 03 f5 0b d3 03 f5 0b 88 03 f5 0b')
 for at in range(2,len(native_vtable),4):struct.pack_into('<H',native_vtable,at,struct.unpack_from('<H',native_vtable,at)[0]+0x1000)
 u.mem_write(0x41172,bytes(native_vtable))
 calls=[];data=bytes([read]) if exists else None
 native_addresses=[0x1c06d,0x1c116,0x1c558,0x1a722,0x19d02,0x19a7a,0x1c0c6,0x1e0d6,0x1aaa8,0x1c3c9]
 for addr in native_addresses:u.mem_write(addr,b'\xcb')
 def w(a,v):u.mem_write(a,struct.pack('<H',v))
 def r(a):return struct.unpack('<H',u.mem_read(a,2))[0]
 def carry(on):u.reg_write(UC_X86_REG_EFLAGS,(u.reg_read(UC_X86_REG_EFLAGS)|1) if on else (u.reg_read(UC_X86_REG_EFLAGS)&~1))
 def cstr(a):
  b=bytes(u.mem_read(a,100));return b.split(b'\0')[0].decode()
 def native(uc,address,size,_):
  nonlocal data
  sp=uc.reg_read(UC_X86_REG_SP)+0x40000
  if address==0x1c06d:
   ptr=r(sp+4);u.mem_write(0x40000+ptr,b'\0'*0x5e);w(0x40000+ptr+0x12,1);w(0x40000+ptr+0x50,8);w(0x40000+ptr+0x52,1);calls.append(['construct',ptr])
  elif address==0x1c116:
   label=cstr(r(sp+8)*16+r(sp+6));calls.append(['label',label]);w(0x40000+r(sp+4)+0x4e,len(label)*5)
  elif address==0x1a722:
   ptr=0x40000+r(sp+4);w(ptr+0x33,r(sp+6));w(ptr+0x35,r(sp+8))
  elif address==0x19a7a:uc.reg_write(UC_X86_REG_AX,event)
  elif address==0x1c0c6:calls.append(['destroy',r(sp+4)])
  elif address==0x1e0d6:calls.append(['palette_destroy',r(sp+4)])
  elif address==0x1aaa8:calls.append(['draw_root',r(sp+4),r(sp+6),r(sp+8)])
  elif address==0x1c3c9:calls.append(['draw_text',r(sp+4)])
  if address in native_addresses:u.mem_write(address,b'\xcb')
  if address==0x50000:uc.emu_stop()
 def intr(uc,number,_):
  nonlocal data
  assert number==0x21
  ax=uc.reg_read(UC_X86_REG_AX);dx=uc.reg_read(UC_X86_REG_DX);ds=uc.reg_read(UC_X86_REG_DS)*16;carry(False)
  if ax in (0x3d00,0x3d02):
   if data is None:carry(True);uc.reg_write(UC_X86_REG_AX,2)
   else:uc.reg_write(UC_X86_REG_AX,5)
  elif ax==0x5b00:
   assert data is None;data=b'';uc.reg_write(UC_X86_REG_AX,5)
  elif ax>>8==0x3f:
   u.mem_write(ds+dx,data);uc.reg_write(UC_X86_REG_AX,len(data))
  elif ax>>8==0x40:
   if write=='carry':carry(True);uc.reg_write(UC_X86_REG_AX,5)
   elif write=='short':uc.reg_write(UC_X86_REG_AX,0)
   else:data=bytes(u.mem_read(ds+dx,1));uc.reg_write(UC_X86_REG_AX,1)
  elif ax>>8==0x3e:
   if close=='carry':carry(True);uc.reg_write(UC_X86_REG_AX,5)
  elif ax>>8==0x41:data=None
  else:raise AssertionError(hex(ax))
 u.hook_add(UC_HOOK_CODE,native);u.hook_add(UC_HOOK_INTR,intr)
 def run(entry,arg=0,more=()):
  u.reg_write(UC_X86_REG_SP,0xb000);w(0x4b000,0);w(0x4b002,0x5000)
  for at,value in enumerate((arg,*more)):w(0x4b004+at*2,value)
  u.reg_write(UC_X86_REG_CS,payload_segment);u.emu_start(payload_address+entry,0x50000,count=100000)
  assert u.reg_read(UC_X86_REG_SP)==0xb004
 run(create)
 if return_draw:
  widget=0x40000+0xe000-0x1e60;w(widget+0x12,0);w(widget+0x10,1)
  preserved={'ax':0x3a3a,'bx':0x4b4b,'cx':0x5c5c,'dx':0x6d6d,'di':0x7e7e}
  for k,value in preserved.items():u.reg_write(regs[k],value)
  run(return_hook,0xe000-0x12d8,(0,0))
  assert r(widget+0x12)==1 and r(widget+0x10)==0
  assert calls[-1]==['draw_root',0xe000-0x12d8,0,0]
  assert all(u.reg_read(regs[k])==value for k,value in preserved.items())
 if child_return:w(0x40000+0xe000-0x1e60+0x12,0)
 run(poll);ret=u.reg_read(UC_X86_REG_AX)
 if child_return:assert ['draw_root',0xe000-0x12d8,0,0] in calls
 expected=0 if event==14 else event;assert ret==expected,(ret,expected)
 if event==14:
  last_label=[item for item in calls if item[0]=='label'][-1]
  assert calls[-1]==['draw_root',0xe000-0x12d8,0,0]
  if write=='ok' and close=='ok':assert data==bytes([(read+1)%5])
  else:assert last_label[1]=='DIFFICULTY: SAVE FAILED'
 if virtual_checks:
  ptr=0xe000-0x1e60;widget=0x40000+ptr;vt=0x40000+r(widget+0x17)
  inherited=bytes(u.mem_read(vt,0x38))
  assert inherited[:4]==bytes(native_vtable[:4]) and inherited[8:12]==bytes(native_vtable[8:12]) and inherited[16:]==bytes(native_vtable[16:])
  draw,draw_seg=struct.unpack('<HH',inherited[4:8]);hit,hit_seg=struct.unpack('<HH',inherited[12:16])
  assert draw_seg==hit_seg==payload_segment
  width=r(widget+0x4e);left=159-width//2;top=194-r(widget+0x50)+r(widget+0x52);bottom=194+r(widget+0x52)
  for x in (left,left+width//4,159,left+3*width//4,left+width-1):
   for y in (top,(top+bottom)//2,bottom):
    run(hit,ptr,(x,y));assert u.reg_read(UC_X86_REG_AX)==1,(x,y,width)
  for x,y in ((left-2,top),(left+width+1,top),(159,top-2),(159,bottom+2)):
   run(hit,ptr,(x,y));assert u.reg_read(UC_X86_REG_AX)==0,(x,y,width)
  # Actual native graphics addressing: flat row-pointer table, segment-relative
  # row pixels. Test the assembled palette translation on complete pixel memory,
  # including unchanged background,137,other colors and every exterior pixel.
  w(widget,0x6000);w(widget+2,0x7000);w(widget+4,0)
  u.mem_write(0x7000,b''.join(struct.pack('<I',y*320) for y in range(200)))
  pixels=bytes((0,131,132,133,134,135,136,137,255)[i%9] for i in range(320*200))
  u.mem_write(0x60000,pixels)
  u.mem_write(widget+0x14,b'\0');before=len(calls);run(draw,ptr)
  assert calls[before:]==[['draw_text',ptr]] and bytes(u.mem_read(0x60000,len(pixels)))==pixels
  u.mem_write(widget+0x14,b'\1');before=len(calls);run(draw,ptr)
  assert calls[before:]==[['draw_text',ptr]]
  expected=bytearray(pixels);mapping={132:131,133:132,134:132,135:133,136:133}
  for y in range(top,bottom+1):
   for x in range(left,left+width):
    at=y*320+x;expected[at]=mapping.get(expected[at],expected[at])
  assert bytes(u.mem_read(0x60000,len(pixels)))==bytes(expected),'Exact native glyph ramp and measured pixel bounds'
  assert u.reg_read(UC_X86_REG_DS)==0x4000 and u.reg_read(UC_X86_REG_ES)==0x4000
 run(cleanup,0x1234);assert calls[-1]==['palette_destroy',0x1234]
 return {'event':event,'write':write,'close':close,'exists':exists,'read':read,'child_return':child_return,'virtual_checks':virtual_checks,'return_draw':return_draw,'disk':None if data is None else data.hex(),'calls':calls,'passed':True}
results=[]
for event in [0,1,3,4,5,6,10,11,14]:results.append(scenario(event))
for level in range(5):results.append(scenario(14,read=level))
for mode in ['carry','short']:results.append(scenario(14,write=mode))
results.append(scenario(14,close='carry'));results.append(scenario(14,exists=False));results.append(scenario(14,exists=False,write='short'))
results.append(scenario(0,child_return=True))
for level in range(5):results.append(scenario(0,read=level,virtual_checks=True))
results.append(scenario(0,return_draw=True))
if args.report:args.report.write_text(json.dumps(results,indent=2)+'\n')
print(len(results),'native assembled hook scenarios passed')
