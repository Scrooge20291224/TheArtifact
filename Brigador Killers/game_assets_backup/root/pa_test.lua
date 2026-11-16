-- pa_probe v17 冒烟测试: 验证 package.loadlib 能不能加载 DLL + 读/写 Mech 内存
-- 用法: lua pa_test()

local function log(msg) print("[pa_test] " .. tostring(msg)) end

function pa_test()
    log("=== Step 1: package.cpath ===")
    log("  package.path = " .. tostring(package.path))
    log("  package.cpath = " .. tostring(package.cpath))

    log("=== Step 2: package.loadlib('pa_probe', ...) 测试 ===")
    -- 先试简单函数
    local ok1, fn1 = pcall(package.loadlib, "pa_probe", "pa_read_f32")
    log("  loadlib('pa_probe','pa_read_f32') = " .. tostring(ok1) .. " -> " .. tostring(fn1))

    local ok2, fn2 = pcall(package.loadlib, "pa_probe", "pa_write_f32")
    log("  loadlib('pa_probe','pa_write_f32') = " .. tostring(ok2) .. " -> " .. tostring(fn2))

    local ok3, fn3 = pcall(package.loadlib, "pa_probe", "luaopen_pa_probe")
    log("  loadlib('pa_probe','luaopen_pa_probe') = " .. tostring(ok3) .. " -> " .. tostring(fn3))

    -- 如果 loadlib 失败, 试 .dll 扩展名
    if not ok1 then
        log("  --- 试 pa_probe.dll ---")
        local ok1b, fn1b = pcall(package.loadlib, "pa_probe.dll", "pa_read_f32")
        log("  loadlib('pa_probe.dll','pa_read_f32') = " .. tostring(ok1b) .. " -> " .. tostring(fn1b))
        fn1 = ok1b and fn1b or fn1
        fn2 = ok2 and fn2 or (ok1b and select(2, pcall(package.loadlib, "pa_probe.dll", "pa_write_f32")) or fn2)
    end

    if not ok1 or not fn1 then
        log("  --- 试绝对路径 ---")
        local exe_dir = string.match(debug.getinfo(1).source, "^@(.+[/\\])")
        if exe_dir then
            log("  exe_dir = " .. exe_dir)
        end
        -- 游戏目录就是 exe 所在
        local ok1c, fn1c = pcall(package.loadlib, "./pa_probe.dll", "pa_read_f32")
        log("  loadlib('./pa_probe.dll','pa_read_f32') = " .. tostring(ok1c) .. " -> " .. tostring(fn1c))
        if ok1c then fn1 = fn1c end
    end

    if not fn1 then
        log("=== 所有 package.loadlib 方式都失败 ===")
        log("  pa_probe.dll 必须在 package.cpath 里能搜到的位置")
        log("  或者需要用 ffi.load 加载 (但 ffi 被阉割了)")
        return false
    end

    log("=== Step 3: 调用 DLL 函数 ===")
    local player = Mech.GetPlayer()
    log("  Mech.GetPlayer() = " .. tostring(player))
    if not player then
        log("  不在关卡里, 需要先进关卡")
        return false
    end

    -- 读 player +0x0000 (type), 应该是 6
    local ok4, val = pcall(fn1, player, 0x0000)
    log("  pa_read_f32(player, 0x0000) = " .. tostring(ok4) .. " -> " .. tostring(val))

    -- 读 player +0x230 (PA LUT 指针低 32 位)
    local ok5, val2 = pcall(fn1, player, 0x0230)
    log("  pa_read_f32(player, 0x0230) = " .. tostring(ok5) .. " -> " .. tostring(val2))

    log("=== Step 4: write 测试 ===")
    -- 临时改 +0x0040 一个 float, 再读回来
    if fn2 then
        local ok6, r1 = pcall(fn1, player, 0x0040)
        log("  原值 +0x0040 = " .. tostring(r1))
        local ok7, r2 = pcall(fn2, player, 0x0040, r1)
        log("  写回 +0x0040 = " .. tostring(r2))
        local ok8, r3 = pcall(fn1, player, 0x0040)
        log("  读后 +0x0040 = " .. tostring(r3))
    else
        log("  fn2 (write_f32) 没加载, 跳过写测试")
    end

    log("=== pa_test 完成! ===")
    return true
end

log("pa_test 已加载, 运行: lua pa_test()")
