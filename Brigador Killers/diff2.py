import re

log = open(r'C:\Program Files (x86)\Steam\steamapps\common\Brigador Killers\pa_probe.log').read()
blocks = log.split('dumping 0x800 bytes @')

def parse_dump(block):
    data = {}
    for line in block.split('\n'):
        m = re.match(r'\s*\+([0-9A-Fa-f]{4})\s+((?:[0-9A-Fa-f]{2}\s+){16})', line)
        if m:
            off = int(m.group(1), 16)
            hex_bytes = m.group(2).split()
            for j, hb in enumerate(hex_bytes):
                data[off + j] = int(hb, 16)
    return data

player = parse_dump(blocks[1])
fake   = parse_dump(blocks[2])

print("=== 值不同但两边都非零 (需要一起拷!) ===")
print("这些可能是指针, type=6 后引擎会 deref")

diffs = []
for off in range(0, 0x800):
    pb = player.get(off, 0)
    fb = fake.get(off, 0)
    if pb != fb and pb != 0 and fb != 0:
        diffs.append((off, pb, fb))

# 合并成连续块
if diffs:
    ranges = []
    s, prev = diffs[0][0], diffs[0][0]
    for off, pb, fb in diffs[1:]:
        if off == prev + 1:
            prev = off
        else:
            ranges.append((s, prev))
            s, prev = off, off
    ranges.append((s, prev))
    
    for rng_start, rng_end in ranges:
        nbytes = rng_end - rng_start + 1
        hex_str = ' '.join(f'{player[o]:02X}' for o in range(rng_start, rng_end+1))
        print(f"  +0x{rng_start:04X}~+0x{rng_end:04X} ({nbytes}B):")
        print(f"    player: {hex_str}")
        
        # 尝试解码为指针 (8 字节小端)
        if nbytes >= 8 and (nbytes % 8 == 0):
            for o in range(rng_start, rng_end - 7, 8):
                ptr_bytes = bytes(player.get(o+i, 0) for i in range(8))
                ptr_val = int.from_bytes(ptr_bytes, 'little')
                # 判断是不是 heap 指针 (Windows user-mode heap 通常 0x000001... 或 0x00007...)
                if ptr_val and (ptr_val > 0x100000000 or ptr_val < 0x00007FFFFFFFFFFF):
                    print(f"    +0x{o:04X} qword = 0x{ptr_val:X} ({ptr_val:#x})")

# 再检查: 玩家独有 (player!=0, fake==0) 的值
print("\n=== 玩家独有 (fake 为 0) 但不是纯 float 的 ===")
for off in range(0, 0x800):
    pb = player.get(off, 0)
    fb = fake.get(off, 0)
    if pb != 0 and fb == 0:
        print(f"  +0x{off:04X}: player=0x{pb:02X} fake=0x00")
