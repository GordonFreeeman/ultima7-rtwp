#!/usr/bin/env python3
"""Execute the delivered 16-bit machine code, with narrow native-service stubs."""
import json,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools/python'),str(ROOT/'source')]
from unicorn import Uc,UC_ARCH_X86,UC_MODE_16,UC_HOOK_CODE
from unicorn.x86_const import *
from native_patcher import Executable
exe=Executable((ROOT/'build/U7-V12.EXE').read_bytes());s=exe.segments[336]
code=bytes(exe.data[s.start:s.start+s.size]);at=code.index(b'U7T12SYM')+8
names=['init','damage','rng','magic_restored','mana_read','mana_write','eligible','tick','mana_init','open_book','new_book']
syms=dict(zip(names,struct.unpack_from('<11H',code,at)))
DS,CS,ES=0x2000,0x4000,0x6000
class Machine:
 def __init__(self,difficulty=2,restored=False):
  self.u=Uc(UC_ARCH_X86,UC_MODE_16);u=self.u;u.mem_map(0,0x100000);u.mem_write(CS*16,code);u.mem_write(CS*16+0xff00,b'\xf4')
  for r,v in [(UC_X86_REG_DS,DS),(UC_X86_REG_SS,DS),(UC_X86_REG_CS,CS),(UC_X86_REG_ES,ES),(UC_X86_REG_FS,0x1111),(UC_X86_REG_GS,0x2222)]:u.reg_write(r,v)
  self.w(0x1064,b'\xd2'+bytes([difficulty]));self.word(0x30b9,2);self.word(0x3089,0x110);self.word(0x308b,0x112);self.word(0x4c0c,0x110)
  self.word(0x5fa4,1024);self.word(0x5fa0,0x300);self.word(0x5fa2,ES);u.mem_write(ES*16+0x300,bytes([0x10 if restored else 0]))
  self.bound=[];self.rng_value=0;self.actors={0x110:0,0x112:1,0x114:20,0x116:21};self.trace=[]
  u.hook_add(UC_HOOK_CODE,self.hook)
 def w(self,o,b):self.u.mem_write(DS*16+o,b)
 def word(self,o,v):self.w(o,struct.pack('<H',v))
 def read(self,o,n=2):return int.from_bytes(self.u.mem_read(DS*16+o,n),'little')
 def hook(self,u,address,size,data):
  ins=bytes(u.mem_read(address,size))
  if ins[:1]!=b'\x9a':return
  off,seg=struct.unpack('<HH',ins[1:]);sp=u.reg_read(UC_X86_REG_SP);arg=lambda i:int.from_bytes(u.mem_read(DS*16+sp+i*2,2),'little')
  if (seg,off)==(0,0x31ed):u.reg_write(UC_X86_REG_AX,0xb000)
  elif (seg,off)==(90*8,0xe29):
   ibo=self.read(arg(0));u.reg_write(UC_X86_REG_AX,self.actors.get(ibo,0xffff))
  elif (seg,off)==(43*8,0x65):
   self.bound.append(arg(0));u.reg_write(UC_X86_REG_AX,self.rng_value%arg(0))
  else:raise AssertionError(f'Unexpected native stub {seg:x}:{off:x}')
  u.reg_write(UC_X86_REG_IP,u.reg_read(UC_X86_REG_IP)+5)
 def run(self,name,stack=None,regs=None):
  u=self.u;sp=0xc000
  if stack is None:stack=[0xff00]
  u.mem_write(DS*16+sp,struct.pack('<'+'H'*len(stack),*stack));u.reg_write(UC_X86_REG_SP,sp)
  if regs:
   for r,v in regs.items():u.reg_write(r,v)
  u.reg_write(UC_X86_REG_IP,syms[name]);u.emu_start(CS*16+syms[name],CS*16+0xff01,count=10000)
  assert u.reg_read(UC_X86_REG_IP)==0xff01,(name,hex(u.reg_read(UC_X86_REG_IP)))
  assert u.reg_read(UC_X86_REG_FS)==0x1111 and u.reg_read(UC_X86_REG_GS)==0x2222
  return u.reg_read(UC_X86_REG_AX)
 def damage(self,attacker,target,amount):
  self.word(0x100,attacker);self.word(0x102,target);self.word(0xd006,0x100);self.word(0xd008,0x102);self.word(0xd00a,amount)
  self.run('damage',[0x3456,0xff00,CS],{UC_X86_REG_BP:0xd000})
  assert self.u.reg_read(UC_X86_REG_DI)==0x100 and self.u.reg_read(UC_X86_REG_SI)==0x102
  assert self.u.reg_read(UC_X86_REG_SP)==0xc006
  return self.read(0xd00a,1)
results=[]
for setting,factor in enumerate([25,75,100,125,200]):
 m=Machine(setting)
 outgoing=m.damage(0x114,0x110,40);received=m.damage(0x110,0x114,40)
 assert outgoing==min(127,(40*factor+50)//100)
 assert received==40*100//factor or received==127 # signed native clamp
 for a,t in [(0x110,0x112),(0x114,0x116),(0,0x110)]:assert m.damage(a,t,40)==40
 assert m.damage(0x114,0x110,0)==0
 assert m.damage(0x114,0x110,255)==255 # native negative damage unchanged
 results.append({'setting':setting,'enemy_outgoing_40':outgoing,'party_hit_40':received})
for setting in [3,4]:
 m=Machine(setting)
 hits=[m.damage(0x110,0x114,1) for i in range(20)]
 assert sum(hits)==20*100//[25,75,100,125,200][setting],hits
 results.append({'setting':setting,'one_point_hits':hits})
 m.actors[0x114]=65535
 assert m.damage(0x110,0x114,1)==1
for restored in [False,True]:
 for setting in range(5):
  for bound in [5,45,60,100,375,600]:
   m=Machine(setting,restored)
   ax=m.run('rng',[0x3456,0xff00,CS,bound],{UC_X86_REG_BP:0xbeef})
   expected=bound
   if restored:expected={1:bound*2,3:bound*2//3,4:bound*2//5}.get(setting,bound)
   if setting==0:assert ax==32767 and m.bound==[]
   else:assert m.bound==[expected]
   assert m.u.reg_read(UC_X86_REG_BP)==0xbeef and m.u.reg_read(UC_X86_REG_SP)==0xc006
for active in [False,True]:
 m=Machine();m.word(0x1068,0x114 if active else 0);m.u.mem_write(ES*16+0x510,b'\x07');m.u.mem_write(ES*16+0x50e,b'\x12')
 ax=m.run('mana_read',[0x500,0xff00,CS]);assert ax==(18 if active else 7)
 m.run('mana_write',[0x500,0xff00,CS,3]);assert m.u.reg_read(UC_X86_REG_SP)==0xc008
 assert bytes(m.u.mem_read(ES*16+0x50e,1))==bytes([3 if active else 18])
 assert bytes(m.u.mem_read(ES*16+0x510,1))==bytes([7 if active else 3])
for npc,expected in [(0,0),(1,0),(3,0),(4,0),(5,1),(7,0),(8,0),(9,0),(10,0),(153,1),(154,0)]:
 m=Machine();assert m.run('eligible',regs={UC_X86_REG_AX:npc})==expected
m=Machine();m.u.mem_write(ES*16+0x508,b'\x18');m.run('mana_init',regs={UC_X86_REG_BX:0x500});assert bytes(m.u.mem_read(ES*16+0x50d,4))==b'\x98\x18\x00\x00'
m.u.mem_write(ES*16+0x50e,b'\x04');m.run('mana_init',regs={UC_X86_REG_BX:0x500});assert bytes(m.u.mem_read(ES*16+0x50e,1))==b'\x04'
for shape in [761,842]:
 m=Machine();m.word(0x4b36,ES);m.word(0x100,0x500)
 m.u.mem_write(ES*16+0x500,struct.pack('<4H',0,0,shape,0x600))
 m.u.mem_write(ES*16+0x600,b'\xaa'*6+struct.pack('<H',0x608));m.u.mem_write(ES*16+0x608,b'\xbb'*8)
 m.run('new_book',[0x1234,0xff00,CS],{UC_X86_REG_SI:0x100})
 assert bytes(m.u.mem_read(ES*16+0x600,6))==(b'\xff\0\0\0\0\xaa' if shape==761 else b'\xaa'*6)
 assert bytes(m.u.mem_read(ES*16+0x608,8))==(b'\0'*8 if shape==761 else b'\xbb'*8)
print(json.dumps({'status':'PASS','machine_code_tests':results,'symbols':syms},indent=2))
