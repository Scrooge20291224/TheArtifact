# 自动生成 Proxy DLL 的 .def 转发文件
# 用法: python gen_def.py <原始DLL路径> <输出.def路径> <重命名的原始DLL名>
# 例如: python gen_def.py "C:\...\SDL2.dll" proxy.def SDL2_orig.dll

import sys
import pefile

if len(sys.argv) < 4:
    print(f"用法: {sys.argv[0]} <原始DLL> <输出.def> <重命名原名>")
    sys.exit(1)

orig_dll = sys.argv[1]
out_def = sys.argv[2]
rename = sys.argv[3]

p = pefile.PE(orig_dll)
exports = p.DIRECTORY_ENTRY_EXPORT.symbols

with open(out_def, "w") as f:
    f.write("LIBRARY SDL2\n")
    f.write("EXPORTS\n")
    for sym in exports:
        if sym.name:
            name = sym.name.decode()
            ordinal = sym.ordinal
            # 格式: FunctionName = rename.FunctionName @ordinal
            f.write(f"  {name} = {rename}.{name} @{ordinal}\n")

print(f"已生成 {out_def}，{len(exports)} 个转发导出")
