# 解析 pa_probe.log 里的 hex dump 并做 pairwise diff
# 用法: python tools/diff_dump.py
import re, sys, os

LOG_PATH = r"C:\Program Files (x86)\Steam\steamapps\common\Brigador Killers\pa_probe.log"

def parse_log(path):
    """返回 list of (label, base_addr, bytes_list)"""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    dumps = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        # 找 "dumping N bytes @ ADDR"
        m = re.search(r"dumping (\d+) bytes @ ([0-9A-Fa-f]+)", line)
        if m:
            length = int(m.group(1))
            base = int(m.group(2), 16)
            i += 1
            data = bytearray(length)
            while i < len(lines):
                line = lines[i].rstrip()
                m2 = re.match(r"\s*\+([0-9A-Fa-f]+)\s+((?:[0-9A-Fa-f]{2}\s+){1,16})", line)
                if m2:
                    offset = int(m2.group(1), 16)
                    hexbytes = m2.group(2).strip().split()
                    for j, hb in enumerate(hexbytes):
                        if offset + j < length:
                            data[offset + j] = int(hb, 16)
                    i += 1
                else:
                    break
            # 尝试从之前的 log 行提取 label（udata=...）
            label = f"dump_{len(dumps)}"
            for k in range(max(0, i-20), i):
                if k < len(lines):
                    lm = re.search(r"\[pa\] udata=(\S+)\s+outer=(\d+)\s+inner=(\d+)\s+id=(\d+)", lines[k])
                    if lm:
                        udata = lm.group(1)
                        outer, inner, id_ = lm.group(2), lm.group(3), lm.group(4)
                        label = f"udata={udata} inner={inner} id={id_}"
                        break
            dumps.append((label, base, bytes(data)))
        else:
            i += 1
    return dumps

def classify(label):
    """尝试从之前的 Lua 输出推断角色类型（看 log 里的 print）"""
    return label

def diff_bytes(a, b, name_a, name_b):
    """逐字节 diff，报告所有不同的偏移"""
    n = min(len(a), len(b))
    diffs = []
    i = 0
    while i < n:
        if a[i] != b[i]:
            start = i
            while i < n and a[i] != b[i]:
                i += 1
            run_len = i - start
            # 把连续不同的 run 合成一行
            diffs.append((start, run_len, a[start:i], b[start:i]))
        else:
            i += 1
    return diffs

def interpret_diffs(diffs, base_a, base_b):
    """尝试把 diff 段解释成有意义的东西：指针、float、dword 等"""
    out = []
    for off, run_len, a_bytes, b_bytes in diffs:
        # 检查是否是 8 字节指针（64-bit little-endian）
        if run_len >= 8:
            ptr_a = int.from_bytes(a_bytes[:8], "little")
            ptr_b = int.from_bytes(b_bytes[:8], "little")
            if ptr_a != ptr_b:
                # 看哪个像指针（高 16 位非零）
                kind_a = "ptr" if ptr_a > 0x10000 else f"0x{ptr_a:X}"
                kind_b = "ptr" if ptr_b > 0x10000 else f"0x{ptr_b:X}"
                out.append(f"  +0x{off:04X} ({run_len:3d}B): A={kind_a}  B={kind_b}")
                # 如果是 exe 内部指针，算 RVA
                for val, tag in [(ptr_a, "A"), (ptr_b, "B")]:
                    if 0x140000000 <= val < 0x150000000:
                        out.append(f"      {tag} RVA = 0x{val - 0x140000000:X} (exe .text 区间)")
        # 检查 4 字节 float
        if run_len >= 4:
            import struct
            for start_j in range(run_len - 3):
                try:
                    fa = struct.unpack("<f", a_bytes[start_j:start_j+4])[0]
                    fb = struct.unpack("<f", b_bytes[start_j:start_j+4])[0]
                    if abs(fa - fb) > 1e-6 and abs(fa) < 1e8 and abs(fb) < 1e8:
                        out.append(f"  +0x{off+start_j:04X} float: A={fa:.4f}  B={fb:.4f}")
                        break
                except:
                    pass
        # 默认 hex dump
        hex_a = " ".join(f"{x:02X}" for x in a_bytes[:16])
        hex_b = " ".join(f"{x:02X}" for x in b_bytes[:16])
        out.append(f"  +0x{off:04X} ({run_len:3d}B): A={hex_a}")
        out.append(f"                         B={hex_b}")
    return out

def main():
    if not os.path.exists(LOG_PATH):
        print(f"!! log 不存在: {LOG_PATH}")
        return
    dumps = parse_log(LOG_PATH)
    if len(dumps) < 2:
        print(f"!! 只有 {len(dumps)} 个 dump，需要至少 2 个")
        return

    print(f"解析到 {len(dumps)} 个 dump:")
    for i, (label, base, data) in enumerate(dumps):
        print(f"  [{i}] base=0x{base:X} size={len(data)} label={label}")
    print()

    # Pairwise diff
    for i in range(len(dumps)):
        for j in range(i+1, len(dumps)):
            la, ba, da = dumps[i]
            lb, bb, db = dumps[j]
            diffs = diff_bytes(da, db, la, lb)
            print(f"=== [{i}] vs [{j}]: {la}  VS  {lb} ===")
            print(f"  不同区间数: {len(diffs)}")
            interesting = [d for d in diffs if d[1] >= 4]
            print(f"  其中 >=4 字节的: {len(interesting)}")
            for line in interpret_diffs(interesting, ba, bb):
                print(line)
            print()

if __name__ == "__main__":
    main()
