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

# 找 .rdata 里 Player_Action 相关字符串的 RVA
import re
rdata_va, rdata_data = None, None
for s in pe.sections:
    if s.Name.startswith(b'.rdata'):
        rdata_va = s.VirtualAddress
        rdata_data = s.get_data()
        break

targets = [b'Gun_Windup', b'Lateral', b'speed', b'ejector', b'Player_Action', b'Vehicle_Filter']
str_rvas = {}
for t in targets:
    pos = 0
    while True:
        idx = rdata_data.find(t, pos)
        if idx < 0: break
        rva = rdata_va + idx
        if rva not in str_rvas:
            str_rvas[rva] = []
        str_rvas[rva].append(t.decode())
        pos = idx + 1

print("=== Player_Action 相关字符串 RVA ===")
for rva, names in sorted(str_rvas.items()):
    print(f"  RVA=0x{rva:X}: {', '.join(names)}")

# 现在搜 .text 里对这些字符串地址的 rip-relative 引用
# 在 .text 里搜索对每个 target 字符串 VA 的 lea/mov 引用
print()
print("=== .text 里引用这些字符串的位置 ===")

for str_rva, names in str_rvas.items():
    target_va = base + str_rva
    refs = []
    for i in range(len(text_data) - 8):
        # 尝试解码 lea rax, [rip+disp32] / mov rax, [rip+disp32]
        # 简化: 搜所有 7 或 8 字节包含 rel32 指向 target_va 的
        for ilen in [7, 8]:
            if i + ilen >= len(text_data): continue
            if ilen == 7 and text_data[i] in (0x48, 0x4C) and text_data[i+1] in (0x8D, 0x8B):
                rel = struct.unpack_from('<i', text_data, i+3)[0]
                rip_end = base + text_va + i + ilen
                ptr_val = (rip_end + rel) & 0xFFFFFFFFFFFFFFFF
                if ptr_val == target_va:
                    refs.append((text_va + i, ilen, 'lea/mov'))
            if ilen == 7 and text_data[i] == 0x48 and text_data[i+1] in (0x8D, 0x8B):
                # 标准 48 8D xx xx xx xx xx
                rel = struct.unpack_from('<i', text_data, i+3)[0]
                rip_end = base + text_va + i + ilen
                ptr_val = (rip_end + rel) & 0xFFFFFFFFFFFFFFFF
                if ptr_val == target_va:
                    refs.append((text_va + i, ilen, 'lea/mov'))
    
    if refs:
        print(f"\n  [{', '.join(names)}] RVA=0x{str_rva:X}:")
        for rva, ilen, kind in refs[:20]:
            print(f"    xref RVA=0x{rva:05X}")

# 换方法: 搜 "src\\Gun.cpp" (Player_Action 调试字符串) 的 xref
print("\n=== 换方法: 直接搜 Mech 里 Player_Action 指针的创建点 ===")
# 我们知道: 只有玩家 Mech 有 Player_Action, 只有玩家 Mech +0x0230 是 heap ptr
# 那是谁给 +0x0230 赋值的?
# 搜谁把某个 heap 对象地址写到 rcx+0x230 或 rdx+0x230 等 (Mech* + 0x230)

# 实际上我们可以搜 .text 里所有 0x230 作为 modrm disp32 或 imm32
# 但太难编码了

# 更好的办法: 搜 "Gun_Windup" 字符串本身 (ASCII), 然后搜它周围的代码
# 如果有 printf("Gun_Windup: %.9f", ...), 那参数就是 Player_Action 里的字段

# 找到 "Gun_Windup" 字符串
gw_off = rdata_data.find(b'Gun_Windup')
if gw_off >= 0:
    gw_rva = rdata_va + gw_off
    gw_va = base + gw_rva
    print(f"\nGun_Windup 字符串 VA = 0x{gw_va:X}")
    # 搜 .text 里谁 load 了这个地址 (lea/load)
    refs = []
    for i in range(len(text_data) - 8):
        for ilen in [7, 8]:
            if i + ilen >= len(text_data): continue
            # 检查是不是 rip-relative
            if text_data[i] in (0x48, 0x4C) and text_data[i+1] in (0x8D, 0x8B):
                rel = struct.unpack_from('<i', text_data, i+3)[0]
                rip_end = base + text_va + i + ilen
                ptr_val = (rip_end + rel) & 0xFFFFFFFFFFFFFFFF
                if ptr_val == gw_va:
                    refs.append(text_va + i)
    print(f"  .text 引用数 = {len(refs)}")
    for rva in refs[:10]:
        print(f"    0x{rva:05X}")
