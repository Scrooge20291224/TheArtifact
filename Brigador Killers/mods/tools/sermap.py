# -*- coding: utf-8 -*-
"""从引擎序列化函数抽取 字段名 -> 结构体偏移（比反序列化端更规整）。

序列化模式：
    movss xmm2, [base+off]   /  movzx r8d, byte [base+off]  /  mov rcx, [base+off]
    lea rdx, [rip+key]
    call  json_set_float / json_set_int / json_set_string
嵌套对象：
    lea r8, [base+off]  (或 rdx)
    lea r9/rdx, [rip+key]
    call <子序列化函数>
"""
import json
import re
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP, X86_INS_LEA, X86_INS_CALL

EXE = r'c:\Program Files (x86)\Steam\steamapps\common\Brigador Killers\brigadorkillers.exe'
SER_ROOT = {'LEG': 0x140219270, 'CHASSIS': 0x140214940, 'MECH': 0x1402198E0}
SET_FLOAT = {0x1401fdc70, 0x1401fd340}
SET_STR = {0x1401fdc80, 0x1401fe080}
SET_BOOL = {0x1401fd500}
SET_INT = {0x1401fd4c0}


class Exe:
    def __init__(self, path):
        self.pe = pefile.PE(path)
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.data = open(path, 'rb').read()
        self.secs = [(s.VirtualAddress, s.PointerToRawData, s.Misc_VirtualSize)
                     for s in self.pe.sections]
        self.funcs = sorted((self.base + e.struct.BeginAddress,
                             self.base + e.struct.EndAddress)
                            for e in self.pe.DIRECTORY_ENTRY_EXCEPTION)
        self.md = Cs(CS_ARCH_X86, CS_MODE_64)
        self.md.detail = True

    def off(self, va):
        rva = va - self.base
        for sva, raw, size in self.secs:
            if sva <= rva < sva + size:
                return raw + (rva - sva)
        return None

    def cstr(self, va):
        o = self.off(va)
        if o is None:
            return None
        m = re.match(rb'[A-Za-z_][A-Za-z0-9_]{1,63}\x00', self.data[o:o + 65])
        return m.group()[:-1].decode() if m else None

    def frange(self, va):
        lo, hi = 0, len(self.funcs) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            b, e = self.funcs[mid]
            if va < b:
                hi = mid - 1
            elif va >= e:
                lo = mid + 1
            else:
                return b, e
        return None

    def dis(self, va):
        r = self.frange(va)
        if not r:
            return []
        b, e = r
        o = self.off(b)
        return list(self.md.disasm(self.data[o:o + (e - b)], b))


def is_serializer(exe, va):
    ins = exe.dis(va)
    return any(x.mnemonic == 'call' and x.operands[0].type == X86_OP_IMM
               and x.operands[0].imm in SET_FLOAT for x in ins)


def struct_base_reg(ins):
    from collections import Counter
    c = Counter()
    for x in ins:
        if x.mnemonic in ('movss', 'mov', 'movzx', 'movsxd', 'movsx'):
            for op in x.operands:
                if op.type == X86_OP_MEM and op.mem.base not in (0, X86_REG_RIP):
                    c[x.reg_name(op.mem.base)] += 1
    return c.most_common(1)[0][0] if c else None


def extract(exe, fva, cache, depth=0):
    if fva in cache:
        return cache[fva]
    cache[fva] = {}
    ins = exe.dis(fva)
    if not ins:
        return {}
    base_reg = struct_base_reg(ins)
    loads = []      # [(idx, disp, kind)] 最近的字段读取
    keys = []       # [(idx, key)]
    out = {}
    for i, x in enumerate(ins):
        # 字段读取
        if x.mnemonic in ('movss', 'mov', 'movzx', 'movsxd', 'movsx') and len(x.operands) >= 2 \
                and x.operands[1].type == X86_OP_MEM:
            m = x.operands[1].mem
            if m.base not in (0, X86_REG_RIP) and base_reg and x.reg_name(m.base) == base_reg:
                kind = 'f32' if x.mnemonic == 'movss' else ('i32' if x.mnemonic in ('movsxd', 'movsx', 'movzx') else 'i32')
                loads.append((i, m.disp, kind))
        if x.mnemonic == 'lea' and len(x.operands) == 2 and x.operands[1].type == X86_OP_MEM \
                and x.operands[1].mem.base == X86_REG_RIP:
            t = x.address + x.size + x.operands[1].mem.disp
            s = exe.cstr(t)
            if s:
                keys.append((i, s))
        if x.mnemonic in ('call', 'jmp') and x.operands[0].type == X86_OP_IMM:
            t = x.operands[0].imm
            key = next((k for j, k in reversed(keys) if i - j <= 6), None)
            if key is None:
                continue
            if t in SET_FLOAT or t in SET_INT or t in SET_BOOL or t in SET_STR:
                ld = next((l for l in reversed(loads) if i - l[0] <= 6), None)
                if ld:
                    # 字符串字段：lea r8,[base+off] 指向字符串对象
                    if t in SET_STR:
                        for y in reversed(ins[max(0, i - 6):i]):
                            if y.mnemonic == 'lea' and len(y.operands) == 2 and \
                                    y.operands[1].type == X86_OP_MEM and \
                                    y.operands[1].mem.base not in (0, X86_REG_RIP) and \
                                    y.operands[0].type == X86_OP_MEM is False:
                                reg = y.reg_name(y.operands[0].reg)
                                if reg in ('r8', 'r9'):
                                    out[key] = (y.operands[1].mem.disp, 'str')
                                    break
                        else:
                            out[key] = (ld[1], 'str')
                        continue
                    out[key] = (ld[1], ld[2])
            else:
                if depth < 4 and is_serializer(exe, t):
                    sub = extract(exe, t, cache, depth + 1)
                    disp = None
                    for y in reversed(ins[max(0, i - 8):i]):
                        if y.mnemonic == 'lea' and len(y.operands) == 2 and \
                                y.operands[1].type == X86_OP_MEM and \
                                y.operands[1].mem.base not in (0, X86_REG_RIP):
                            disp = y.operands[1].mem.disp
                            break
                    if disp is not None:
                        out[key] = (disp, 'obj', sub)
    cache[fva] = out
    return out


def flatten(tree, pre=''):
    res = {}
    for k, v in tree.items():
        if v[1] == 'obj':
            for kk, vv in flatten(v[2], k + '.').items():
                res[kk] = (v[0] + vv[0],) + vv[1:]
        else:
            res[k] = (v[0], v[1])
    return res


if __name__ == '__main__':
    exe = Exe(EXE)
    arch = sys.argv[1] if len(sys.argv) > 1 else 'LEG'
    tree = extract(exe, SER_ROOT[arch], {})
    flat = flatten(tree)
    out = {k: {'offset': hex(v[0]), 'kind': v[1]} for k, v in sorted(flat.items(), key=lambda kv: kv[1][0])}
    print(json.dumps(out, indent=1, ensure_ascii=False))
    if len(sys.argv) > 2:
        json.dump(out, open(sys.argv[2], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
