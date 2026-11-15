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

# 找所有 lea/mov 用 rip+disp32 的指令，把算出来的 VA 和 RVA 全打出来
# 特别是 GetPlayer 函数里的那一条
target_funcs = {
    'GetPlayer': (0x1A86A0, 0x1A8720),
    'DisableAI': (0x1A93D0, 0x1A9410),
    'ResolveMech': (0x024C80, 0x024D20),
}

for fname, (start_rva, end_rva) in target_funcs.items():
    print(f'\n========== {fname} (0x{start_rva:X}~0x{end_rva:X}) ==========')
    code = text_data[start_rva - text_va : end_rva - text_va]
    for insn in md.disasm(code, base + start_rva):
        rva = insn.address - base
        # 找有 rip-relative 引用的
        for op in insn.operands:
            if op.type == CS_OP_MEM and op.mem.base == X86_REG_RIP:
                rip_end = insn.address + insn.size  # rip = 指令结束地址
                target_va = rip_end + op.mem.disp
                target_rva = target_va - base
                print(f'  0x{rva:05X}: {insn.mnemonic} {insn.op_str}')
                print(f'    => rip_rel -> RVA=0x{target_rva:05X} VA=0x{target_va:016X}')
