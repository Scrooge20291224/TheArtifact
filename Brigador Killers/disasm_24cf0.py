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

# 0x178F30 不是 ret, 是 jmp 0x140024cf0
# 反汇编 0x24CF0
target = 0x24CF0
off = target - text_va
print(f'========== RVA=0x{target:X} (真正的 get_player) ==========')
code = text_data[off:off+256]
for insn in md.disasm(code, base + target):
    rva = insn.address - base
    extra = ''
    for op in insn.operands:
        if op.type == CS_OP_MEM and op.mem.base == X86_REG_RIP:
            rip_end = insn.address + insn.size
            tv = rip_end + op.mem.disp
            extra += f' [->0x{tv-base:X}]'
    print(f'  0x{rva:05X}: {insn.mnemonic:10s} {insn.op_str}{extra}')
    if insn.mnemonic.startswith('ret') and rva > target + 1:
        break
