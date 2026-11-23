# -*- coding: utf-8 -*-
"""离线修改 Brigador Killers assets.pack 内的资源结构体（不启动游戏、不调引擎）。

pack 布局（已实测）：
  0x00 u32 magic 0x5EA1C012 | 0x04 u32 ver 0x17B | 0x10 u32 count
  0x78 起四张表（顺序固定，按 count 计算长度）：
    A: u64 × count  —— 资源名在文件中的绝对偏移（NUL 结尾）
    B: u32 × count  —— archetype（11=LEG 12=CHASSIS 14=MECH）
    C: u64 × count  —— 数据块文件偏移
    D: u64 × count  —— 数据块大小
  之后是名称字符串区，0x1000000 起是资源数据区。

用法：
  python packpatch.py <assets.pack> speed <资源路径> <前进> [侧向] [倒车]
  python packpatch.py <assets.pack> offset <资源路径> <结构体内偏移(hex)> <float值>

示例：
  python packpatch.py assets.pack speed assets/data/vics/lowers/rig_volta_carmine_01_lo.json 2.5
"""
import os
import struct
import sys

MAGIC = 0x5EA1C012


def table_layout(f):
    head = f.read(0x40)
    magic, ver = struct.unpack_from('<2I', head, 0)
    count = struct.unpack_from('<I', head, 0x10)[0]
    if magic != MAGIC:
        raise SystemExit('不是有效的 assets.pack（magic=%08x）' % magic)
    a_off = 0x78
    a_n = count * 8
    b_off = (a_off + a_n + 0xF) & ~0xF
    b_n = count * 4
    c_off = (b_off + b_n + 0xF) & ~0xF
    c_n = count * 8
    d_off = c_off + c_n
    return count, a_off, b_off, c_off, d_off


def find_index(f, count, a_off, path):
    want = path.encode('utf-8')
    for i in range(count):
        f.seek(a_off + i * 8)
        no = struct.unpack('<Q', f.read(8))[0]
        f.seek(no)
        s = f.read(len(want) + 1)
        if s[:len(want)] == want and s[len(want):len(want) + 1] == b'\0':
            return i
    return -1


def entry_info(f, idx, b_off, c_off, d_off):
    f.seek(b_off + idx * 4)
    arch = struct.unpack('<I', f.read(4))[0]
    f.seek(c_off + idx * 8)
    off = struct.unpack('<Q', f.read(8))[0]
    f.seek(d_off + idx * 8)
    size = struct.unpack('<Q', f.read(8))[0]
    return arch, off, size


def find_speed_triple(data, fwd, side, rev, acc):
    pat = struct.pack('<6f', fwd, side, rev, acc, acc, acc)
    hits = []
    i = data.find(pat)
    while i >= 0:
        hits.append(i)
        i = data.find(pat, i + 1)
    return hits


def scan_triples(data):
    """扫描 '三连相同 float + 三连相同 float' 的模式（速度/加速度一族）。"""
    out = []
    for rel in range(0, len(data) - 24 + 1, 4):
        a, b, c, d, e, g = struct.unpack_from('<6f', data, rel)
        if a == b == c and d == e == g and 0.0 < a < 1e5 and 0.0 < d < 1e5:
            out.append((rel, (a, d)))
    return out


def read_manifest(f):
    """读出全部条目：[(name_bytes, arch, off, size)]，按名称表原顺序。"""
    count, a_off, b_off, c_off, d_off = table_layout(f)
    out = []
    for i in range(count):
        f.seek(a_off + i * 8)
        no = struct.unpack('<Q', f.read(8))[0]
        f.seek(no)
        name = f.read(300).split(b'\0')[0]
        arch, off, size = entry_info(f, i, b_off, c_off, d_off)
        out.append((name, arch, off, size))
    return out


def _write_pack(f, entries, total, blobs, out_path):
    """entries: [(name,arch,off,size)]；blobs: 依次追加到 EOF 的数据块字节。"""
    count = len(entries)
    a_off = 0x78
    b_off = (a_off + count * 8 + 0xF) & ~0xF
    c_off = (b_off + count * 4 + 0xF) & ~0xF
    d_off = c_off + count * 8
    s_off = 0x56F4A8  # 名称区搬到 0x56F4A8 起的空闲区（原名称区后面紧接其它表）

    f.seek(0)
    header = bytearray(f.read(0x1000000))
    header[0x10:0x14] = struct.pack('<I', count)
    struct.pack_into('<Q', header, 0x18, a_off)
    struct.pack_into('<Q', header, 0x20, b_off)
    struct.pack_into('<Q', header, 0x28, c_off)
    struct.pack_into('<Q', header, 0x30, d_off)
    struct.pack_into('<Q', header, 0x38, s_off)

    name_cur = s_off
    view = memoryview(header)
    for i, (name, arch, off, size) in enumerate(entries):
        struct.pack_into('<Q', view, a_off + i * 8, name_cur)
        struct.pack_into('<I', view, b_off + i * 4, arch)
        struct.pack_into('<Q', view, c_off + i * 8, off)
        struct.pack_into('<Q', view, d_off + i * 8, size)
        header[name_cur:name_cur + len(name)] = name
        header[name_cur + len(name)] = 0
        name_cur += len(name) + 1
    view.release()
    if name_cur >= 0xF30750:
        print('名称字符串超出空闲区上限 0xF30750')
        return 4

    if os.path.exists(out_path):
        os.remove(out_path)
    with open(out_path, 'wb') as g:
        g.write(header)
        f.seek(0x1000000)
        left = total - 0x1000000
        while left > 0:
            chunk = f.read(min(16 * 1024 * 1024, left))
            if not chunk:
                break
            g.write(chunk)
            left -= len(chunk)
        for blob in blobs:
            g.write(blob)
    print('已写出 %s: count=%d 追加 %d 块' % (out_path, count, len(blobs)))
    return 0


def add_clone(pack, src_path, new_path, out_path):
    """复制一个资源条目为新的资源名，写到 out_path（重建清单，不改原文件）。"""
    import os

    f = open(pack, 'rb')
    entries = read_manifest(f)
    total = os.path.getsize(pack)
    src = None
    for e in entries:
        if e[0] == src_path.encode('utf-8'):
            src = e
            break
    if src is None:
        print('找不到源资源:', src_path)
        return 2
    if any(name == new_path.encode('utf-8') for name, _, _, _ in entries):
        print('新名字已存在:', new_path)
        return 3

    f.seek(src[2])
    blob = f.read(src[3])
    entries.append((new_path.encode('utf-8'), src[1], total, len(blob)))
    entries.sort(key=lambda e: e[0])
    rc = _write_pack(f, entries, total, [blob], out_path)
    f.close()
    return rc


def player_clone(pack, unit_path, out_path):
    """只给玩家载具做副本：复制 MECH 及其 LEG，副本 MECH 的 +0xC0 指向新 LEG。"""
    import os

    f = open(pack, 'rb')
    entries = read_manifest(f)
    total = os.path.getsize(pack)
    byname = {e[0]: e for e in entries}
    src = byname.get(unit_path.encode('utf-8'))
    if src is None:
        print('找不到载具资源:', unit_path)
        return 2

    f.seek(src[2])
    mech = bytearray(f.read(src[3]))
    leg_off = struct.unpack_from('<Q', mech, 0xC0)[0]
    leg = None
    for e in entries:
        if e[2] == leg_off:
            leg = e
            break
    if leg is None or leg[1] != 11:
        print('+0xC0 不是 LEG 资源（off=0x%x）' % leg_off)
        return 3

    f.seek(leg[2])
    leg_blob = f.read(leg[3])

    def variant(name):
        s = name.decode('utf-8')
        return (s[:-5] + '_player.json').encode('utf-8')

    new_mech_name, new_leg_name = variant(src[0]), variant(leg[0])
    if new_mech_name in byname or new_leg_name in byname:
        print('副本名已存在:', new_mech_name.decode(), new_leg_name.decode())
        return 3

    leg_new_off = total
    mech_new_off = total + len(leg_blob)
    struct.pack_into('<Q', mech, 0xC0, leg_new_off)

    entries.append((new_leg_name, 11, leg_new_off, len(leg_blob)))
    entries.append((new_mech_name, src[1], mech_new_off, len(mech)))
    entries.sort(key=lambda e: e[0])
    rc = _write_pack(f, entries, total, [leg_blob, bytes(mech)], out_path)
    f.close()
    if rc == 0:
        print('玩家副本: %s (leg=%s)' % (new_mech_name.decode(), new_leg_name.decode()))
    return rc


def sacrifice_clone(pack, unit_path, new_name, out_path):
    """零增长克隆：复用两个孤儿条目（MECH + LEG），原地覆盖数据并把名称改成新名。

    不改条目数量、不改表大小，因此不动重定位表；受害者槽位是源槽位超集，
    克隆时多出的槽位保留受害者原值（有效指针）。
    """
    f = open(pack, 'rb')
    entries = read_manifest(f)
    total = os.path.getsize(pack)
    byname = {e[0]: e for e in entries}
    byoff = {e[2]: e for e in entries}
    src = byname.get(unit_path.encode('utf-8'))
    if src is None:
        print('找不到源载具:', unit_path)
        return 2
    f.seek(src[2])
    mech = bytearray(f.read(src[3]))
    leg_off = struct.unpack_from('<Q', mech, 0xC0)[0]
    src_leg = byoff.get(leg_off)
    if src_leg is None or src_leg[1] != 11:
        print('源 +0xC0 不是 LEG')
        return 3

    # 读取重定位槽位表（A：u64 槽位文件偏移）
    f.seek(0x2CFF88)
    A = set(struct.unpack('<%dQ' % 0x3AF2A, f.read(0x3AF2A * 8)))

    def slot_rels(off, size):
        return {x - off for x in A if off <= x < off + size}

    mech_slots = slot_rels(src[2], src[3])
    leg_slots = slot_rels(src_leg[2], src_leg[3])

    # 找受害者：arch 相同、大小相同、槽位超集，且未被任何资源引用
    referenced = set()
    for n, a, o, s in entries:
        if a in (11, 12, 14):
            f.seek(o)
            data = f.read(s)
            for j in range(0, s - 7, 8):
                v = struct.unpack_from('<Q', data, j)[0]
                if v in byoff:
                    referenced.add(v)

    def pick(arch, size, slots, prefer):
        best = None
        best_score = -1
        for n, a, o, s in entries:
            if a != arch or s != size or o in referenced:
                continue
            rels = slot_rels(o, s)
            if not slots.issubset(rels):
                continue
            score = sum(1 for kw in prefer if kw in n) * 10 + len(rels)
            if score > best_score:
                best, best_score = (n, a, o, s, rels), score
        return best

    vm = pick(14, src[3], mech_slots, [b'corpse', b'tuktuk'])
    vl = pick(11, src_leg[3], leg_slots, [b'tuktuk', b'_F', b'-F'])
    if vm is None or vl is None:
        print('找不到合适的受害条目（MECH=%s LEG=%s）' % (bool(vm), bool(vl)))
        return 4
    print('MECH 受害: %s' % vm[0].decode())
    print('LEG  受害: %s' % vl[0].decode())

    # 克隆 MECH：改写 +0xC0 指向受害 LEG；受害多出的槽位保留其原值
    f.seek(vm[2])
    vm_orig = f.read(vm[3])
    extra = vm[4] - mech_slots
    struct.pack_into('<Q', mech, 0xC0, vl[2])
    for rel in extra:
        if 0 <= rel <= len(mech) - 8:
            struct.pack_into('<Q', mech, rel, struct.unpack_from('<Q', vm_orig, rel)[0])
    # 克隆 LEG
    f.seek(src_leg[2])
    leg = bytearray(f.read(src_leg[3]))
    leg_extra = vl[4] - leg_slots
    for rel in leg_extra:
        if 0 <= rel <= len(leg) - 8:
            f.seek(vl[2] + rel)
            v = struct.unpack('<Q', f.read(8))[0]
            struct.pack_into('<Q', leg, rel, v)

    # 重写名称：受害两条改名，字符串写入空闲区
    rename = {vm[0]: new_name.encode('utf-8')}
    base = new_name[:-5]
    rename[vl[0]] = (base + '_lo_player.json').encode('utf-8')

    # 名称表重排（count 不变）：四张表按新名称排序重写；表位置直接用头部现有值
    count = len(entries)
    f.seek(0)
    header = bytearray(f.read(0x1000000))
    a_off, b_off, c_off, d_off = struct.unpack_from('<4Q', header, 0x18)
    names = [rename.get(e[0], e[0]) for e in entries]
    order = sorted(range(count), key=lambda i: names[i])
    s_off = 0x56F4A8
    name_cur = s_off
    for pos, i in enumerate(order):
        nm = names[i]
        header[name_cur:name_cur + len(nm)] = nm
        header[name_cur + len(nm)] = 0
        struct.pack_into('<Q', header, a_off + pos * 8, name_cur)
        struct.pack_into('<I', header, b_off + pos * 4, entries[i][1])
        struct.pack_into('<Q', header, c_off + pos * 8, entries[i][2])
        struct.pack_into('<Q', header, d_off + pos * 8, entries[i][3])
        name_cur += len(nm) + 1
    if name_cur >= 0xF30750:
        print('名称区溢出')
        return 5

    if os.path.exists(out_path):
        os.remove(out_path)
    patch = sorted([(vm[2], vm[3], bytes(mech)), (vl[2], vl[3], bytes(leg))])
    with open(out_path, 'wb') as g:
        g.write(header)
        pos = 0x1000000
        for off, size, blob in patch:
            while pos < off:
                chunk = f.read(min(16 * 1024 * 1024, off - pos))
                if not chunk:
                    break
                g.write(chunk)
                pos += len(chunk)
            f.seek(off + size)
            g.write(blob)
            pos = off + size
        left = total - pos
        while left > 0:
            chunk = f.read(min(16 * 1024 * 1024, left))
            if not chunk:
                break
            g.write(chunk)
            left -= len(chunk)
    f.close()
    print('已写出 %s（MECH=%s LEG=%s）' % (out_path, new_name, rename[vl[0]].decode()))
    return 0


def main():
    if len(sys.argv) >= 6 and sys.argv[2] == 'sacrifice-clone':
        return sacrifice_clone(sys.argv[1], sys.argv[3], sys.argv[4], sys.argv[5])
    if len(sys.argv) >= 5 and sys.argv[2] == 'add-clone':
        out = sys.argv[5] if len(sys.argv) > 5 else sys.argv[1] + '.test'
        return add_clone(sys.argv[1], sys.argv[3], sys.argv[4], out)
    if len(sys.argv) >= 5 and sys.argv[2] == 'player-clone':
        out = sys.argv[4] if len(sys.argv) > 4 else sys.argv[1] + '.test'
        return player_clone(sys.argv[1], sys.argv[3], out)
    if len(sys.argv) < 5:
        print(__doc__)
        return 1
    pack, mode, path = sys.argv[1], sys.argv[2], sys.argv[3]
    f = open(pack, 'r+b')
    count, a_off, b_off, c_off, d_off = table_layout(f)
    idx = find_index(f, count, a_off, path)
    if idx < 0:
        print('找不到资源:', path)
        return 2
    arch, off, size = entry_info(f, idx, b_off, c_off, d_off)
    print('idx=%d arch=%d off=0x%x size=%d' % (idx, arch, off, size))

    if mode == 'speed':
        fwd = float(sys.argv[4])
        side = float(sys.argv[5]) if len(sys.argv) > 5 else fwd
        rev = float(sys.argv[6]) if len(sys.argv) > 6 else fwd
        old = None
        data = f.read(size) if f.seek(off) == off else b''
        for acc in (15.0, 10.0, 20.0, 25.0, 30.0):
            hits = find_speed_triple(data, 1.25, 1.25, 1.25, acc) or \
                   find_speed_triple(data, fwd, side, rev, acc)
            if hits:
                old = acc
                break
        if not old:
            cand = scan_triples(data)
            if len(cand) != 1:
                print('速度三元组候选=%d，请改用 offset 模式' % len(cand))
                for rel, vals in cand[:8]:
                    print('  relative=0x%x speed=%g acc=%g' % (rel, vals[0], vals[1]))
                return 3
            hits = [cand[0][0]]
            old = cand[0][1][1]
            print('  自动定位 relative=0x%x speed=%g acc=%g' % (hits[0], cand[0][1][0], old))
        for rel in hits:
            f.seek(off + rel)
            cur = struct.unpack('<3f', f.read(12))
            print('  命中 relative=0x%x 当前=%s' % (rel, cur))
            f.seek(off + rel)
            f.write(struct.pack('<3f', fwd, side, rev))
            print('  已写入 %s (加速度=%g)' % ((fwd, side, rev), old))
        f.flush()
        return 0

    if mode == 'field':
        import json
        import os
        name, newval = sys.argv[4], float(sys.argv[5])
        dry = '--dry' in sys.argv
        arch_name = {11: 'leg', 12: 'chassis', 14: 'mech'}.get(arch)
        mpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'maps', arch_name + '.json')
        doc = json.load(open(mpath, encoding='utf-8'))
        meta = doc['fields'].get(name)
        if not meta:
            print('映射表里没有字段:', name)
            print('可用字段示例:', list(doc['fields'])[:12])
            return 4
        rel = meta['offset']
        kind = meta['kind']
        written = newval * 3.141592653589793 / 180.0 if kind == 'f32_deg' else newval
        f.seek(off + rel)
        raw = f.read(4)
        old = struct.unpack('<f', raw)[0] if kind.startswith('f32') else struct.unpack('<i', raw)[0]
        print('%s = %g (off=0x%x kind=%s) 当前=%g' % (name, newval, rel, kind, old))
        if dry:
            print('  --dry：未写入')
            return 0
        f.seek(off + rel)
        f.write(struct.pack('<f', written) if kind.startswith('f32') else struct.pack('<i', int(newval)))
        f.flush()
        print('  已写入结构体值 %g' % written)
        return 0

    if mode == 'offset':
        rel = int(sys.argv[4], 0)
        val = float(sys.argv[5])
        f.seek(off + rel)
        old = struct.unpack('<f', f.read(4))[0]
        f.seek(off + rel)
        f.write(struct.pack('<f', val))
        f.flush()
        print('  relative=0x%x: %g -> %g' % (rel, old, val))
        return 0

    print('未知模式:', mode)
    return 1


if __name__ == '__main__':
    sys.exit(main())
