import pefile, struct, sys

EXE = r'C:\Program Files (x86)\Steam\steamapps\common\Brigador Killers\brigadorkillers.exe'
pe = pefile.PE(EXE)
IB = pe.OPTIONAL_HEADER.ImageBase
raw = pe.__data__

def off2rva(off):
    for s in pe.sections:
        if s.PointerToRawData <= off < s.PointerToRawData + s.SizeOfRawData:
            return s.VirtualAddress + (off - s.PointerToRawData)
    return None

def rva2off(rva):
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + s.Misc_VirtualSize:
            return s.PointerToRawData + (rva - s.VirtualAddress)
    return None

print('=== sections ===')
for s in pe.sections:
    n = s.Name.rstrip(b'\x00').decode()
    print(f'  {n:10s} VA=0x{s.VirtualAddress:08X} VS=0x{s.Misc_VirtualSize:08X} RAW=0x{s.PointerToRawData:08X}')

# locate occurrences of the method-name strings
targets = [b'DisableAI', b'MoveTo', b'GetPlayer', b'SetPosition']
rva_of = {}
for t in targets:
    offs = []
    start = 0
    while True:
        i = raw.find(t, start)
        if i < 0: break
        offs.append(i)
        start = i + 1
    print(f'\n"{t.decode()}" occurrences: {len(offs)}')
    for o in offs[:6]:
        r = off2rva(o)
        print(f'   file_off=0x{o:X} rva=0x{r:X}' if r else f'   file_off=0x{o:X} (unmapped)')
    # prefer ones followed by a null byte (standalone C string)
    good = [o for o in offs if o + len(t) < len(raw) and raw[o + len(t)] == 0]
    if good:
        rva_of[t] = off2rva(good[0])
        print(f'   -> chosen RVA 0x{rva_of[t]:X} (null-terminated)')
    elif offs:
        rva_of[t] = off2rva(offs[0])
        print(f'   -> chosen RVA 0x{rva_of[t]:X} (first)')

# scan .text for RIP-relative LEA/MOV referencing those RVAs
text = next(s for s in pe.sections if s.Name.rstrip(b'\x00') == b'.text')
tstart = text.PointerToRawData
tend = text.PointerToRawData + text.Misc_VirtualSize
tva = text.VirtualAddress

print('\n=== scanning .text for references ===')
for t, rva in rva_of.items():
    hits = []
    for i in range(tstart, min(tend, len(raw)) - 7):
        # 48 8D 05/0D/15/1D/25/2D/35/3D  disp32   (lea r64, [rip+disp])
        if raw[i] == 0x48 and raw[i+1] == 0x8D and (raw[i+2] & 0xC7) == 0x05:
            disp = struct.unpack_from('<i', raw, i+3)[0]
            ins_rva = tva + (i - tstart)
            end = ins_rva + 7
            tgt = (end + disp) & 0xFFFFFFFFFFFFFFFF
            if tgt == rva:
                hits.append(ins_rva)
        # 48 8B 05/... mov r64, [rip+disp]
        elif raw[i] == 0x48 and raw[i+1] == 0x8B and (raw[i+2] & 0xC7) == 0x05:
            disp = struct.unpack_from('<i', raw, i+3)[0]
            ins_rva = tva + (i - tstart)
            end = ins_rva + 7
            tgt = (end + disp) & 0xFFFFFFFFFFFFFFFF
            if tgt == rva:
                hits.append(ins_rva)
    print(f'  {t.decode():12s} rva=0x{rva:X}  refs={len(hits)}')
    for h in hits[:10]:
        print(f'      ref @ 0x{h:X}')
