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

md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True

target = 0x1A86A0
off = target - text_va
print(f'========== Mech.GetPlayer RVA=0x{target:X} ==========')
code = text_data[off:off+512]
for insn in md.disasm(code, base + target):
    rva = insn.address - base
    print(f'  0x{rva:05X}: {insn.mnemonic:10s} {insn.op_str}')
    if insn.mnemonic.startswith('ret') and rva > target + 2:
        break

print()
print('========== Mech.DisableAI RVA=0x1A93D0 ==========')
target = 0x1A93D0
off = target - text_va
code = text_data[off:off+256]
for insn in md.disasm(code, base + target):
    rva = insn.address - base
    print(f'  0x{rva:05X}: {insn.mnemonic:10s} {insn.op_str}')
    if insn.mnemonic.startswith('ret') and rva > target + 2:
        break
