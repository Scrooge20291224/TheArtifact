import re

log = open(r'C:\Program Files (x86)\Steam\steamapps\common\Brigador Killers\pa_probe.log').read()

# 按 "dumping 0x800 bytes @" 分块
blocks = log.split('dumping 0x800 bytes @')

def parse_dump(block):
    """解析 dump 块为 {offset: bytes}"""
    data = {}
    for line in block.split('\n'):
        # 格式: "  +0000  D3 AA 5F 42 C6 7A 2A 42 ..."
        m = re.match(r'\s*\+([0-9A-Fa-f]{4})\s+((?:[0-9A-Fa-f]{2}\s+){16})', line)
        if m:
            off = int(m.group(1), 16)
            hex_bytes = m.group(2).split()
            for j, hb in enumerate(hex_bytes):
                data[off + j] = int(hb, 16)
    return data

player = parse_dump(blocks[1] if len(blocks) > 1 else '')
fake   = parse_dump(blocks[2] if len(blocks) > 2 else '')

print(f"玩家有效字节: {len(player)}")
print(f"fake 有效字节: {len(fake)}")

# diff: 玩家非零且 fake 为零的 byte (Player_Action 区域)
player_only_bytes = []
all_diff_bytes = []

for off in range(0, 0x800):
    pb = player.get(off, 0)
    fb = fake.get(off, 0)
    if pb != fb:
        all_diff_bytes.append((off, pb, fb))
        if pb != 0 and fb == 0:
            player_only_bytes.append((off, pb))

print(f"\n=== 总 diff byte 数: {len(all_diff_bytes)} ===")
print(f"=== 玩家非零 + fake 为零 (Player_Action 区域): {len(player_only_bytes)} ===")

# 按连续区间分组 player_only_bytes
print("\n--- 玩家独有 (非零, fake 为零) 连续区间 ---")
if player_only_bytes:
    ranges = []
    start = player_only_bytes[0][0]
    prev = start
    for off, pb in player_only_bytes[1:]:
        if off == prev + 1:
            prev = off
        else:
            ranges.append((start, prev))
            start = off
            prev = off
    ranges.append((start, prev))
    
    for s, e in ranges:
        length = e - s + 1
        # 打印这区间的 hex
        hex_str = ' '.join(f'{player[o]:02X}' for o in range(s, e+1))
        print(f"  +0x{s:04X} ~ +0x{e:04X} ({length}B): {hex_str}")

# 也显示玩家独有但 fake 也是非零的 (值不同)
print("\n--- 值不同但两边都非零 (可能是组件/指针不同) ---")
for off, pb, fb in all_diff_bytes:
    if pb != 0 and fb != 0:
        print(f"  +0x{off:04X}: player=0x{pb:02X} fake=0x{fb:02X}")

print("\n=== 关键发现总结 ===")
print("玩家独有的连续非零区间 = Player_Action 布局!")
