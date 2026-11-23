# -*- coding: utf-8 -*-
"""把序列化端抽取结果整理成 点分字段 -> 偏移 的映射表，并用 pack + 导出 JSON 校验。"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import packpatch as P

WHEEL = {'track', 'offset_from_origin', 'friction_coefficient', 'cornering_stiffness',
         'handbrake_friction_coefficient', 'handbrake_cornering_stiffness',
         'powered', 'size'}
TOP = {'size', 'height', 'path_radius', 'destroyed_height'}
# 结构体里存弧度，JSON 输出为度
DEG = {'min_angular_velocity', 'max_angular_velocity', 'max_steering_angle'}


def flat_json(o, prefix=''):
    out = {}
    if isinstance(o, dict):
        for k, v in o.items():
            out.update(flat_json(v, prefix + '.' + k if prefix else k))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            out.update(flat_json(v, prefix + '[%d]' % i))
    else:
        out[prefix] = o
    return out


def main(raw_map, json_path, asset, pack, out_path):
    raw = json.load(open(raw_map, encoding='utf-8'))
    fields = {}
    for k, v in raw.items():
        o = int(v['offset'], 16)
        if k in WHEEL and k != 'size':
            fields['vehicle_data.front_wheel_data.' + k] = {'offset': o - 0x20, 'kind': v['kind']}
            fields['vehicle_data.rear_wheel_data.' + k] = {'offset': o, 'kind': v['kind']}
        elif k in TOP:
            fields[k] = {'offset': o, 'kind': v['kind']}
        else:
            kind = v['kind']
            if k in DEG:
                kind = 'f32_deg'
            fields['vehicle_data.' + k] = {'offset': o, 'kind': kind}

    # 补上实测确认的字段
    fields['vehicle_data.front_wheel_data.size'] = {'offset': 0x1078, 'kind': 'f32'}
    fields['vehicle_data.rear_wheel_data.size'] = {'offset': 0x1098, 'kind': 'f32'}

    # 校验
    f = open(pack, 'rb')
    count, a, b, c, d = P.table_layout(f)
    idx = P.find_index(f, count, a, asset)
    arch, off, size = P.entry_info(f, idx, b, c, d)
    f.seek(off)
    data = f.read(size)
    js = flat_json(json.load(open(json_path, encoding='utf-8')))
    ok = bad = 0
    for path, meta in fields.items():
        if path not in js:
            continue
        o = meta['offset']
        if meta['kind'] == 'f32':
            got = struct.unpack_from('<f', data, o)[0]
            good = abs(got - float(js[path])) < 1e-4
        elif meta['kind'] == 'f32_deg':
            got = struct.unpack_from('<f', data, o)[0]
            good = abs(got - float(js[path]) * 3.141592653589793 / 180.0) < 1e-4
        else:
            got = struct.unpack_from('<i', data, o)[0]
            good = int(got) == int(bool(js[path]) if isinstance(js[path], bool) else js[path])
        if good:
            ok += 1
        else:
            bad += 1
            print('MISMATCH %-48s off=0x%x json=%r got=%r' % (path, o, js[path], got))
    covered = sum(1 for k in js if k in fields)
    print('verified=%d mismatch=%d json_leaves=%d covered=%d uncovered=%d'
          % (ok, bad, len(js), covered, len(js) - covered))
    doc = {'asset': asset, 'archetype': arch, 'struct_size': size,
           'verified': ok, 'mismatch': bad, 'fields': fields}
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(doc, open(out_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('map ->', out_path)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
