import pefile, struct

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
    'lateral_fmt':    0x3ACB68,
    'Player_Action':  0x3ACBA8,
    'Vehicle_Filter': 0x3ACBB8,
    'Gun_Windup':     0x3ACBD8,
    'ejector':        0x3ACBE8,
    'src\\Gun.cpp':   0x3ACBC8,
}

for name, rva in TARGETS.items():
    absva = IB + rva
    needle = struct.pack('<Q', absva)
    locs = []
    start = 0
    while True:
        i = raw.find(needle, start)
        if i < 0: break
        locs.append(i)
        start = i + 1
    print(f'{name:16s} VA=0x{absva:X}  absolute-refs={len(locs)}')
    for o in locs[:8]:
        print(f'    file 0x{o:X}  rva 0x{off2rva(o):X}')
