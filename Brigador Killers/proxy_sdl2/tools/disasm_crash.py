import pefile
pe = pefile.PE(r'C:\Program Files (x86)\Steam\steamapps\common\Brigador Killers\brigadorkillers.exe')
base = pe.OPTIONAL_HEADER.ImageBase

from capstone import *
md = Cs(CS_ARCH_X86, CS_MODE_64)

rva = 0x3892CF
data = pe.get_memory_mapped_image()

# 从 rva-48 开始, 让 capstone 完整覆盖到 rva+48
start = rva - 48
end = rva + 64
buf = data[start:end]
print(f'RVA 0x{rva:x} (VA 0x{base+rva:x}):')
for ins in md.disasm(buf, base + start):
    marker = ' <--- CRASH' if ins.address == base + rva else ''
    print(f'  {ins.address:016X}: {ins.mnemonic:7s} {ins.op_str}{marker}')
    if ins.address > base + rva + 32:
        break
