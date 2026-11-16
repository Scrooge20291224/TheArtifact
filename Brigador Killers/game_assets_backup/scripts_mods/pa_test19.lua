-- pa_test19.lua — ffi 最终判定, 只输出一行 + 落盘
local function load_fn(name)
    local ok, f = pcall(package.loadlib, "pa_probe.dll", name)
    if ok and type(f) == "function" then return f end
    return nil
end

local lines = {}
local function rec(s)
    lines[#lines + 1] = s
    print(s)
end

local result = {}
local ok_all = true

-- 1. 拿 ffi
local ffi = nil
local pa_ffi = load_fn("pa_ffi")
if pa_ffi then
    local ok, res = pcall(pa_ffi)
    if ok and type(res) == "table" then ffi = res end
end
result.ffi_table = (ffi ~= nil)
if not ffi then ok_all = false end

-- 2. 拿 io (用于落盘)
local io_lib = nil
local pa_io = load_fn("pa_io")
if pa_io then
    local ok, res = pcall(pa_io)
    if ok and type(res) == "table" then io_lib = res end
end

if ffi then
    -- 3. 冒烟: 数字数组
    local ok, err = pcall(function()
        local b = ffi.new("int[1]", 12345)
        result.int_read = b[0]
        if b[0] ~= 12345 then error("int 读写不一致") end

        local f2 = ffi.new("float[2]")
        f2[0] = 3.5; f2[1] = -2.25
        result.float_read = f2[0] .. "," .. f2[1]

        -- 4. 读 exe 内存
        local pa_base = load_fn("pa_base")
        if pa_base then
            local base = pa_base()
            result.base = string.format("0x%X", base)
            local p = ffi.cast("uint8_t*", base)
            result.mz = string.format("%02X%02X", p[0], p[1])
            if p[0] ~= 0x4D or p[1] ~= 0x5A then error("exe 头不是 MZ") end
        end

        -- 5. 试着给 cdef 定义结构 (后续要用)
        ffi.cdef[[
            typedef struct { float x, y; } pa_vec2;
        ]]
        local v = ffi.new("pa_vec2")
        v.x = 1.5; v.y = -3.5
        result.cdef = string.format("%.1f,%.1f", v.x, v.y)
    end)
    if not ok then
        ok_all = false
        result.smoke_err = tostring(err)
    end
end

-- 输出到文件
local dump = {}
for k, v in pairs(result) do
    dump[#dump + 1] = k .. "=" .. tostring(v)
end
local body = table.concat(dump, "\n") .. "\nFFI_ALL_OK=" .. tostring(ok_all) .. "\n"

if io_lib and io_lib.open then
    local f = io_lib.open("pa_test19_result.txt", "w")
    if f then
        f:write(body)
        f:close()
        rec("已落盘 pa_test19_result.txt")
    else
        rec("io.open 失败")
    end
else
    rec("io 不可用")
end

-- 控制台只打一行
print(">>> FFI_ALL_OK=" .. tostring(ok_all))
