-- ffi 冒烟测试 v2: 试 require("ffi") 和更多入口
-- 用法: lua vs_ffi_probe()

local function log(msg) print("[ffi_probe] " .. tostring(msg)) end

function vs_ffi_probe()
    log("=== 1. require('ffi') ===")
    local ok1, ffi = pcall(require, "ffi")
    log("  require('ffi') = " .. tostring(ok1) .. " -> " .. tostring(ffi))
    if ok1 and ffi then
        log("  ffi.type = " .. tostring(ffi.type))
        log("  ffi.load = " .. tostring(ffi.load))
        log("  ffi.cast = " .. tostring(ffi.cast))
    end

    log("=== 2. jit.off + require ===")
    local ok2, jit = pcall(require, "jit")
    log("  require('jit') = " .. tostring(ok2) .. " -> " .. tostring(jit))
    if ok2 and jit and jit.off then
        jit.off("ffi")
        log("  jit.off('ffi') 已调用")
        local ok3, ffi2 = pcall(require, "ffi")
        log("  再次 require('ffi') = " .. tostring(ok3) .. " -> " .. tostring(ffi2))
    end

    log("=== 3. table.loadstring ===")
    local ok4, ls = pcall(function() return loadstring end)
    log("  loadstring = " .. tostring(ls))

    log("=== 4. 直接调 luaopen_ffi (已知在 exe RVA 0x3299B0) ===")
    if ffi or (ok1 and ffi) then
        log("  ffi 已可用, 跳过这步")
    else
        -- 用 debug 找 luaopen_ffi, 或者用 pa_probe 导出
        log("  需要另想办法获取 luaopen_ffi 指针")
    end

    log("=== 5. package.loadlib 试从 exe 加载 ===")
    -- 有些实现里 loadlib 可以传 exe 自身
    local ok5, val5 = pcall(package.loadlib, "Brigador Killers.exe", "luaopen_ffi")
    log("  package.loadlib('Brigador Killers.exe','luaopen_ffi') = " .. tostring(ok5) .. " -> " .. tostring(val5))

    -- 也试当前目录
    local ok6, val6 = pcall(package.loadlib, ".", "luaopen_ffi")
    log("  package.loadlib('.','luaopen_ffi') = " .. tostring(ok6) .. " -> " .. tostring(val6))

    log("=== 6. 如果 ffi 可用, 测 kernel32 ===")
    local ffi_use = ffi or (ok1 and ffi) or nil
    if ffi_use and ffi_use.load then
        local ok7, k32 = pcall(function() return ffi_use.load("kernel32") end)
        log("  ffi.load('kernel32') = " .. tostring(ok7) .. " -> " .. tostring(k32))
        if ok7 and k32 then
            local ok8, tick = pcall(k32.GetTickCount)
            log("  GetTickCount() = " .. tostring(ok8) .. " -> " .. tostring(tick))
        end
    else
        log("  ffi 不可用, 跳过 kernel32 测试")
    end

    log("=== 完成 ===")
end

log("ffi_probe v2 已加载, 运行: lua vs_ffi_probe()")
