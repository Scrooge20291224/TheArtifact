-- pa_test23.lua — 扫 .text 找对 Player_Action 等字符串的 RIP-relative xref
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
local TEXT_BASE = BASE + 0x1000
local TEXT_SIZE = 0x3AA000

rec(string.format(".text 0x%X +0x%X", TEXT_BASE, TEXT_SIZE))

local TARGETS = {
    { name = "Player_Action",    rva = 0x3ACBA8 },
    { name = "Gun_Windup",      rva = 0x3ACBD8 },
    { name = "ejector",         rva = 0x3ACBE8 },
}

local p = ffi.cast("uint8_t*", TEXT_BASE)

for _, t in ipairs(TARGETS) do
    rec(string.format("\n=== %s (RVA 0x%X) ===", t.name, t.rva))

    -- 小端 4 字节 (LuaJIT 无内置 & 位运算, 用算术)
    local lb = t.rva % 4294967296
    local b1 = lb % 256
    local b2 = math.floor(lb / 256) % 256
    local b3 = math.floor(lb / 65536) % 256
    local b4 = math.floor(lb / 16777216) % 256

    local count = 0
    for i = 0, TEXT_SIZE - 8 do
        local ok, v0 = pcall(function() return tonumber(p[i]) end)
        if not ok then break end
        if v0 == b1 then
            local v1 = tonumber(p[i+1]) or 0
            local v2 = tonumber(p[i+2]) or 0
            local v3 = tonumber(p[i+3]) or 0
            if v1 == b2 and v2 == b3 and v3 == b4 then
                -- 扫到一处 disp32 四字节 (小端 = rva)
                -- 尝试 6..10 字节长的指令, disp 在末尾 4 字节
                for instr_len = 6, 10 do
                    local instr_start = i - (instr_len - 4)
                    if instr_start >= 0 then
                        local real_pc = TEXT_BASE + instr_start + instr_len
                        local disp32 = tonumber(ffi.cast("int32_t*", p + i)[0])
                        local va = real_pc + disp32
                        local rva = va - BASE
                        if rva == t.rva then
                            -- 完美命中!
                            local opcs = {}
                            for k = -instr_len + 4, 3 do
                                local b = tonumber(p[i + k]) or 0
                                opcs[#opcs + 1] = string.format("%02X", b)
                            end
                            rec(string.format("  *** 命中! text+0x%04X len=%d opc=%s disp=%d",
                                instr_start, instr_len, table.concat(opcs, " "), disp32))
                            count = count + 1
                            break
                        end
                    end
                end
            end
        end
    end
    if count == 0 then rec("  未找到 RIP-relative 引用") end
end

local body = table.concat(out, "\n")
print(">>> 写入 pa_test23_result.txt")
if io_lib and io_lib.open then
    local f = io_lib.open("pa_test23_result.txt", "w")
    if f then f:write(body); f:close() end
end
