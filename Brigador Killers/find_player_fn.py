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

# 反汇编 0x140178f30 (RVA 0x178F30) 以及它的上下游
for target in [0x178F30, 0x140178F30 - base]:
    pass

# 直接用 RVA
target_rva = 0x178F30
off = target_rva - text_va
print(f'========== 0x{target_rva:X} (GetPlayer 调用的函数) ==========')
code = text_data[off:off+512]
func_end = None
for insn in md.disasm(code, base + target_rva):
    rva = insn.address - base
    extra = ''
    for op in insn.operands:
        if op.type == CS_OP_MEM and op.mem.base == X86_REG_RIP:
            rip_end = insn.address + insn.size
            target_va = rip_end + op.mem.disp
            target_rva2 = target_va - base
            extra += f'  [rip -> 0x{target_rva2:X}]'
        if op.type == CS_OP_MEM and op.mem.base != 0 and op.mem.disp != 0:
            # 简单偏移访问
            pass
    print(f'  0x{rva:05X}: {insn.mnemonic:10s} {insn.op_str}{extra}')
    if insn.mnemonic.startswith('ret') and rva > target_rva + 1:
        break

print()
print('========== Mech.GetPlayer 完整流程 ==========')
# 再看一遍 GetPlayer 调完 0x178F30 后做了什么
target_rva = 0x1A86A0
off = target_rva - text_va
code = text_data[off:off+128]
for insn in md.disasm(code, base + target_rva):
    rva = insn.address - base
    extra = ''
    for op in insn.operands:
        if op.type == CS_OP_MEM and op.mem.base == X86_REG_RIP:
            rip_end = insn.address + insn.size
            target_va = rip_end + op.mem.disp
            target_rva2 = target_va - base
            extra += f'  [rip -> 0x{target_rva2:X}]'
    print(f'  0x{rva:05X}: {insn.mnemonic:10s} {insn.op_str}{extra}')
    if insn.mnemonic.startswith('ret') and rva > target_rva + 1:
        break
