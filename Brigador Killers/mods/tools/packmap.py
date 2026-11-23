# -*- coding: utf-8 -*-
"""用导出的 JSON 对拍 pack 内二进制结构体，自动标定 字段 -> 偏移。

思路：
  JSON 叶子顺序 = 引擎序列化代码顺序 = 结构体字段顺序（大体一致），
  于是把每个叶子在结构体里所有可能出现的位置作为候选，做单调递增的序列对齐，
  命中数最多的路径即字段映射。
用法：
  python packmap.py <assets.pack> <资源路径> <导出的json> [输出map.json]
"""
import json
import struct
import sys
from bisect import bisect_left

MAGIC = 0x5EA1C012


def open_pack(path):
    f = open(path, 'rb')
    head = f.read(0x40)
    magic = struct.unpack_from('<I', head, 0)[0]
    if magic != MAGIC:
        raise SystemExit('bad magic %08x' % magic)
    count = struct.unpack_from('<I', head, 0x10)[0]
    a = 0x78
    b = (a + count * 8 + 0xF) & ~0xF
    c = (b + count * 4 + 0xF) & ~0xF
    d = c + count * 8
    return f, count, a, b, c, d


def find_entry(f, count, a_off, b_off, c_off, d_off, path):
    want = path.encode()
    for i in range(count):
        f.seek(a_off + i * 8)
        no = struct.unpack('<Q', f.read(8))[0]
        f.seek(no)
        s = f.read(len(want) + 1)
        if s[:len(want)] == want and s[len(want):len(want) + 1] == b'\0':
            f.seek(c_off + i * 8)
            off = struct.unpack('<Q', f.read(8))[0]
            f.seek(d_off + i * 8)
            size = struct.unpack('<Q', f.read(8))[0]
            return i, off, size
    return -1, 0, 0


def flatten(o, pre=''):
    out = []

    def walk(v, p):
        if isinstance(v, dict):
            for k, x in v.items():
                walk(x, p + '.' + k if p else k)
        elif isinstance(v, list):
            for i, x in enumerate(v):
                walk(x, p + '[%d]' % i)
        else:
            out.append((p, v))
    walk(o, pre)
    return out


def candidates(data, val):
    res = []
    if isinstance(val, str):
        b = val.encode('utf-8')
        if not b:
            return res
        i = data.find(b)
        while i >= 0:
            res.append((i, 'str'))
            i = data.find(b, i + 1)
        return res
    if isinstance(val, bool):
        return res
    if isinstance(val, (int, float)):
        f32 = struct.pack('<f', float(val))
        i = data.find(f32)
        while i >= 0:
            res.append((i, 'f32'))
            i = data.find(f32, i + 1)
        if isinstance(val, int) and -2**31 <= val < 2**31:
            i32 = struct.pack('<i', val)
            i = data.find(i32)
            while i >= 0:
                res.append((i, 'i32'))
                i = data.find(i32, i + 1)
        return sorted(set(res))
    return res


def align(leaves, data):
    """DP：在候选位置中选严格递增的一条，最大化命中数。"""
    cand = [candidates(data, v) for _, v in leaves]
    n = len(leaves)
    # dp[i][j] = 以第 i 个叶子的第 j 个候选结尾时的最大命中数；记录前驱
    dp = [[1] * len(cand[0])] if n else []
    prev = [[-1] * len(cand[0])] if n else []
    for i in range(1, n):
        cur = [1] * len(cand[i])
        pr = [-1] * len(cand[i])
        if not cand[i]:
            dp.append(cur)
            prev.append(pr)
            continue
        prev_positions = [(p, k) for k, p in enumerate(cand[i - 1])]
        prev_positions.sort()
        poss = [p for p, _ in prev_positions]
        # 前缀最大，便于 O(C log C)
        best_for = []
        best_val = -1
        best_k = -1
        for p, k in prev_positions:
            v = dp[i - 1][k]
            if v > best_val:
                best_val, best_k = v, k
            best_for.append((p, best_val, best_k))
        import bisect
        keys = [x[0] for x in best_for]
        for j, p in enumerate(cand[i]):
            idx = bisect.bisect_left(keys, p) - 1
            if idx >= 0:
                v = best_for[idx][1]
                if v > 0:
                    cur[j] = v + 1
                    pr[j] = best_for[idx][2]
        dp.append(cur)
        prev.append(pr)
    if not n:
        return []
    last = max(range(len(dp[-1])), key=lambda k: dp[-1][k])
    path = [None] * n
    cur = last
    for i in range(n - 1, -1, -1):
        if not cand[i]:
            path[i] = None
            cur = -1
            continue
        if cur < 0:
            # 该叶子无候选，从上一个有候选的继续需要向前找，简化：标记 None
            path[i] = None
            continue
        path[i] = cand[i][cur]
        cur = prev[i][cur] if i > 0 else -1
    return path


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        return 1
    pack, asset, jpath = sys.argv[1], sys.argv[2], sys.argv[3]
    f, count, a, b, c, d = open_pack(pack)
    idx, off, size = find_entry(f, count, a, b, c, d, asset)
    if idx < 0:
        print('entry not found')
        return 2
    f.seek(off)
    data = f.read(size)
    leaves = flatten(json.load(open(jpath, encoding='utf-8')))
    print('entry idx=%d off=0x%x size=%d  leaves=%d' % (idx, off, size, len(leaves)))
    path = align(leaves, data)
    hit = sum(1 for p in path if p)
    print('aligned %d/%d' % (hit, len(leaves)))
    rows = []
    for (k, v), p in zip(leaves, path):
        if not p:
            rows.append({'key': k, 'value': v, 'offset': None})
            print('  MISS  %-46s %r' % (k, v))
            continue
        o, t = p
        rows.append({'key': k, 'value': v, 'offset': o, 'kind': t})
        print('  %-46s off=0x%-5x %-4s %r' % (k, o, t, v))
    if len(sys.argv) > 4:
        json.dump(rows, open(sys.argv[4], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('map ->', sys.argv[4])
    return 0


if __name__ == '__main__':
    sys.exit(main())
