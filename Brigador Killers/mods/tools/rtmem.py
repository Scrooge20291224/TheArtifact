# -*- coding: utf-8 -*-
"""运行时内存读写小工具（Windows / ctypes），用于 Brigador Killers 资源结构侦察。

用法：
  python rtmem.py info <pid>
  python rtmem.py dump <pid> <addr> <len> [--f32]
  python rtmem.py cmp  <pid> <addr> <pack> <entry>      # 内存 vs pack 条目 payload 差异
  python rtmem.py cmpunit <pid> <cloneAddr> <legAddr> <pack> <mechEntry>
                                                        # 同时对比 MECH 与其 +0xC0 LEG
  python rtmem.py write <pid> <addr> <hex> [--yes]      # 写内存（必须显式 --yes）
  python rtmem.py swap <pid> <pack> <targetEntry> <cloneMechAddr> <cloneLegAddr> [--yes]
                                                        # 运行时换类：目标载具 payload 灌入玩家克隆槽
"""
import ctypes
import os
import struct
import sys
import tempfile
from ctypes import wintypes

k32 = ctypes.WinDLL('kernel32', use_last_error=True)
psapi = ctypes.WinDLL('psapi', use_last_error=True)

LIST_MODULES_ALL = 0x03
OFF_RES_ROOT = 0x0B38850
OFF_PACK_IN_ROOT = 0x2718

PROCESS_VM_READ = 0x10
PROCESS_VM_WRITE = 0x20
PROCESS_VM_OPERATION = 0x08
PROCESS_QUERY_INFORMATION = 0x400

k32.OpenProcess.restype = wintypes.HANDLE
k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
k32.ReadProcessMemory.restype = wintypes.BOOL
k32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.WriteProcessMemory.restype = wintypes.BOOL
k32.WriteProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                   ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.CloseHandle.argtypes = [wintypes.HANDLE]

MAGIC = 0x5EA1C012


class Proc:
    def __init__(self, pid, write=False):
        access = PROCESS_VM_READ | PROCESS_QUERY_INFORMATION
        if write:
            access |= PROCESS_VM_WRITE | PROCESS_VM_OPERATION
        self.h = k32.OpenProcess(access, False, int(pid))
        if not self.h:
            raise SystemExit('OpenProcess 失败 pid=%s err=%d' % (pid, ctypes.get_last_error()))
        self.pid = int(pid)

    def read(self, addr, n):
        buf = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t(0)
        if not k32.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)):
            return None
        return buf.raw[:got.value]

    def q(self, addr):
        b = self.read(addr, 8)
        return struct.unpack('<Q', b)[0] if b and len(b) == 8 else None

    def u32(self, addr):
        b = self.read(addr, 4)
        return struct.unpack('<I', b)[0] if b and len(b) == 4 else None

    def f32(self, addr):
        b = self.read(addr, 4)
        return struct.unpack('<f', b)[0] if b and len(b) == 4 else None

    def write(self, addr, data):
        n = len(data)
        buf = ctypes.create_string_buffer(data, n)
        put = ctypes.c_size_t(0)
        ok = k32.WriteProcessMemory(self.h, ctypes.c_void_p(addr), buf, n, ctypes.byref(put))
        return bool(ok) and put.value == n

    def close(self):
        k32.CloseHandle(self.h)


class Pack:
    def __init__(self, path):
        self.f = open(path, 'rb')
        head = self.f.read(0x60)
        magic = struct.unpack_from('<I', head, 0)[0]
        if magic != MAGIC:
            raise SystemExit('不是有效 assets.pack: %08x' % magic)
        self.count = struct.unpack_from('<I', head, 0x10)[0]
        (self.a, self.b, self.c, self.d, self.s) = struct.unpack_from('<5Q', head, 0x18)
        self.rel_off, self.rel_cnt = struct.unpack_from('<2Q', head, 0x40)
        self.entries = []
        for i in range(self.count):
            self.f.seek(self.a + i * 8)
            no = struct.unpack('<Q', self.f.read(8))[0]
            self.f.seek(no)
            name = self.f.read(300).split(b'\0')[0]
            self.f.seek(self.b + i * 4)
            arch = struct.unpack('<I', self.f.read(4))[0]
            self.f.seek(self.c + i * 8)
            off = struct.unpack('<Q', self.f.read(8))[0]
            self.f.seek(self.d + i * 8)
            size = struct.unpack('<Q', self.f.read(8))[0]
            self.entries.append((name, arch, off, size))

    def by_name(self, name):
        want = name.encode('utf-8') if isinstance(name, str) else name
        for i, e in enumerate(self.entries):
            if e[0] == want:
                return i, e
        return -1, None

    def by_off(self, off):
        for i, e in enumerate(self.entries):
            if e[2] == off:
                return i, e
        return -1, None

    def payload(self, e):
        self.f.seek(e[2])
        return self.f.read(e[3])

    def rels(self, e):
        """返回条目 payload 内的重定位槽相对偏移列表。"""
        self.f.seek(self.rel_off)
        vals = struct.unpack('<%dQ' % self.rel_cnt, self.f.read(self.rel_cnt * 8))
        off, size = e[2], e[3]
        return [v - off for v in vals if off <= v < off + size]


def cmd_info(pid):
    p = Proc(pid)
    # 模块基址：读 PEB 太绕，这里用 PSS 太慢；直接让调用者提供是不行 —— 用 toolhelp 简化
    # 改为通过 GetModuleHandle 不行（跨进程），用 EnumProcessModules 也可；这里只做基础读。
    print('opened pid=%d' % pid)
    p.close()


def fmt_f32(b, i):
    return struct.unpack_from('<f', b, i)[0]


def cmd_dump(pid, addr, ln, show_f32=False):
    p = Proc(pid)
    b = p.read(addr, ln)
    if not b:
        raise SystemExit('读取失败 %x' % addr)
    for o in range(0, len(b) - 7, 8):
        q = struct.unpack_from('<Q', b, o)[0]
        f = struct.unpack_from('<f', b, o)[0]
        g = struct.unpack_from('<f', b, o + 4)[0]
        print('  +0x%04x = 0x%016x  f=%g  (hi f=%g)' % (o, q, f, g))
    p.close()


def diff_mem(mem, blob, label, limit=60):
    n = min(len(mem), len(blob))
    diffs = 0
    print('-- %s: mem=%d bytes pack=%d bytes, 对比前 %d 字节' % (label, len(mem), len(blob), n))
    o = 0
    while o + 8 <= n:
        a = struct.unpack_from('<Q', mem, o)[0]
        bb = struct.unpack_from('<Q', blob, o)[0]
        if a != bb:
            diffs += 1
            if diffs <= limit:
                print('   +0x%04x mem=0x%016x pack=0x%016x' % (o, a, bb))
        o += 8
    print('-- %s: 差异 qword 数 = %d' % (label, diffs))
    return diffs


def cmd_cmp(pid, addr, packpath, entry):
    p = Proc(pid)
    pk = Pack(packpath)
    i, e = pk.by_name(entry)
    if e is None:
        raise SystemExit('pack 里找不到 %s' % entry)
    blob = pk.payload(e)
    mem = p.read(addr, len(blob))
    if not mem:
        raise SystemExit('内存读取失败 %x' % addr)
    diff_mem(mem, blob, '%s arch=%d off=0x%x size=%d' % (entry, e[1], e[2], e[3]))
    p.close()


def cmd_cmpunit(pid, clone_addr, leg_addr, packpath, entry):
    p = Proc(pid)
    pk = Pack(packpath)
    i, e = pk.by_name(entry)
    if e is None:
        raise SystemExit('pack 里找不到 %s' % entry)
    blob = pk.payload(e)
    leg_off = struct.unpack_from('<Q', blob, 0xC0)[0]
    li, le = pk.by_off(leg_off)
    print('MECH %s off=0x%x size=%d  +0xC0=0x%x -> %s' %
          (entry, e[2], e[3], leg_off, le[0].decode() if le else '?'))
    mem = p.read(clone_addr, len(blob))
    if mem:
        diff_mem(mem, blob, 'MECH 内存 @0x%x' % clone_addr)
    if le:
        lb = pk.payload(le)
        lm = p.read(leg_addr, len(lb))
        if lm:
            diff_mem(lm, lb, 'LEG 内存 @0x%x (%s)' % (leg_addr, le[0].decode()))
            # 速度字段
            for off, nm in ((4124, 'max_forward_speed'), (4128, 'max_side_speed'),
                            (4132, 'max_reverse_speed'), (4136, 'max_forward_accel')):
                print('   LEG+%d %s: mem=%g pack=%g' %
                      (off, nm, struct.unpack_from('<f', lm, off)[0],
                       struct.unpack_from('<f', lb, off)[0]))
        else:
            print('LEG 内存读取失败 0x%x' % leg_addr)
    else:
        print('MECH 内存读取失败 0x%x' % clone_addr)
    p.close()


def cmd_write(pid, addr, hx, yes):
    data = bytes.fromhex(hx)
    p = Proc(pid, write=True)
    old = p.read(addr, len(data))
    print('原值: %s' % (old.hex() if old else '(读取失败)'))
    if not yes:
        print('未加 --yes，不写入')
        p.close()
        return
    ok = p.write(addr, data)
    new = p.read(addr, len(data))
    print('写入%s，新值: %s' % ('成功' if ok else '失败', new.hex() if new else '(读取失败)'))
    p.close()


class MODULEINFO(ctypes.Structure):
    _fields_ = [('lpBaseOfDll', ctypes.c_void_p),
                ('SizeOfImage', wintypes.DWORD),
                ('EntryPoint', ctypes.c_void_p)]


psapi.EnumProcessModulesEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p),
                                       wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                       wintypes.DWORD]
psapi.GetModuleInformation.argtypes = [wintypes.HANDLE, ctypes.c_void_p,
                                       ctypes.POINTER(MODULEINFO), wintypes.DWORD]


def module_base(pid):
    access = PROCESS_QUERY_INFORMATION | PROCESS_VM_READ
    h = k32.OpenProcess(access, False, int(pid))
    if not h:
        raise SystemExit('module_base: OpenProcess 失败 err=%d' % ctypes.get_last_error())
    mods = (ctypes.c_void_p * 1024)()
    need = wintypes.DWORD(0)
    ok = psapi.EnumProcessModulesEx(h, mods, ctypes.sizeof(mods), ctypes.byref(need), LIST_MODULES_ALL)
    if not ok:
        k32.CloseHandle(h)
        raise SystemExit('EnumProcessModulesEx 失败 err=%d' % ctypes.get_last_error())
    mi = MODULEINFO()
    psapi.GetModuleInformation(h, mods[0], ctypes.byref(mi), ctypes.sizeof(mi))
    k32.CloseHandle(h)
    return mi.lpBaseOfDll or 0


def cmd_swap(pid, packpath, target, mech_hex, leg_hex, yes, preserve='0x3338,0x11a0'):
    """把目标载具的 MECH/LEG payload 灌进玩家克隆槽，重定位槽改写成运行时指针。"""
    p = Proc(pid, write=yes)
    pk = Pack(packpath)
    base = module_base(pid)
    root = p.q(base + OFF_RES_ROOT)
    pack_ptr = p.q(root + OFF_PACK_IN_ROOT) if root else None
    resarr = p.q(pack_ptr + 0x18) if pack_ptr else None
    print('base=0x%x root=0x%x pack=0x%x resarr=0x%x' %
          (base, root or 0, pack_ptr or 0, resarr or 0))

    ti, te = pk.by_name(target)
    if te is None:
        raise SystemExit('pack 里找不到目标 %s' % target)
    if te[1] != 14:
        raise SystemExit('目标 archetype=%d 不是 MECH' % te[1])
    mech = bytearray(pk.payload(te))
    leg_off = struct.unpack_from('<Q', mech, 0xC0)[0]
    li, le = pk.by_off(leg_off)
    if le is None or le[1] != 11:
        raise SystemExit('目标 +0xC0 不是 LEG: 0x%x' % leg_off)
    leg = bytearray(pk.payload(le))
    print('目标 %s (MECH %d) + LEG %s (%d)' % (target, te[3], le[0].decode(), le[3]))

    mech_rel = pk.rels(te)
    leg_rel = pk.rels(le)
    print('重定位槽: MECH %d 个 %s' % (len(mech_rel), ['0x%x' % r for r in mech_rel]))
    print('重定位槽: LEG  %d 个 %s' % (len(leg_rel), ['0x%x' % r for r in leg_rel]))

    unresolved = []

    def resolve(v):
        if not v:
            return 0
        idx, e = pk.by_off(v)
        if idx < 0:
            return None
        addr = p.q(resarr + idx * 8)
        return addr

    def patch(buf, rels, label):
        for r in rels:
            v = struct.unpack_from('<Q', buf, r)[0]
            addr = resolve(v)
            if addr is None:
                unresolved.append((label, r, v))
                continue
            struct.pack_into('<Q', buf, r, addr)
            print('  %s +0x%x: 0x%x -> 0x%x' % (label, r, v, addr or 0))

    patch(mech, mech_rel, 'MECH')
    patch(leg, leg_rel, 'LEG')
    if unresolved:
        print('!! 无法解析的重定位（偏移: 值）：')
        for label, r, v in unresolved:
            print('   %s +0x%x = 0x%x' % (label, r, v))
        if not yes:
            print('（dry-run，不写入）')
        return 3

    mech_addr = int(mech_hex, 16)
    leg_addr = int(leg_hex, 16)
    # 目标 MECH 的 LEG 指针固定指向克隆 LEG 槽
    struct.pack_into('<Q', mech, 0xC0, leg_addr)
    print('MECH+0xC0 -> 克隆 LEG 0x%x' % leg_addr)

    old_mech = p.read(mech_addr, len(mech))
    old_leg = p.read(leg_addr, len(leg))
    if old_mech is None or old_leg is None:
        raise SystemExit('读取克隆槽失败')
    print('克隆槽现有: MECH %d 字节 LEG %d 字节' % (len(old_mech), len(old_leg)))

    # 保留运行时写入的非重定位字段（如加载时赋的标记）
    for item in preserve.split(','):
        off = int(item.strip(), 0)
        if off + 8 <= len(mech) and off not in mech_rel:
            struct.pack_into('<Q', mech, off, struct.unpack_from('<Q', old_mech, off)[0])
            print('保留 MECH +0x%x = 0x%x' % (off, struct.unpack_from('<Q', old_mech, off)[0]))
        if off + 8 <= len(leg) and off not in leg_rel:
            struct.pack_into('<Q', leg, off, struct.unpack_from('<Q', old_leg, off)[0])
            print('保留 LEG  +0x%x = 0x%x' % (off, struct.unpack_from('<Q', old_leg, off)[0]))

    if not yes:
        print('（dry-run，未写入；加 --yes 执行）')
        p.close()
        return 0

    bak_dir = tempfile.gettempdir()
    open(os.path.join(bak_dir, 'bk_clone_mech.bin'), 'wb').write(old_mech)
    open(os.path.join(bak_dir, 'bk_clone_leg.bin'), 'wb').write(old_leg)
    print('已备份原克隆数据到 %s' % bak_dir)

    ok1 = p.write(leg_addr, bytes(leg))
    ok2 = p.write(mech_addr, bytes(mech))
    print('写入 LEG:%s  MECH:%s' % (ok1, ok2))
    chk = p.read(mech_addr + 0xC0, 8)
    print('校验 MECH+0xC0 = %s' % (chk.hex() if chk else '?'))
    p.close()
    return 0


def cmd_scanrefs(pid, ent_addr, ln, mech_addr, leg_addr, old_mech_bin, old_leg_bin, yes):
    """在实体记录里找“换类前的旧子资源指针”，可选替换为换类后的新指针。"""
    p = Proc(pid, write=yes)
    old_mech = open(old_mech_bin, 'rb').read()
    old_leg = open(old_leg_bin, 'rb').read()
    new_mech = p.read(mech_addr, len(old_mech))
    new_leg = p.read(leg_addr, len(old_leg))
    if not new_mech or not new_leg:
        raise SystemExit('读取克隆槽失败')

    def is_ptr(v):
        return 0x10000000000 <= v < 0x1000000000000

    pairs = {}
    for buf_old, buf_new, tag in ((old_mech, new_mech, 'mech'), (old_leg, new_leg, 'leg')):
        for off in range(0, min(len(buf_old), len(buf_new)) - 7, 8):
            o = struct.unpack_from('<Q', buf_old, off)[0]
            n = struct.unpack_from('<Q', buf_new, off)[0]
            if o != n and is_ptr(o) and is_ptr(n):
                pairs[o] = (n, '%s+0x%x' % (tag, off))
    print('旧->新 指针配对 %d 条' % len(pairs))

    buf = p.read(ent_addr, ln)
    if not buf:
        raise SystemExit('实体读取失败 0x%x' % ent_addr)
    hits = []
    for off in range(0, len(buf) - 7, 8):
        v = struct.unpack_from('<Q', buf, off)[0]
        if v in pairs:
            hits.append((off, v, pairs[v]))
    print('实体 0x%x 范围内命中 %d 处' % (ent_addr, len(hits)))
    for off, v, (n, tag) in hits:
        print('  ent+0x%-5x = 0x%x (%s) -> 0x%x' % (off, v, tag, n))
    if not hits:
        p.close()
        return 0
    if not yes:
        print('（dry-run，未写入；加 --yes 执行）')
        p.close()
        return 0
    for off, v, (n, tag) in hits:
        ok = p.write(ent_addr + off, struct.pack('<Q', n))
        print('  写入 ent+0x%x -> 0x%x %s' % (off, n, ok))
    p.close()
    return 0


def cmd_remapent(pid, ent_addr, ln, mech_addr, leg_addr, old_mech_bin, old_leg_bin, packpath, yes):
    """把实体记录里“指向旧子资源内部”的指针搬到新子资源的同偏移处。"""
    p = Proc(pid, write=yes)
    pk = Pack(packpath)
    base = module_base(pid)
    root = p.q(base + OFF_RES_ROOT)
    pack_ptr = p.q(root + OFF_PACK_IN_ROOT) if root else None
    resarr = p.q(pack_ptr + 0x18) if pack_ptr else None
    if not resarr:
        raise SystemExit('resarr 不可用')
    raw = p.read(resarr, pk.count * 8)
    if not raw:
        raise SystemExit('resarr 读取失败')
    addr2idx = {}
    for i in range(pk.count):
        a = struct.unpack_from('<Q', raw, i * 8)[0]
        if a:
            addr2idx[a] = i

    old_mech = open(old_mech_bin, 'rb').read()
    old_leg = open(old_leg_bin, 'rb').read()
    new_mech = p.read(mech_addr, len(old_mech))
    new_leg = p.read(leg_addr, len(old_leg))

    ranges = []   # (old_start, old_end, new_start, label)
    for buf_old, buf_new, tag in ((old_mech, new_mech, 'mech'), (old_leg, new_leg, 'leg')):
        for off in range(0, min(len(buf_old), len(buf_new)) - 7, 8):
            o = struct.unpack_from('<Q', buf_old, off)[0]
            n = struct.unpack_from('<Q', buf_new, off)[0]
            if o == n or o < 0x10000000000:
                continue
            idx = addr2idx.get(o)
            if idx is None:
                continue
            size = pk.entries[idx][3]
            ranges.append((o, o + size, n, '%s+0x%x (%s)' % (tag, off, pk.entries[idx][0].decode())))
    print('旧子资源区间 %d 个' % len(ranges))
    for r in ranges:
        print('  0x%x..0x%x -> 0x%x  %s' % r)

    buf = p.read(ent_addr, ln)
    if not buf:
        raise SystemExit('实体读取失败')
    hits = []
    for off in range(0, len(buf) - 7, 8):
        q = struct.unpack_from('<Q', buf, off)[0]
        for os_, oe, ns, label in ranges:
            if os_ <= q < oe:
                hits.append((off, q, ns + (q - os_), label, q - os_))
                break
    print('命中 %d 处' % len(hits))
    for off, q, nq, label, rel in hits:
        print('  ent+0x%-5x = 0x%x  ->  0x%x   %s +0x%x' % (off, q, nq, label, rel))
    if not hits:
        p.close()
        return 0
    if not yes:
        print('（dry-run，未写入；加 --yes 执行）')
        p.close()
        return 0
    for off, q, nq, label, rel in hits:
        ok = p.write(ent_addr + off, struct.pack('<Q', nq))
        print('  写入 ent+0x%x -> 0x%x %s' % (off, nq, ok))
    p.close()
    return 0


def cmd_strings(pid, addr, ln, minlen=4):
    """读取一段内存并列出其中的 ASCII 字符串（带偏移）。"""
    p = Proc(pid)
    b = p.read(addr, ln)
    if not b:
        raise SystemExit('读取失败')
    i = 0
    while i < len(b):
        c = b[i]
        if 0x20 <= c <= 0x7e:
            j = i
            while j < len(b) and 0x20 <= b[j] <= 0x7e:
                j += 1
            if j - i >= minlen:
                print('  +0x%x  %s' % (i, b[i:j].decode('ascii')))
            i = j
        else:
            i += 1
    p.close()


def cmd_res(pid, packpath, entry):
    """按资源名解析运行时资源地址，并打印其 LEG(+0xC0)。"""
    p = Proc(pid)
    pk = Pack(packpath)
    base = module_base(pid)
    root = p.q(base + OFF_RES_ROOT)
    pack_ptr = p.q(root + OFF_PACK_IN_ROOT) if root else None
    resarr = p.q(pack_ptr + 0x18) if pack_ptr else None
    i, e = pk.by_name(entry)
    if e is None:
        raise SystemExit('找不到条目 %s' % entry)
    addr = p.q(resarr + i * 8)
    print('idx=%d arch=%d size=%d addr=0x%x' % (i, e[1], e[3], addr or 0))
    if addr and e[1] == 14:
        leg = p.q(addr + 0xC0)
        print('leg=0x%x' % (leg or 0))
    p.close()


if __name__ == '__main__':
    a = sys.argv[1:]
    if not a:
        raise SystemExit(__doc__)
    cmd = a[0]
    if cmd == 'info':
        cmd_info(a[1])
    elif cmd == 'dump':
        cmd_dump(int(a[1]), int(a[2], 16), int(a[3], 0), '--f32' in a)
    elif cmd == 'cmp':
        cmd_cmp(int(a[1]), int(a[2], 16), a[3], a[4])
    elif cmd == 'cmpunit':
        cmd_cmpunit(int(a[1]), int(a[2], 16), int(a[3], 16), a[4], a[5])
    elif cmd == 'write':
        cmd_write(int(a[1]), int(a[2], 16), a[3], '--yes' in a)
    elif cmd == 'swap':
        cmd_swap(int(a[1]), a[2], a[3], a[4], a[5], '--yes' in a)
    elif cmd == 'scanrefs':
        cmd_scanrefs(int(a[1]), int(a[2], 16), int(a[3], 0), int(a[4], 16), int(a[5], 16),
                     a[6], a[7], '--yes' in a)
    elif cmd == 'remapent':
        cmd_remapent(int(a[1]), int(a[2], 16), int(a[3], 0), int(a[4], 16), int(a[5], 16),
                     a[6], a[7], a[8], '--yes' in a)
    elif cmd == 'strings':
        cmd_strings(int(a[1]), int(a[2], 16), int(a[3], 0))
    elif cmd == 'res':
        cmd_res(int(a[1]), a[2], a[3])
    else:
        raise SystemExit('未知命令: ' + cmd)
