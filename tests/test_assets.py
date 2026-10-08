#!/usr/bin/env python3
"""Verify preservation of native records, branch destinations and linker data."""
import argparse, struct, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'source'))
from asset_patcher import functions, decode, patch_usecode, link_dependencies, MERCHANTS, SHOP_ID

def parts(body):
    size=struct.unpack_from('<H',body)[0];at=2+size
    argc,locals_,count=struct.unpack_from('<3H',body,at)
    return body[2:at], (argc,locals_), struct.unpack_from('<'+'H'*count,body,at+6), body[at+6+2*count:]

def main():
    p=argparse.ArgumentParser();p.add_argument('--game-root',required=True);args=p.parse_args()
    root=Path(args.game_root)/'STATIC';original=(root/'USECODE').read_bytes()
    before=dict(functions(original));after=dict(functions(patch_usecode(original)))
    assert set(after)==set(before)|{SHOP_ID}
    for fid,body in before.items():
        if fid not in MERCHANTS:
            assert after[fid]==body
            continue
        data,header,ext,code=parts(body);ndata,nheader,next_,ncode=parts(after[fid])
        assert ndata==data+b'spellbook\0' and header==nheader and next_==ext+(SHOP_ID,)
        old=decode(code);new=decode(ncode);mapping={};cursor=0
        for pos,end,op,target in old:
            mapping[pos]=cursor
            if op==4:
                cursor+=7 # add the answer immediately before native CONVERSE
                native_pos=cursor;cursor+=end-pos
                cursor+=14 # inserted match, shop call and return to conversation
            else:
                native_pos=cursor;cursor+=end-pos
            assert ncode[native_pos]==op
            # All original operands except branch displacements remain exact.
            assert ncode[native_pos+1:native_pos+end-pos-(2 if target is not None else 0)]==code[pos+1:end-(2 if target is not None else 0)]
        mapping[len(code)]=cursor
        cursor=0
        for pos,end,op,target in old:
            native_pos=mapping[pos]+(7 if op==4 else 0)
            if target is not None:
                dest=native_pos+end-pos+struct.unpack_from('<h',ncode,native_pos+end-pos-2)[0]
                assert dest==mapping[target]
    rebuilt=link_dependencies(original)
    assert rebuilt==tuple((root/name).read_bytes() for name in ['LINKDEP1','LINKDEP2'])
    index,pointers=link_dependencies(patch_usecode(original));offsets={};position=0
    for fid,body in functions(patch_usecode(original)):
        offsets[position]=fid;position+=len(body)+4
    for fid in after:
        first,total=struct.unpack_from('<HH',index,fid*4)
        last=struct.unpack_from('<H',index,(fid+1)*4)[0]
        ids=[offsets[struct.unpack_from('<I',pointers,i*4)[0]]for i in range(first,last)]
        assert ids==sorted(set(ids)) and fid in ids and sum(len(after[i])for i in ids)==total
    print('PASS: six merchant records preserve every original operand and branch; all other records unchanged; pristine linker tables byte-identical; new dependency closures valid.')

if __name__=='__main__':main()
