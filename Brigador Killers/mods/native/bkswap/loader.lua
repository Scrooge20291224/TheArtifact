-- bkswap 载入器：把 native DLL 的加载过程封装成一个短命令
-- 用法（进关卡后，控制台）：luaload assets/scripts/mods/bkswap.lua
-- 需要改行为时，编辑 %TEMP%\bk_swap.txt，再执行一次本命令即可。

local candidates = {
    "C:/bk/bkswap7.dll",
    "C:/Users/Scrooge/Documents/GitHub/TheArtifact/Brigador Killers/mods/native/bkswap/bin/bkswap7.dll",
}

local loaded = false
local last_err = "no candidate"

for _, path in ipairs(candidates) do
    local f, e = package.loadlib(path, "luaopen_bkswap")
    if f then
        local ok, err = pcall(f)
        if ok then
            print("[bkswap] loaded: " .. path)
            loaded = true
        else
            last_err = tostring(err)
        end
        break
    else
        last_err = tostring(e)
    end
end

if not loaded then
    print("[bkswap] load failed: " .. last_err)
end
