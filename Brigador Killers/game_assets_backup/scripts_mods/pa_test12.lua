-- pa_test12.lua — DisableAI + 拷 PA + 手动写字段测试
print("=== pa_test12: 精确控制测试 ===")

local function load_fn(name)
    local ok, f = pcall(package.loadlib, "pa_probe.dll", name)
    return (type(f) == "function") and f or nil
end

local pa_copy_pa  = load_fn("pa_copy_player_action")
local pa_read_f32 = load_fn("pa_read_f32")
local pa_write_f32 = load_fn("pa_write_f32")

local real = Mech.GetPlayer()
print("玩家 = " .. tostring(real))

local DEFAULT_VEHICLE = "assets/data/vics/units/rig_volta_carmine_01.json"
local rx, ry = real:GetPosition()
local face = real:GetOrient() or 0
local fx, fy = rx + math.cos(face)*5, ry + math.sin(face)*5
local fake = Mech.Create(DEFAULT_VEHICLE, Vec2.New(fx, fy), face, 0, 0)
print("Fake = " .. tostring(fake))

-- 1. 彻底关掉 fake 自己的游荡 AI
print("\n--- Step 1: DisableAI ---")
local ok, err = pcall(function() fake:DisableAI() end)
print("  DisableAI ok=" .. tostring(ok) .. " err=" .. tostring(err))

-- 2. 拷 Player_Action
print("\n--- Step 2: 拷 Player_Action ---")
ok, err = pcall(pa_copy_pa, fake, real)
print("  copy_pa ok=" .. tostring(ok) .. " err=" .. tostring(err))

-- 3. 读关键字段
print("\n--- Step 3: 关键字段 ---")
local function read(label, off)
    local v = pa_read_f32(fake, off)
    local r = pa_read_f32(real, off)
    print(string.format("  %s: fake=%s player=%s", label, tostring(v), tostring(r)))
end
read("+0x0008 pair1_a", 0x0008)
read("+0x000C pair1_b", 0x000C)
read("+0x0400 PA_main",  0x0400)
read("+0x0404 PA_next",  0x0404)
read("+0x0702 speed_coef", 0x0702)
read("+0x0706 time_coef", 0x0706)

-- 4. 手动写 speed coef = 大值 看 fake 会不会猛走
print("\n--- Step 4: 手动写 speed_coef=10 ---")
ok, err = pcall(pa_write_f32, fake, 0x0702, 10.0)
print("  write ok=" .. tostring(ok))
local v = pa_read_f32(fake, 0x0702)
print("  验证 fake+0x0702 = " .. tostring(v))
print("  [观察] fake 会不会突然加速或走动?")

-- 5. 手动写 speed_coef 恢复
print("\n--- Step 5: speed_coef 恢复 1.0 ---")
pcall(pa_write_f32, fake, 0x0702, 1.0)

-- 6. 试试手动写 Lateral/PA 偏移
print("\n--- Step 6: 试试手动写 PA_main ---")
pcall(pa_write_f32, fake, 0x0400, 100.0)
local v2 = pa_read_f32(fake, 0x0400)
print("  fake+0x0400 已写成 100.0: " .. tostring(v2))
print("  [观察] fake 有没有反应?")

print("\n=== 测试完成, 告诉我 fake 有没有任何反应 ===")
