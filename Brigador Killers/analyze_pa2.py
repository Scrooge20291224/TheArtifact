import pefile, struct
from capstone import *

pe = pefile.PE(r'C:\Program Files (x86)\Steam\steamapps\common\Brigador Killers\brigadorkillers.exe', fast_load=False)
base = pe.OPTIONAL_HEADER.ImageBase
text_va, text_data = None, None
for s in pe.sections:
    if s.Name.startswith(b'.text'):
        text_va = s.VirtualAddress
        text_data = s.get_data()
        break

# 搜 RTTI: LegPlayerControlled / PlayerControlled
# RTTI 字符串在 .rdata 里，我们搜它的地址，然后找 xref
import re
all_sections = {}
for s in pe.sections:
    name = s.Name.decode(errors='replace').rstrip(chr(0))
    all_sections[name] = (s.VirtualAddress, s.get_data())

# 搜 RTTI 名字
target_names = [b'LegPlayerControlled', b'ChassisPlayerControlled', 
                b'Player_Action', b'PlayerControlled', b'LegVehicle']

for tname in target_names:
    for sname, (sva, sdata) in all_sections.items():
        pos = 0
        while True:
            idx = sdata.find(tname, pos)
            if idx < 0: break
            rva = sva + idx
            print(f'[{tname.decode()}] RVA=0x{rva:X} VA=0x{base+rva:X} (in {sname})')
            pos = idx + 1
print()

# 扫 Mech 里的 Player_Action 指针 —— 对比玩家和 fake 结构里的 qword 差异
# 从之前 diff dump 里找"玩家独有但 fake 为 0 的 qword"
# 那些就是 Player_Action 相关指针

# 重新看 diff dump 0x400 区域（玩家独有的）
# 之前玩家 dump: +0400 CB A8 68 42 54 EE 4F 42 48 E1 3A 3F 
# 这 12B 是纯 float，不像指针

# 但让我扫 fake +0x0400 ~ +0x0800 全是 0 的区域
# 玩家那里 +0x0400~+0x040C 是 float，但 +0x0410 之后也是 0...
# 直到 +0x04C0 有 dword 变化

# 关键: 玩家 Mech 的 +0x0400 区域不是指针
# 那 Player_Action 指针在哪?

# 让我找 exe 里 new Player_Action 的 xref
# C++ new 会调 operator new，然后构造函数
# 搜 "PlayerControlled" RTTI 的 xref

def find_xref_ptr(dll_base, text_base, text_bytes, target_rva):
    """找 .text 里引用 target_rva 地址的 rip-relative 访问"""
    target_va = dll_base + target_rva
    refs = []
    for i in range(len(text_bytes) - 7):
        # lea reg, [rip+disp32]
        if text_bytes[i] == 0x48 and text_bytes[i+1] in (0x8D, 0x8B):
            # 可能是 lea rax/rbx/rcx/rdx/rsi/rdi/rbp/r8~r15 or mov
            rel = struct.unpack_from('<i', text_bytes, i+3)[0]
            # rip 指令结束位置 = text_va + i + 7 (6字节 lea 或 7字节 mov)
            # 实际上 lea rax, [rip+disp32] = 48 8D xx xx xx xx xx (7 bytes)
            # 但也可能是 48 8D xx xx xx xx xx (8 bytes with REX+modrm+SIB)
            # 简化: 先假设是标准 7-byte lea
            for ilen in [7, 8]:
                if i + ilen >= len(text_bytes): continue
                rip_end = dll_base + text_base + i + ilen
                ptr_val = (rip_end + rel) & 0xFFFFFFFFFFFFFFFF
                if ptr_val == target_va:
                    refs.append((text_base + i, f'lea@{ilen}'))
        # mov reg, [rip+disp32] (load pointer)
        if text_bytes[i] == 0x48 and text_bytes[i+1] == 0x8B:
            for ilen in [7, 8]:
                if i + ilen >= len(text_bytes): continue
                rel = struct.unpack_from('<i', text_bytes, i+3)[0]
                rip_end = dll_base + text_base + i + ilen
                ptr_val = (rip_end + rel) & 0xFFFFFFFFFFFFFFFF
                if ptr_val == target_va:
                    refs.append((text_base + i, f'mov@{ilen}'))
    return refs

# 搜 .rdata 里所有 "PlayerControlled" 的 RTTI 相关地址
# RTTI 结构: _s_RTTI_Complete_ObjectLocator 有 pointer to type name
# 我们先搜包含 "LegPlayerControlled" 的字符串地址
for tname in [b'LegPlayerControlled']:
    for sname, (sva, sdata) in all_sections.items():
        idx = sdata.find(tname)
        if idx >= 0:
            name_rva = sva + idx
            print(f'搜索 [{tname.decode()}] RVA=0x{name_rva:X}')
            # 这个字符串在 RTTI 里被引用（pointer to member）
            # 搜 .text 里的 xref
            xrefs = find_xref_ptr(base, text_va, text_data, name_rva)
            for xrva, xtype in xrefs:
                print(f'  xref: 0x{xrva:X} ({xtype})')
print()

# 再搜 .text 里对 0xB56838 (我以为的全局指针) 的访问
# 验证它到底是什么
print("=== 扫 0xB56838 附近的全局引用 ===")
for tgt_rva in [0xB56838, 0xB38850, 0xDE910]:
    xrefs = find_xref_ptr(base, text_va, text_data, tgt_rva)
    print(f'RVA 0x{tgt_rva:X} ({len(xrefs)} xrefs):')
    for xrva, xtype in xrefs[:10]:
        print(f'  0x{xrva:X} {xtype}')
