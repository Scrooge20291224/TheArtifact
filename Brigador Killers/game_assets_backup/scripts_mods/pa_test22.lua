-- pa_test22.lua — 搜 exe 里 Player_Action 的 xref
local function load_fn(name)
    local ok, f = pcall(package.loadlib, "pa_probe.dll", name)
    if ok and type(f) == "function" then return f end
    return nil
end

local ffi = load_fn("pa_ffi")()
local pa_base = load_fn("pa_base")()
local io_lib = load_fn("pa_io")()

ffi.cdef[[
void *VirtualQuery(void *lpAddress, void *lpBuffer, uint64_t dwLength);
]]

local out = {}
local function rec(s) out[#out + 1] = s; print(s) end

local BASE = pa_base
rec(string.format("exe base = 0x%X", BASE))

-- MEMORY_BASIC_INFORMATION 简化
local MBIType = ffi.typeof[[
    struct {
        void*    BaseAddress;
        void*    AllocationBase;
        uint32_t AllocationProtect;
        uint32_t __p0;
        uint64_t RegionSize;
        uint32_t State;
        uint32_t Protect;
        uint32_t Type;
        uint32_t __p1;
    }
]]

-- 把字符串转成字节序列
local function str_to_bytes(s)
    local bytes = {}
    for i = 1, #s do bytes[#bytes + 1] = string.byte(s, i) end
    return bytes
end

-- 扫可读的 .text / .rdata 段
local regions = {}
local cur = BASE
for i = 1, 128 do
    local mbi = ffi.new(MBIType)
    local r = ffi.C.VirtualQuery(ffi.cast("void*", cur), mbi, ffi.sizeof(mbi))
    if r == nil then break end
    local st = tonumber(mbi.State)
    local pr = tonumber(mbi.Protect)
    local tp = tonumber(mbi.Type)
    local base = tonumber(ffi.cast("uint64_t", mbi.BaseAddress))
    local rsize = tonumber(mbi.RegionSize)

    if st == 0x1000 and rsize > 0x1000 and rsize < 0x2000000 then
        regions[#regions + 1] = { base = base, size = rsize, protect = pr }
    end
    cur = base + rsize
    if cur < base then break end
end

rec("=== 可搜索的内存段 ===")
for _, r in ipairs(regions) do
    rec(string.format("  0x%X ~ 0x%X  size=0x%X prot=0x%X", r.base, r.base + r.size, r.size, r.protect))
end

-- 在所有段里找字符串（大小写敏感，ASCII / UTF-8）
local NEEDLES = {
    "Player_Action",
    "Gun_Windup",
    "ejector",
    "Vehicle_Filter",
    "Lateral distance",
    "GetPlayer",
}

local function mem_search(base, size, pattern)
    local pat_bytes = str_to_bytes(pattern)
    local plen = #pat_bytes
    if plen == 0 or plen > size then return nil end
    local p = ffi.cast("uint8_t*", base)
    for i = 0, size - plen do
        local match = true
        for j = 1, plen do
            local ok, b = pcall(function() return p[i + j - 1] end)
            if not ok or tonumber(b) ~= pat_bytes[j] then match = false; break end
        end
        if match then return base + i end
    end
    return nil
end

local needle_results = {}
for _, n in ipairs(NEEDLES) do
    rec(string.format("\n--- 搜 %q ---", n))
    local hits = {}
    for _, r in ipairs(regions) do
        local addr = mem_search(r.base, r.size, n)
        while addr do
            local hit = { addr = addr, rva = addr - BASE }
            hits[#hits + 1] = hit
            rec(string.format("  found at 0x%X (RVA 0x%X)", addr, addr - BASE))
            -- 在同一 region 内继续搜, 跳过刚找到的
            local next_addr = mem_search(addr + 1, r.base + r.size - addr - 1, n)
            if not next_addr then break end
            addr = next_addr
        end
    end
    needle_results[n] = hits
end

rec("\n=== 结果汇总 ===")
for n, hits in pairs(needle_results) do
    rec(string.format("%-20s : %d hits", n, #hits))
    for _, h in ipairs(hits) do
        rec(string.format("  RVA 0x%X", h.rva))
    end
end

-- 落盘
local body = table.concat(out, "\n")
print(">>> 结果已写入 pa_test22_result.txt")
if io_lib and io_lib.open then
    local f = io_lib.open("pa_test22_result.txt", "w")
    if f then f:write(body); f:close() end
end
