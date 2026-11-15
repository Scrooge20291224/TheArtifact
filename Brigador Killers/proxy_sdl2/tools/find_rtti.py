import pefile, re

EXE = r'C:\Program Files (x86)\Steam\steamapps\common\Brigador Killers\brigadorkillers.exe'
pe = pefile.PE(EXE)
IB = pe.OPTIONAL_HEADER.ImageBase
raw = pe.__data__

def off2rva(o):
    for s in pe.sections:
        if s.PointerToRawData <= o < s.PointerToRawData + s.SizeOfRawData:
            return s.VirtualAddress + (o - s.PointerToRawData)
    return None

# MSVC RTTI mangled names look like ".?AVPlayer_Action@@"
pat = re.compile(rb'\.\?AV[A-Za-z0-9_@?$]{2,80}@@')
found = []
for m in pat.finditer(raw):
    name = m.group().decode('ascii', 'replace')
    if any(k in name for k in ('Action', 'Player', 'Gun', 'Mech', 'Mover', 'Drive', 'Control', 'Input', 'Vehicle')):
        found.append((off2rva(m.start()), name))

print(f'=== RTTI names matching (count={len(found)}) ===')
for rva, name in found:
    print(f'  RVA 0x{rva:08X}  {name}')

print()
print('=== ALL .?AV names with "Action" ===')
for m in pat.finditer(raw):
    name = m.group().decode('ascii', 'replace')
    if 'Action' in name:
        print(f'  RVA 0x{off2rva(m.start()):08X}  {name}')

# also look for plain "Gun" class RTTI
print()
print('=== .?AV names containing Gun ===')
for m in pat.finditer(raw):
    name = m.group().decode('ascii', 'replace')
    if 'Gun' in name:
        print(f'  RVA 0x{off2rva(m.start()):08X}  {name}')
