import pefile, struct, sys
from capstone import *

EXE = r'C:\Program Files (x86)\Steam\steamapps\common\Brigador Killers\brigadorkillers.exe'
pe = pefile.PE(EXE)
IB = pe.OPTIONAL_HEADER.ImageBase
raw = pe.__data__

def off2rva(o):
    for s in pe.sections:
        if s.PointerToRawData <= o < s.PointerToRawData + s.SizeOfRawData:
            return s.VirtualAddress + (o - s.PointerToRawData)
    return None

def rva2off(rva):
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + s.Misc_VirtualSize:
            return s.PointerToRawData + (rva - s.VirtualAddress)
    return None

TARGETS = {
    'lateral_fmt': 0x3ACB68,
    'Player_Action': 0x3ACBA8,
    'Vehicle_Filter': 0x3ACBB8,
    'Gun_Windup': 0x3ACBD8,
    'ejector': 0x3ACBE8,
}

text = next(s for s in pe.sections if s.Name.rstrip(b'\x00') == b'.text')
T0 = text.PointerToRawData
T1 = text.PointerToRawData + text.Misc_VirtualSize
TVA = text.VirtualAddress

# generic rip-relative scanner
hits = {k: [] for k in TARGETS}
for i in range(T0, min(T1, len(raw)) - 7):
    b0, b1, b2 = raw[i], raw[i+1], raw[i+2]
    # REX prefix 0x40-0x4F (optional), opcode 8D (lea) or 8B (mov) or 89 (mov store) or 3B/39 (cmp)
    if not (0x40 <= b0 <= 0x4F):
        continue
    if b1 not in (0x8D, 0x8B, 0x89, 0x3B, 0x39, 0x8A, 0x88, 0xC7):
        continue
    if (b2 & 0xC7) != 0x05:
        continue
    # 89 and 39/3B have modrm byte AFTER opcode, so b2 is modrm — ok
    # but for opcodes with imm, disp position differs; handle only 8D/8B/3B/39 here
    disp_off = i + 3
    disp = struct.unpack_from('<i', raw, disp_off)[0]
    ins_rva = TVA + (i - T0)
    end = ins_rva + 7
    tgt = (end + disp) & 0xFFFFFFFFFFFFFFFF
    for k, trva in TARGETS.items():
        if tgt == IB + trva:
            hits[k].append(ins_rva)

for k, v in hits.items():
    print(f'{k:16s} refs={len(v)}  RVA=0x{TARGETS[k]:X}')
    for h in v[:12]:
        print(f'    @0x{h:X}')

# disassemble around first hit of lateral_fmt
if hits['lateral_fmt']:
    h = hits['lateral_fmt'][0]
    start = max(0, h - 0x60)
    off = rva2off(start)
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    print(f'\n=== context around lateral_fmt ref @0x{h:X} ===')
    print(f'    (function likely starts before 0x{h-0x60:X})')
    for ins in md.disasm(raw[off:off+0x180], IB + start):
        bs = ' '.join(f'{b:02X}' for b in ins.bytes)
        print(f'  0x{ins.address:X}  {bs:<26s} {ins.mnemonic:<8s} {ins.op_str}')
