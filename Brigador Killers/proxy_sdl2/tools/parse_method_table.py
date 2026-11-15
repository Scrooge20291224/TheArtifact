import pefile, struct

EXE = r'C:\Program Files (x86)\Steam\steamapps\common\Brigador Killers\brigadorkillers.exe'
pe = pefile.PE(EXE)
IB = pe.OPTIONAL_HEADER.ImageBase
raw = pe.__data__
print(f'ImageBase = 0x{IB:X}')

text = next(s for s in pe.sections if s.Name.rstrip(b'\x00') == b'.text')
TEXT_LO = IB + text.VirtualAddress
TEXT_HI = TEXT_LO + text.Misc_VirtualSize
print(f'.text VA 0x{TEXT_LO:X} .. 0x{TEXT_HI:X}')

def off2rva(o):
    for s in pe.sections:
        if s.PointerToRawData <= o < s.PointerToRawData + s.SizeOfRawData:
            return s.VirtualAddress + (o - s.PointerToRawData)
    return None

def va2off(va):
    rva = va - IB
    if rva < 0: return None
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + s.Misc_VirtualSize:
            return s.PointerToRawData + (rva - s.VirtualAddress)
    return None

def read_cstr(va, maxlen=64):
    o = va2off(va)
    if o is None or o >= len(raw): return None
    end = o
    while end < len(raw) and end - o < maxlen and raw[end] != 0:
        if not (32 <= raw[end] < 127): return None
        end += 1
    if end == o: return None
    return raw[o:end].decode('ascii')

# scan whole image for {name_ptr, fn_ptr} pairs
pairs = []
for s in pe.sections:
    lo = s.PointerToRawData
    hi = lo + s.SizeOfRawData
    for o in range(lo, hi - 16, 8):
        nva, fva = struct.unpack_from('<QQ', raw, o)
        if not (TEXT_LO <= fva < TEXT_HI):
            continue
        if not (IB <= nva < IB + 0x1000000):
            continue
        name = read_cstr(nva, 40)
        if not name or len(name) < 3:
            continue
        # name must look like an identifier
        if not all(c.isalnum() or c == '_' for c in name):
            continue
        pairs.append((off2rva(o), name, fva - IB, fva))

# de-dup consecutive identical name+fn (table has no padding dupes, but keep unique)
seen = set()
out = []
for rva, name, frva, fva in pairs:
    k = (name, frva)
    if k in seen: continue
    seen.add(k)
    out.append((rva, name, frva, fva))

print(f'\n=== {len(out)} 条 {{name, func}} 候选（RVA / 名字 / 实现RVA） ===')
for rva, name, frva, fva in out:
    print(f'  0x{rva:08X}  {name:24s}  impl RVA=0x{frva:08X}')

# highlight the ones we care about
want = {'DisableAI','GetPlayer','GetPlayerHovered','MoveTo','SetPosition','Look','Halt','Speak','SetHealth','GetPosition','SetOrient','GetOrient','GetAIState','QueueAIState','SetOrder','Bail','EjectSeat','EjectAll','Gib','SetLocked','SetSeatLocked'}
print('\n=== 关注项 ===')
for rva, name, frva, fva in out:
    if name in want:
        print(f'  {name:20s} impl RVA 0x{frva:08X}')
