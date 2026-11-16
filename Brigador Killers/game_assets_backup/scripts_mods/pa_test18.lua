-- pa_test18.lua — 尝试夺取 ffi
print("=== pa_test18: 解锁 ffi ===")

local function load_fn(name)
    local ok, f = pcall(package.loadlib, "pa_probe.dll", name)
    if ok and type(f) == "function" then return f end
    print("  !! 加载 " .. name .. " 失败: " .. tostring(f))
    return nil
end

local ffi = nil
local pa_ffi = load_fn("pa_ffi")
if pa_ffi then
    local ok, res = pcall(pa_ffi)
    print("pa_ffi ok=" .. tostring(ok) .. " type=" .. type(res))
    if ok and type(res) == "table" then ffi = res end
end

if not ffi then
    print("\n=== pa_ffi 未成功, 试备选: package.preload ===")
    print("  package.preload = " .. tostring(package.preload))
    if package.preload then
        for k, v in pairs(package.preload) do
            print("    preload." .. tostring(k) .. " = " .. type(v))
        end
    end
    print("\n结论: 需要换别的方式")
    return
end

print("\n*** 拿到 ffi 表 ***")
print("  ffi.C       = " .. tostring(ffi.C))
print("  ffi.new     = " .. tostring(ffi.new))
print("  ffi.cast    = " .. tostring(ffi.cast))
print("  ffi.sizeof  = " .. tostring(ffi.sizeof))

-- 冒烟测试: 分配内存 + 读写
local ok, err = pcall(function()
    local buf = ffi.new("int[1]", 12345)
    print("  int[1] 写入 12345, 读回 = " .. tostring(buf[0]))

    local f = ffi.new("float[2]")
    f[0] = 3.5; f[1] = -2.25
    print(string.format("  float[2] = %.2f, %.2f", f[0], f[1]))

    -- 读 exe 基址
    local pa_base = load_fn("pa_base")
    if pa_base then
        local base = pa_base()
        print(string.format("  exe base = 0x%X", base))
        -- 用 ffi 直接读 exe 头部 MZ 标志验证能否读进程内存
        local p = ffi.cast("uint8_t*", base)
        print(string.format("  读 exe 首字节: 0x%02X 0x%02X (应为 4D 5A = MZ)", p[0], p[1]))
    end
end)

if not ok then
    print("  !! ffi 冒烟测试失败: " .. tostring(err))
else
    print("\n=== ffi 完全可用! 后续所有内存操作都可以直接用 ffi ===")
end

-- 顺便试试 bit / os
print("\n--- 其他库 ---")
for _, nm in ipairs({"pa_bit", "pa_os", "pa_io"}) do
    local fn = load_fn(nm)
    if fn then
        local ok2, res2 = pcall(fn)
        print(string.format("  %s -> %s %s", nm, type(res2), ok2 and tostring(res2 ~= nil) or tostring(res2)))
    end
end
