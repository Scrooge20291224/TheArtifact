import pefile
pe = pefile.PE(r'C:\Program Files (x86)\Steam\steamapps\common\Brigador Killers\brigadorkillers.exe')
base = pe.OPTIONAL_HEADER.ImageBase

from capstone import *
md = Cs(CS_ARCH_X86, CS_MODE_64)

rva = 0xE92CF  # 之前算错了, 重新按 runtime base 算
data = pe.get_memory_mapped_image()

start = rva - 48
end = rva + 64
buf = data[start:end]
print(f'RVA 0x{rva:x} (static VA 0x{base+rva:x}):')
for ins in md.disasm(buf, base + start):
    marker = ' <--- CRASH' if ins.address == base + rva else ''
    print(f'  {ins.address:016X}: {ins.mnemonic:7s} {ins.op_str}{marker}')
    if ins.address > base + rva + 48:
        break
