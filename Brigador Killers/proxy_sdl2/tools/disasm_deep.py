import pefile
from capstone import *

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

def dump(name, rva, ln):
    off = rva2off(rva)
    if off is None:
        print(f'{name}: RVA 0x{rva:X} not mapped'); return
    code = raw[off:off+ln]
    print(f'\n===== {name}  RVA 0x{rva:X} =====')
    n = 0
    for ins in md.disasm(code, IB + rva):
        bs = ' '.join(f'{b:02X}' for b in ins.bytes)
        print(f'  0x{ins.address:X}  {bs:<24s} {ins.mnemonic:<7s} {ins.op_str}')
        n += 1
        if n > 90: 
            print('  ...')
            break
        if ins.mnemonic == 'int3':
            break

# DisableAI -> actual implementation
dump('sub_1400DE910 (DisableAI body)', 0x0DE910, 0x120)
# userdata -> Mech* resolver
dump('sub_140024C80 (udata->mech)', 0x024C80, 0x100)
# GetPlayer's player-object getter
dump('sub_140178F30 (get player obj)', 0x178F30, 0xC0)
