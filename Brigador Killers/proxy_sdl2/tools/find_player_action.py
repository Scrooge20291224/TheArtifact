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

def va2off(va):
    return rva2off(va - IB)

def read_cstr(va, maxlen=48):
    o = va2off(va)
    if o is None or o >= len(raw): return None
    end = o
    while end < len(raw) and end - o < maxlen and raw[end] != 0:
        if not (32 <= raw[end] < 127): return None
        end += 1
    return raw[o:end].decode('ascii') if end > o else None

# 1. locate Player_Action and its field names
for t in [b'Player_Action', b'Gun_Windup', b'Lateral', b'ejector', b'Vehicle_Filter']:
    off = raw.find(t)
    print(f'"{t.decode()}" file_off=0x{off:X} rva=0x{off2rva(off):X} va=0x{IB+off2rva(off):X}')

# 2. dump area around Player_Action
off = raw.find(b'Player_Action')
rva = off2rva(off)
start = max(0, off - 0x400)
end = min(len(raw), off + 0x400)
blob = raw[start:end]
base_rva = off2rva(start)
print(f'\n=== dump RVA 0x{base_rva:X} .. 0x{base_rva+len(blob):X} ===')
for i in range(0, len(blob), 16):
    line = blob[i:i+16]
    hexs = ' '.join(f'{b:02X}' for b in line)
    asc = ''.join(chr(b) if 32 <= b < 127 else '.' for b in line)
    print(f'{base_rva+i:08X}  {hexs:<48s}  {asc}')

# 3. scan that region for {name_ptr, value} pairs where value looks like an offset/size
print('\n=== 该区域内 {name_ptr, small_int} 配对（疑似字段偏移表） ===')
for i in range(0, len(blob) - 16, 8):
    nva, val = struct.unpack_from('<QQ', blob, i)
    name = read_cstr(nva)
    if name and (val < 0x1000 or val < 0x100000):
        print(f'  RVA 0x{base_rva+i:08X}  name="{name}"  val=0x{val:X} ({val})')
