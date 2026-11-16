-- pa_test20.lua — 用 ff i + 特征坐标反查 MoveTo 目标字段
-- 不需要重新编译 DLL, 纯 Lua
local function load_fn(name)
    local ok, f = pcall(package.loadlib, "pa_probe.dll", name)
    if ok and type(f) == "function" then return f end
    return nil
end

local ffi = load_fn("pa_ffi")()
local pa_ptr = load_fn("pa_ptr")
local io_lib = load_fn("pa_io")()

ffi.cdef[[
typedef struct {
    void   *BaseAddress;
    void   *AllocationBase;
    uint32_t AllocationProtect;
    uint32_t __pad0;
    uint64_t RegionSize;
    uint32_t State;
    uint32_t Protect;
    uint32_t Type;
    uint32_t __pad1;
} MEMORY_BASIC_INFORMATION;

void *VirtualQuery(void *lpAddress, MEMORY_BASIC_INFORMATION *lpBuffer, uint64_t dwLength);
]]

local out = {}
local function rec(s) out[#out + 1] = s end

-- 检查 [addr, addr+size) 是否整段可读
local function readable(addr, size)
    local mbi = ffi.new("MEMORY_BASIC_INFORMATION")
    local cur = addr
    local enda = addr + size
    for _ = 1, 64 do
        local r = ffi.C.VirtualQuery(ffi.cast("void*", cur), mbi, ffi.sizeof(mbi))
        if r == nil then return false end
        local st = tonumber(mbi.State)
        local pr = tonumber(mbi.Protect)
        if st ~= 0x1000 then return false end          -- 未提交
        if pr == 0x01 or pr == 0x10 then return false end -- NOACCESS / EXECUTE
        if pr >= 0x100 then return false end            -- GUARD
        local base = tonumber(ffi.cast("uint64_t", mbi.BaseAddress))
        local rsize = tonumber(mbi.RegionSize)
        local region_end = base + rsize
        if region_end >= enda then return true end
        cur = region_end
        if cur == 0 then return false end
    end
    return false
end

local function find_floats(addr, size, targets)
    local hits = {}
    if not readable(addr, size) then
        rec(string.format("  [skip] 0x%X+0x%X 不可读", addr, size))
        return hits
    end
    local p = ffi.cast("uint8_t*", addr)
    for off = 0, size - 8, 4 do
        local ok, uv = pcall(function() return ffi.cast("float*", p + off)[0] end)
        if ok and uv ~= nil then
            local f = tonumber(uv)
            if f ~= nil then
                for _, t in ipairs(targets) do
                    if math.abs(f - t.v) < 1e-3 then
                        hits[#hits + 1] = { off = off, v = f, name = t.name }
                    end
                end
            end
        end
    end
    return hits
end

local real = Mech.GetPlayer()
local rx, ry = real:GetPosition()
local face = real:GetOrient() or 0
rec(string.format("玩家 (%.2f, %.2f)", rx, ry))

local VIC = "assets/data/vics/units/rig_volta_carmine_01.json"
local fake = Mech.Create(VIC, Vec2.New(rx + 6, ry + 6), face, 0, 0)
if not fake then rec("!! fake 创建失败") return end

-- 特征小数 + 玩家附近偏移: 3 位小数, 撞车概率极低
local TX, TY = rx + 7.12340, ry + 7.56780
local ok, err = pcall(function() fake:MoveTo(Vec2.New(TX, TY)) end)
if not ok or not err then
    rec("!! MoveTo 失败 ok=" .. tostring(ok) .. " err=" .. tostring(err))
end
rec(string.format("fake MoveTo (%.4f, %.4f)", TX, TY))

local mp = pa_ptr(fake)
rec(string.format("fake mech* = 0x%X", mp))

local targets = {
    { name = "TX", v = TX },
    { name = "TY", v = TY },
}

rec("\n=== 扫 mech 0x0000~0x2000 ===")
local hits = find_floats(mp, 0x2000, targets)
if #hits == 0 then
    rec("  未命中")
else
    for _, h in ipairs(hits) do
        rec(string.format("  +0x%04X = %.2f (%s)", h.off, h.v, h.name))
    end
end

-- 若命中, 把命中点附近 64 字节 dump 出来
if #hits > 0 then
    local p = ffi.cast("uint8_t*", mp)
    for _, h in ipairs(hits) do
        local start = math.max(0, h.off - 32)
        local chunk = {}
        for i = 0, 64, 4 do
            local okf, fv = pcall(function() return ffi.cast("float*", p + start + i)[0] end)
            local oki, iv = pcall(function() return ffi.cast("int32_t*", p + start + i)[0] end)
            fv = okf and tonumber(fv) or 0
            iv = oki and tonumber(iv) or 0
            chunk[#chunk + 1] = string.format("+%03X f=%.4g i=%d", start + i, fv, iv)
        end
        rec(string.format("  周围 (基准 +0x%04X):", h.off))
        rec("    " .. table.concat(chunk, "\n    "))
    end
end

-- 若 mech 内没命中, 试 AI 指针 (+0x720) 指向的对象
rec("\n=== mech 未命中则扫 AI 对象 ===")
local p = ffi.cast("uint8_t*", mp)
local aiptr_uv = ffi.cast("uint64_t*", p + 0x720)[0]
local aiptr = tonumber(aiptr_uv) or 0
rec(string.format("  mech+0x720 = 0x%X", aiptr))
if aiptr ~= 0 and readable(aiptr, 0x400) then
    local h2 = find_floats(aiptr, 0x400, targets)
    if #h2 == 0 then rec("  AI 对象未命中") else
        for _, h in ipairs(h2) do
            rec(string.format("  AI+0x%04X = %.2f (%s)", h.off, h.v, h.name))
        end
    end
else
    rec("  AI 指针无效或不可读")
end

-- 落盘
local body = table.concat(out, "\n")
print(">>> 结果已写入 pa_test20_result.txt")
if io_lib and io_lib.open then
    local f = io_lib.open("pa_test20_result.txt", "w")
    if f then f:write(body); f:close() end
end
print(">>> HIT_COUNT=" .. tostring(#hits))
