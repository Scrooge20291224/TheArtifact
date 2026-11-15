import pefile, struct

pe = pefile.PE(r'C:\Program Files (x86)\Steam\steamapps\common\Brigador Killers\brigadorkillers.exe', fast_load=False)
base = pe.OPTIONAL_HEADER.ImageBase
img = pe.get_memory_mapped_image()

# section 范围
secs = []
for s in pe.sections:
    secs.append((s.Name.rstrip(b'\x00').decode(errors='replace'),
                 s.VirtualAddress, s.VirtualAddress + s.Misc_VirtualSize,
                 s.get_data()))

def sec_of(rva):
    for name, va, end, data in secs:
        if va <= rva < end:
            return name, data, va
    return None, None, None

def read_cstr(rva, maxlen=128):
    name, data, va = sec_of(rva)
    if name is None: return None
    off = rva - va
    if off < 0 or off >= len(data): return None
    end = data.find(b'\x00', off)
    if end < 0 or end - off > maxlen: return None
    raw = data[off:end]
    if len(raw) < 2: return None
    try:
        s = raw.decode('ascii')
    except UnicodeDecodeError:
        return None
    # 必须是可打印标识符风格
    if not all(32 <= ord(c) < 127 for c in s):
        return None
    if not any(c.isalpha() for c in s):
        return None
    return s

# 扫 .rdata 里所有 16 字节对齐的 {ptr->字符串, ptr->.text} 对
rdata_name, rdata_data, rdata_va = None, None, None
text_name, text_data, text_va = None, None, None
for name, va, end, data in secs:
    if name.startswith('.rdata'):
        rdata_name, rdata_data, rdata_va = name, data, va
    if name.startswith('.text'):
        text_name, text_data, text_va = name, data, va
    if name == '.data':
        data_name, data_data, data_va = name, data, va

text_lo = text_va
text_hi = text_va + len(text_data)

found = {}   # name -> impl rva
pairs = []

for off in range(0, len(rdata_data) - 16, 8):
    try:
        v1, v2 = struct.unpack_from('<QQ', rdata_data, off)
    except struct.error:
        break
    # v1 指向 .rdata 内字符串
    if not (rdata_va <= v1 - base < rdata_va + len(rdata_data)):
        continue
    # v2 指向 .text
    if not (text_lo <= v2 - base < text_hi):
        continue
    name = read_cstr(v1 - base)
    if not name or len(name) < 2 or len(name) > 64:
        continue
    # 名字必须像方法名: 字母开头, 无空格, 无奇怪字符
    if not (name[0].isalpha() or name[0] == '_'):
        continue
    if any(c in name for c in ' \t/\\:;,"\'(){}[]<>'):
        continue
    impl = v2 - base
    pairs.append((rdata_va + off, name, impl))
    found.setdefault(name, impl)

print(f"扫描到 {len(pairs)} 条 {{name, impl}} 记录, 去重后 {len(found)} 个名字\n")

# 按名字关键词分类
kw = ['Gun', 'Fire', 'Shoot', 'Weapon', 'Speed', 'Veloc', 'Move', 'Thrust',
      'Impulse', 'Force', 'Lateral', 'Windup', 'Eject', 'Seat', 'Time',
      'AI', 'State', 'Input', 'Control', 'Player', 'Health', 'Damage']
print("=== 关键词命中 ===")
for k in kw:
    hits = sorted([n for n in found if k.lower() in n.lower()])
    if hits:
        print(f"\n[{k}] {len(hits)} 个:")
        for n in hits[:40]:
            print(f"   {n:34s} RVA=0x{found[n]:06X}")

print("\n=== 全部方法名 (排序, 前 400) ===")
for n in sorted(found)[:400]:
    print(f"  {n:36s} 0x{found[n]:06X}")
print(f"\n总计 {len(found)} 个唯一名字")
