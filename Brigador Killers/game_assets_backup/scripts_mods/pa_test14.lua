-- pa_test14.lua — DisableAI + v10 全拷 + MoveTo + 手动写字段
print("=== pa_test14: 精确控制 fake ===")

local function load_fn(name)
    local ok, f = pcall(package.loadlib, "pa_probe.dll", name)
    return (type(f) == "function") and f or nil
end

local pa_copy_pa   = load_fn("pa_copy_player_action")
local pa_read_f32  = load_fn("pa_read_f32")
local pa_write_f32 = load_fn("pa_write_f32")
local pa_ptr       = load_fn("pa_ptr")

local real = Mech.GetPlayer()
print("玩家 = " .. tostring(real))

local rx, ry = real:GetPosition()
print("玩家位置: " .. string.format("(%.1f, %.1f)", rx, ry))

local DEFAULT_VEHICLE = "assets/data/vics/units/rig_volta_carmine_01.json"
local face = real:GetOrient() or 0
local fx, fy = rx + math.cos(face)*5, ry + math.sin(face)*5
local fake = Mech.Create(DEFAULT_VEHICLE, Vec2.New(fx, fy), face, 0, 0)
print("Fake = " .. tostring(fake))

-- 先 DisableAI 彻底关掉 fake 自己的游荡
print("\n--- Step 1: DisableAI 关掉游荡 ---")
pcall(function() fake:DisableAI() end)

-- v10: 全拷 + 恢复组件指针
print("\n--- Step 2: v10 全拷 + 恢复组件 ---")
local ok, err = pcall(pa_copy_pa, fake, real)
print("  copy ok=" .. tostring(ok))

-- 读关键字段
print("\n--- Step 3: 验证拷贝结果 ---")
local function show(label, off)
    local v = pa_read_f32(fake, off)
    print(string.format("  fake+0x%04X %s = %s", off, label, tostring(v)))
end
show("type(u32)", 0x0000)
show("float_A",   0x0008)
show("PA_main",   0x0400)
show("speed_coef",0x0702)

-- DisableAI 后用 MoveTo 看会不会走
print("\n--- Step 4: MoveTo 测试 ---")
local tx, ty = rx + 15, ry
print("  目标: (" .. string.format("%.1f, %.1f", tx, ty) .. ")")
ok, err = pcall(function() fake:MoveTo(Vec2.New(tx, ty)) end)
print("  MoveTo ok=" .. tostring(ok) .. " err=" .. tostring(err))
print("  [观察] fake 会不会走过去?")

-- 等一下
for i = 1, 1000000 do end  -- 轻等

-- 手动写 speed_coef = 3.0 (加速)
print("\n--- Step 5: 手动写 speed_coef=3.0 ---")
pcall(pa_write_f32, fake, 0x0702, 3.0)
print("  [观察] fake 会不会加速?")

-- 再等
for i = 1, 2000000 do end

-- 恢复 speed
print("\n--- Step 6: speed_coef 恢复 1.0 ---")
pcall(pa_write_f32, fake, 0x0702, 1.0)

print("\n=== 测试完成, 告诉我 fake 全程的反应 ===")
