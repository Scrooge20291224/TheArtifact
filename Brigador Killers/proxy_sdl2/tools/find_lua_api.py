import pefile
from capstone import *
from collections import Counter

EXE = r'C:\Program Files (x86)\Steam\steamapps\common\Brigador Killers\brigadorkillers.exe'
pe = pefile.PE(EXE)
IB = pe.OPTIONAL_HEADER.ImageBase
raw = pe.__data__

def rva2off(rva):
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + s.Misc_VirtualSize:
            return s.PointerToRawData + (rva - s.VirtualAddress)
    return None

md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True

def dump(name, rva, ln, show_calls=True):
    off = rva2off(rva)
    code = raw[off:off+ln]
    print(f'\n===== {name}  RVA 0x{rva:X} =====')
    calls = []
    for ins in md.disasm(code, IB + rva):
        bs = ' '.join(f'{b:02X}' for b in ins.bytes)
        print(f'  0x{ins.address:X}  {bs:<22s} {ins.mnemonic:<7s} {ins.op_str}')
        if ins.mnemonic == 'call' and ins.op_str.startswith('0x'):
            calls.append(int(ins.op_str, 16) - IB)
    return calls

c1 = dump('GetPosition', 0x1A8FE0, 0xE0)
c2 = dump('Halt', 0x1AA690, 0x50)
c3 = dump('MoveTo', 0x1A9640, 0xB0)
c4 = dump('SetHealth', 0x1A92A0, 0xB0)

print('\n=== 被调用的内部函数（RVA 频次） ===')
cnt = Counter(c1 + c2 + c3 + c4)
for rva, n in cnt.most_common(30):
    print(f'  0x{rva:08X}  x{n}')
