import re

log = open(r'C:\Program Files (x86)\Steam\steamapps\common\Brigador Killers\pa_probe.log').read()

# 按 dump_qwords 分块
blocks = log.split('dump_qwords @')
# blocks[0] = 头部, blocks[1] = 玩家 dump, blocks[2] = fake dump

def parse_dump(block):
    offsets = {}
    for line in block.split('\n'):
        m = re.search(r'\+0x([0-9A-Fa-f]+) qword=0x([0-9A-Fa-f]+)', line)
        if m:
            off = int(m.group(1), 16)
            val = int(m.group(2), 16)
            offsets[off] = val
    return offsets

player = parse_dump(blocks[1] if len(blocks) > 1 else '')
fake   = parse_dump(blocks[2] if len(blocks) > 2 else '')

print(f"玩家 heap ptrs: {len(player)}")
print(f"fake heap ptrs: {len(fake)}")

# 只在玩家里有的（玩家独有）
player_only = {}
for off, val in player.items():
    if off not in fake or fake[off] != val:
        if off not in fake:
            player_only[off] = val

# 也在 fake 里但值不同
diff_val = {}
for off in set(list(player.keys()) + list(fake.keys())):
    pv = player.get(off)
    fv = fake.get(off)
    if pv is not None and fv is not None and pv != fv:
        diff_val[off] = (pv, fv)

print()
print("=== 玩家独有 (fake 里完全没有) ===")
for off in sorted(player_only.keys()):
    print(f"  +0x{off:04X}: 0x{player_only[off]:016X}")

print()
print("=== 都有但值不同 ===")
for off in sorted(diff_val.keys()):
    pv, fv = diff_val[off]
    # 去掉两个值都是模块内地址的 (exe base + rva 模式)
    # 模块地址高 16 位不是 0x0000
    def is_module_addr(v):
        return (v >> 48) != 0
    if is_module_addr(pv) or is_module_addr(fv):
        # 还是打出来但标一下
        tag = "[MOD]"
    else:
        tag = ""
    print(f"  +0x{off:04X}: player=0x{pv:016X} fake=0x{fv:016X} {tag}")

print()
print("=== 重点: 纯 heap 地址 (高 16 位=0) 且玩家独有或值不同 ===")
for off in sorted(set(list(player_only.keys()) + list(diff_val.keys()))):
    if off in player_only:
        pv = player_only[off]
        fv_str = "(无)"
    else:
        pv, fv = diff_val[off]
        fv_str = f"0x{fv:016X}"
    
    if (pv >> 48) == 0:  # 纯 heap
        print(f"  +0x{off:04X}: player=0x{pv:016X} fake={fv_str}")
