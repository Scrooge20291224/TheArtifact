import pefile, struct

pe = pefile.PE(r'C:\Program Files (x86)\Steam\steamapps\common\Brigador Killers\brigadorkillers.exe', fast_load=False)
base = pe.OPTIONAL_HEADER.ImageBase

# 搜 Mech 方法表里谁处理 Player_Action
# 我们知道 DisableAI 在 0x1A93D0, GetPlayer 在 0x1A86A0
# 搜这些函数附近的 call/jmp, 看有没有调 Player_Action 相关

# 更好的方法: 搜 "Gun_Windup" 等字符串的 xref, 然后往上追谁 call 了那个函数
# 但我们已经知道字符串没 xref (debug code 被优化掉了)

# 换方法: 搜 Mech 方法表里有没有看起来像 Player_Action 的
# 方法表在 0x3D2550 ~ 0x3D2A80, 每 16B = {char* name_VA, uint64_t impl_RVA}

text_va = None
for s in pe.sections:
    if s.Name.startswith(b'.text'):
        text_va = s.VirtualAddress
        break

# 读 .rdata 找方法表名字字符串
rdata_va, rdata_data = None, None
for s in pe.sections:
    if s.Name.startswith(b'.rdata'):
        rdata_va = s.VirtualAddress
        rdata_data = s.get_data()
        break

# 扫方法表
print("=== Mech 方法表 ===")
methods = []
for i in range(0x3D2550 - pe.OPTIONAL_HEADER.ImageBase, 0x3D2A80 - pe.OPTIONAL_HEADER.ImageBase, 16):
    try:
        chunk = pe.get_memory_mapped_image()[i:i+16]
        name_va, impl_rva = struct.unpack_from('<QQ', chunk)
        if impl_rva == 0 and name_va == 0:
            continue
        name_rva = name_va - base
        # 读名字
        name = ""
        if 0 < name_rva < len(rdata_data):
            j = name_rva
            while j < len(rdata_data) and rdata_data[j] != 0:
                name += chr(rdata_data[j])
                j += 1
        methods.append((name, impl_rva))
        if name:
            print(f"  {name:30s} RVA=0x{impl_rva:06X}")
    except:
        pass

# 现在, 关键问题: Player_Action 是 Mech 的一部分吗?
# 之前 hex dump 显示 Player_Action 数据在 Mech +0x0400, +0x0702 等
# 但引擎怎么"处理"这些数据? 谁读它们?
#
# 思路: 搜谁写了 Mech +0x0400 附近的 float
# 或者搜谁读了 Mech +0x0702
# 但这需要 disasm 大量代码...

# 更简单的方法: 已知 type=6 时引擎会走玩家专属分支 (v7 crash 证明了)
# 那这个专属分支是什么? 是谁看 type 然后分叉的?
#
# 搜 .text 里对 Mech+0x0000 (type 字段) 的 mov/load
# 然后看后续 call

print("\n=== 搜 Mech type 字段的访问点 ===")
# type 在 Mech +0x0000, 所以搜对 rcx/r15 等 (Mech*) 的 [reg+0] 访问
# 然后看 cmp eax, 6 或 cmp eax, 0x6 之类

# 暴力: 在 .text 里搜 "83 F8 06" (cmp eax, 6) 或 "83 F8 00" (cmp eax, 0)
# 因为 type 是 dword, 所以大概率是: mov eax, [rcx]; cmp eax, 6
# 即: 8B 01 / 8B 41 00 (mov eax, [rcx] / mov eax, [rcx+0])
# 然后 83 F8 06 (cmp eax, 6)

import capstone
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True

text_section = None
for s in pe.sections:
    if s.Name.startswith(b'.text'):
        text_section = s
        break

text_data = text_section.get_data()
text_base = base + text_section.VirtualAddress

# 搜: mov eax, [reg+0] ; cmp eax, 6
# 这是最典型的 "if (mech->type == 6)" 模式
print("\n--- 搜 'if (mech->type == 6)' 模式 ---")
patterns = [
    # mov eax, [rcx+0]  (8B 01)
    b'\x8B\x01',
    # mov eax, [rdx+0]  (8B 02)  
    b'\x8B\x02',
    # mov eax, [rsi+0]  (8B 06)
    b'\x8B\x06',
    # mov eax, [rdi+0]  (8B 07)
    b'\x8B\x07',
    # mov eax, [r15+0]  (41 8B 07)
    b'\x41\x8B\x07',
    # mov eax, [r14+0]  (41 8B 06)
    b'\x41\x8B\x06',
]

import re
cmp_6 = b'\x83\xF8\x06'  # cmp eax, 6 (3 bytes)

for pat in patterns:
    idx = 0
    while True:
        idx = text_data.find(pat, idx)
        if idx < 0: break
        # 检查后面 10 字节内有没有 cmp eax, 6
        next_bytes = text_data[idx+len(pat):idx+len(pat)+15]
        cmp_pos = next_bytes.find(cmp_6)
        if cmp_pos >= 0:
            rva = text_section.VirtualAddress + idx
            print(f"  RVA=0x{rva:05X}: mov eax, [reg+0] + cmp eax, 6 (pattern {pat.hex()})")
            # 反汇编附近代码
            code = text_data[idx:idx+40]
            for insn in md.disasm(code, text_base + idx):
                print(f"    {insn.mnemonic} {insn.op_str}")
                if insn.mnemonic == 'cmp':
                    break
        idx += 1
