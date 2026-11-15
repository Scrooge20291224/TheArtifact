import pefile, struct

pe = pefile.PE(r'C:\Program Files (x86)\Steam\steamapps\common\Brigador Killers\brigadorkillers.exe', fast_load=False)
base = pe.OPTIONAL_HEADER.ImageBase
text_va, text_data = None, None
for s in pe.sections:
    if s.Name.startswith(b'.text'):
        text_va = s.VirtualAddress
        text_data = s.get_data()
        break

target_va = base + 0x318A10  # lua_pushnumber

refs = []
for i in range(len(text_data) - 5):
    if text_data[i] == 0xE8:
        rel = struct.unpack_from('<i', text_data, i+1)[0]
        call_target_va = (base + text_va + i + 5 + rel) & 0xFFFFFFFFFFFFFFFF
        if call_target_va == target_va:
            refs.append(text_va + i)

print(f'Found {len(refs)} callers of lua_pushnumber (0x318A10):')
for rva in refs[:10]:
    print(f'  caller RVA = 0x{rva:X}')
    # 搜索 caller 前面 30 字节内有没有其他 call
    start = max(0, rva - text_va - 30)
    end = min(len(text_data), rva - text_va)
    for j in range(start, end - 4):
        if text_data[j] == 0xE8:
            rel2 = struct.unpack_from('<i', text_data, j+1)[0]
            ct2 = (base + text_va + j + 5 + rel2) & 0xFFFFFFFFFFFFFFFF
            print(f'    nearby call RVA=0x{text_va+j:X} -> 0x{ct2 - base:X}')
