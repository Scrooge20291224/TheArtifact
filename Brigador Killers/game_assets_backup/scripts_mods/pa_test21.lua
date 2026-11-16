-- pa_test21.lua — 验证 MoveTo 目标字段是不是活的
local function load_fn(name)
    local ok, f = pcall(package.loadlib, "pa_probe.dll", name)
    if ok and type(f) == "function" then return f end
    return nil
end

local ffi = load_fn("pa_ffi")()
local pa_ptr = load_fn("pa_ptr")
local io_lib = load_fn("pa_io")()

local function writable(addr, size)
    local MEM_COMMIT = 0x1000
    local PAGE_GUARD = 0x100
    local PAGE_NOACCESS = 0x01
    local MEMORY_BASIC_INFORMATION = ffi.typeof[[
        struct {
            void*   BaseAddress;
            void*   AllocationBase;
            uint32_t AllocationProtect;
            uint32_t __pad0;
            uint64_t RegionSize;
            uint32_t State;
            uint32_t Protect;
            uint32_t Type;
            uint32_t __pad1;
        }
    ]]
    local mbi = ffi.new(MEMORY_BASIC_INFORMATION)
    local cur = ffi.cast("uint64_t", addr)
    local enda = cur + size
    for _ = 1, 64 do
        local r = ffi.C.VirtualQuery(ffi.cast("void*", cur), mbi, ffi.sizeof(mbi))
        if r == nil then return false end
        local st = tonumber(mbi.State)
        local pr = tonumber(mbi.Protect)
        if st ~= MEM_COMMIT then return false end
        if pr == PAGE_NOACCESS or pr == 0x10 then return false end
        if pr >= PAGE_GUARD then return false end
        local base = tonumber(ffi.cast("uint64_t", mbi.BaseAddress))
        local rsize = tonumber(mbi.RegionSize)
        if base + rsize >= enda then return true end
        cur = base + rsize
        if cur == 0 then return false end
    end
    return false
end

local function write_f32(ptr, off, v)
    if not writable(ptr + off, 4) then return false, "不可写" end
    ffi.cast("float*", ptr + off)[0] = v
    return true
end

local out = {}
local function rec(s) out[#out + 1] = s; print(s) end

ffi.cdef[[
typedef struct { int32_t __unused; } __never_used;
void *VirtualQuery(void *lpAddress, void *lpBuffer, uint64_t dwLength);
]]

local real = Mech.GetPlayer()
local rx, ry = real:GetPosition()
rec(string.format("玩家 (%.2f, %.2f)", rx, ry))

local VIC = "assets/data/vics/units/rig_volta_carmine_01.json"
local fake = Mech.Create(VIC, Vec2.New(rx + 6, ry + 6), real:GetOrient() or 0, 0, 0)
if not fake then rec("!! fake 创建失败"); return end

-- 旧目标 (用 MoveTo 设)
local OLD_X, OLD_Y = rx + 50, ry
fake:MoveTo(Vec2.New(OLD_X, OLD_Y))
rec(string.format("Phase 1: MoveTo (%.2f, %.2f), 等 1.5 秒...", OLD_X, OLD_Y))

local mp = pa_ptr(fake)
rec(string.format("mech* = 0x%X", mp))

-- 等一会让 fake 开始移动
for i = 1, 150000 do end  -- Lua 忙等 ~= 1.5 秒 (粗糙但无依赖)

local p = ffi.cast("uint8_t*", mp)

-- 读 MoveTo 写入的目标字段
local function read_vec2(off)
    local x = tonumber(ffi.cast("float*", p + off)[0]) or 0
    local y = tonumber(ffi.cast("float*", p + off + 4)[0]) or 0
    return x, y
end

local function pack_vec2(off)
    local x, y = read_vec2(off)
    return { x = x, y = y }
end

local before = {
    ["+0x0188"] = pack_vec2(0x0188),
    ["+0x0E00"] = pack_vec2(0x0E00),
    ["+0x1180"] = pack_vec2(0x1180),
    ["+0x1188"] = pack_vec2(0x1188),
}

rec("\n=== Phase 1 结束, AI 仍在跑 ===")
for name, v in pairs(before) do
    rec(string.format("  %s = (%.2f, %.2f)", name, v.x, v.y))
end
local bx, by = fake:GetPosition()
rec(string.format("  fake 实际位置 = (%.2f, %.2f)", bx, by))

-- DisableAI
rec("\n=== Phase 2: DisableAI, 手动改目标 ===")
fake:DisableAI()

-- 新目标 (明显不同)
local NEW_X = rx - 20
local NEW_Y = ry + 20

local edits = {
    { ["+0x0188"] = 0x0188 },
    { ["+0x0E00"] = 0x0E00 },
    { ["+0x1180"] = 0x1180 },
    { ["+0x1188"] = 0x1188 },
}

for _, e in ipairs(edits) do
    for name, off in pairs(e) do
        local ok1, err1 = write_f32(mp, off, NEW_X)
        local ok2, err2 = write_f32(mp, off + 4, NEW_Y)
        rec(string.format("  写 %s = (%.2f, %.2f) ok=%s,%s", name, NEW_X, NEW_Y, ok1, ok2))
    end
end

rec(string.format("\n  等 2 秒看 fake 会不会改方向往 (%.2f, %.2f)...", NEW_X, NEW_Y))
for i = 1, 200000 do end

local ax, ay = fake:GetPosition()
rec(string.format("  fake 位置 = (%.2f, %.2f)", ax, ay))

-- 诊断: 现在字段是什么
local after = {
    ["+0x0188"] = pack_vec2(0x0188),
    ["+0x0E00"] = pack_vec2(0x0E00),
    ["+0x1180"] = pack_vec2(0x1180),
    ["+0x1188"] = pack_vec2(0x1188),
}
rec("\n=== 改后字段 ===")
for name, v in pairs(after) do
    rec(string.format("  %s = (%.2f, %.2f) 目标 (%.2f, %.2f)", name, v.x, v.y, NEW_X, NEW_Y))
end

-- 落盘
local body = table.concat(out, "\n")
print(">>> 结果已写入 pa_test21_result.txt")
if io_lib and io_lib.open then
    local f = io_lib.open("pa_test21_result.txt", "w")
    if f then f:write(body); f:close() end
end
