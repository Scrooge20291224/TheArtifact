import pefile, struct

EXE = r'C:\Program Files (x86)\Steam\steamapps\common\Brigador Killers\brigadorkillers.exe'
pe = pefile.PE(EXE)
raw = pe.__data__

def rva2off(rva):
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + s.Misc_VirtualSize:
            return s.PointerToRawData + (rva - s.VirtualAddress)
    return None

def off2rva(off):
    for s in pe.sections:
        if s.PointerToRawData <= off < s.PointerToRawData + s.SizeOfRawData:
            return s.VirtualAddress + (off - s.PointerToRawData)
    return None

def is_str_ptr(rva):
    o = rva2off(rva)
    if o is None or o >= len(raw): return None
    end = o
    while end < len(raw) and end - o < 80 and raw[end] != 0:
        if not (32 <= raw[end] < 127): return None
        end += 1
    if end == o: return None
    return raw[o:end].decode('ascii', 'replace')

base = 0x3D2700
size = 0x600
o = rva2off(base)
blob = raw[o:o+size]

print(f'=== dump RVA 0x{base:X} .. 0x{base+size:X} ===')
for i in range(0, size, 16):
    line = blob[i:i+16]
    hexs = ' '.join(f'{b:02X}' for b in line)
    asc = ''.join(chr(b) if 32 <= b < 127 else '.' for b in line)
    print(f'{base+i:08X}  {hexs:<48s}  {asc}')

print()
print('=== 该区域内在 .data/.rdata 中看起来像指针的 8 字节值 ===')
for i in range(0, size - 8, 8):
    v = struct.unpack_from('<Q', blob, i)[0]
    if 0x3A0000 < v < 0x0D00000:  # plausible RVA/VA in loaded image
        s = is_str_ptr(v)
        if s:
            print(f'  +0x{i:04X} (RVA 0x{base+i:X}) -> 0x{v:X} "{s}"')
