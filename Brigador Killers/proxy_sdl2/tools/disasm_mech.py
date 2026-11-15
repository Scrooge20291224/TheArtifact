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

FUNCS = {
    'GetPlayer':     (0x1A86A0, 0x120),
    'DisableAI':     (0x1A93D0, 0x40),
    'GetPosition':   (0x1A8FE0, 0xC0),
    'SetPosition':   (0x1A90A0, 0x70),
    'GetOrient':     (0x1A9410, 0x80),
    'Look':          (0x1A9490, 0x1B0),
    'MoveTo':        (0x1A9640, 0xB0),
    'GetAIState':    (0x1AA1C0, 0x80),
    'Halt':          (0x1AA690, 0x50),
    'SetHealth':     (0x1A92A0, 0xC0),
}

for name, (rva, ln) in FUNCS.items():
    off = rva2off(rva)
    code = raw[off:off+ln]
    print(f'\n===== {name} @ RVA 0x{rva:X} =====')
    print(f'     VA = 0x{IB+rva:X}')
    for ins in md.disasm(code, IB + rva):
        bytes_str = ' '.join(f'{b:02X}' for b in ins.bytes)
        print(f'  0x{ins.address:X}  {bytes_str:<28s} {ins.mnemonic:<8s} {ins.op_str}')
