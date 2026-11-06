import sys,struct,re; sys.path.insert(0,'VDMod/re'); from pe import *
def d(lo,hi):
  o=va2off(lo)
  for ins in MD.disasm(D[o:o+(hi-lo)],lo):
    s=ins.op_str; m=re.search(r'\[(?:\w+\*4 \+ )?0x([0-9a-f]{6,8})\]',s); c=''
    if m:
      a=int(m.group(1),16)
      if 0x8cd000<=a<0x948000: c='   ; %g'%struct.unpack_from('<f',D,va2off(a))[0]
    print(f'{ins.address:08x}  {ins.mnemonic:7s} {s}{c}')
    if ins.mnemonic=='ret' and len(sys.argv)<4: break
d(int(sys.argv[1],16),int(sys.argv[2],16))
