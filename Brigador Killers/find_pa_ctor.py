import pefile, struct
from capstone import *
from capstone.x86 import X86_REG_RIP

pe = pefile.PE(r'C:\Program Files (x86)\Steam\steamapps\common\Brigador Killers\brigadorkillers.exe', fast_load=False)
base = pe.OPTIONAL_HEADER.ImageBase
text_va, text_data = None, None
for s in pe.sections:
    if s.Name.startswith(b'.text'):
        text_va = s.VirtualAddress
        text_data = s.get_data()
        break

md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True

# 关键问题: Mech +0x0400 附近到底是什么?
# 如果那是 Player_Action 指针, 应该有 xref 访问它

# 搜 .text 里对 Mech 结构 +0x0400 的访问
# 模式: [reg + 0x40] 或 [reg + 0x400] 或 [reg + 0x1C468]...
# 重点看谁访问了 0x1C468 (刚才找到的玩家 Mech* 偏移)

print('========== 谁访问了 state->+0x1C468 (玩家 Mech*) ==========')
# 这个偏移太大，不太可能直接硬编码在代码里（MSVC 会拆）
# 让我们看谁访问了 +0x1C4xx 范围
import re
# 扫 .text 里有没有 68 C4 01 00 00 00 00 00 (mov rax, [reg+0x1C468] 类似)
# 实际上 x86 modrm 编码太复杂，换方法：搜谁调用了 0x178F30 (get_player_mech_from_state)

target_fn_va = base + 0x178F30
target_low32 = target_fn_va & 0xFFFFFFFF
refs = []
for i in range(len(text_data) - 5):
    if text_data[i] == 0xE8:  # call rel32
        rel = struct.unpack_from('<i', text_data, i+1)[0]
        call_target = (base + text_va + i + 5 + rel) & 0xFFFFFFFFFFFFFFFF
        if call_target == target_fn_va:
            refs.append(text_va + i)

print(f'callers of 0x178F30 (get_player_mech): {len(refs)}')
for rva in refs:
    print(f'  caller RVA = 0x{rva:05X}')

print()

# 另一个思路: 我们知道 Player_Action 有 RTTI 名 LegPlayerControlled
# 搜谁在构造函数里 new 了它
# C++ new 会先调 operator new，然后调构造函数
# 构造函数里第一个操作通常是把 RTTI 指针写到 +0 (虚表指针)

# LegPlayerControlled RTTI 在 .data 里 RVA=0x49B4A4 -> 这是 vftable 指针目标
# 搜谁把 0x49B4A4 或包含它的地址写到某个对象开头

# 让我直接看 .data 里 0x49B4A4 附近是什么
# pefile 读 section
for s in pe.sections:
    if s.Name.startswith(b'.data'):
        sva = s.VirtualAddress
        sdata = s.get_data()
        idx = 0x49B4A4 - sva
        if 0 <= idx < len(sdata):
            print(f'.data RVA 0x49B4A4 (LegPlayerControlled RTTI 附近):')
            for i in range(-16, 32, 8):
                off = idx + i
                if 0 <= off < len(sdata):
                    q = struct.unpack_from('<Q', sdata, off)[0]
                    print(f'  +{i:+d}: 0x{q:016X}')
        break

print()
print('========== 搜谁用了 vftable/RTTI 相关的 0x49B4xx 地址 ==========')
# 构造函数里会 lea/load RTTI/vftable 地址写到对象 +0
target_va_range = (base + 0x49B400, base + 0x49B800)
for i in range(len(text_data) - 7):
    # 搜所有 rip-relative lea/mov
    if text_data[i] in (0x48, 0x4C) and text_data[i+1] in (0x8D, 0x8B):
        rel = struct.unpack_from('<i', text_data, i+3)[0]
        for ilen in [7, 8]:
            if i + ilen >= len(text_data): continue
            rip_end = base + text_va + i + ilen
            ptr_val = (rip_end + rel) & 0xFFFFFFFFFFFFFFFF
            if target_va_range[0] <= ptr_val <= target_va_range[1]:
                print(f'  0x{text_va+i:05X}: 引用 0x{ptr_val - base:05X}')
