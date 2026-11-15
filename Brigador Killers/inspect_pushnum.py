import pefile
from capstone import *

pe = pefile.PE(r'C:\Program Files (x86)\Steam\steamapps\common\Brigador Killers\brigadorkillers.exe', fast_load=False)
base = pe.OPTIONAL_HEADER.ImageBase
text_va, text_data = None, None
for s in pe.sections:
    if s.Name.startswith(b'.text'):
        text_va = s.VirtualAddress
        text_data = s.get_data()
        break

md = Cs(CS_ARCH_X86, CS_MODE_64)

# 看 caller 0x49C7B 附近的完整代码（这个 caller 之前有 call 0x318A50）
# 0x318A50 在 pushnumber 之后 0x40 字节，应该是另一个 Lua API
for rva in [0x318A50, 0x49C6B]:
    off = rva - text_va
    raw = text_data[off:off+24]
    print(f'=== RVA=0x{rva:X} ===')
    for insn in md.disasm(raw, base + rva):
        print(f'  0x{rva + (insn.address - base - rva):X}: {insn.mnemonic} {insn.op_str}')
    print()

# 看 caller 0x493C6 所在的函数（pushnumber caller，前面有 0x178F20）
off = 0x49380 - text_va
print('=== caller context 0x49380 ~ 0x49400 ===')
code = text_data[off:off+128]
for insn in md.disasm(code, base + 0x49380):
    rva = insn.address - base
    print(f'  0x{rva:X}: {insn.mnemonic:10s} {insn.op_str}')
    if insn.mnemonic.startswith('ret') and rva > 0x49390:
        break
