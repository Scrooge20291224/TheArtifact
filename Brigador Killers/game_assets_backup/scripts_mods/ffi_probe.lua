-- 探测：引擎实际加载了哪些 Lua 库（不 require ffi）
local function probe(name)
    local ok, lib = pcall(require, name)
    if ok then
        print(string.format("OK  require('%s') = %s", name, tostring(lib)))
        return lib
    else
        print(string.format("MISS require('%s') = %s", name, tostring(lib)))
        return nil
    end
end

print("=== 引擎 Lua 库探测 ===")
local libs = {
    "ffi","jit","jit.opt","jit.util",
    "io","os","debug","coroutine",
    "table","string","math","bit",
    "string.buffer","bit32","luajit",
    "filesystem" -- 引擎可能有自定义 FS
}
for _, l in ipairs(libs) do probe(l) end

print("")
print("=== _G 里的全局函数（除标准 Lua 外） ===")
for k, v in pairs(_G) do
    if type(v) == "function" then
        local info = debug.getinfo and debug.getinfo(v) or nil
        local src = info and info.short_src or "?"
        if src ~= "?main?" and src ~= "[C]" then
            print(string.format("  %s @ %s", k, src))
        end
    end
end
