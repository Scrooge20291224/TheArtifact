-- pa_test5.lua — 验证 Player_Action 字段控制
-- 拷完 PA 后，尝试直接改 fake 的 speed / lateral 字段看反应

print("=== pa_test5: Field Write Test ===")

local function load_fn(name)
    local ok, f = pcall(package.loadlib, "pa_probe.dll", name)
    return (type(f) == "function") and f or nil
end

local pa_copy  = load_fn("pa_copy_player_action")
local pa_rf32  = load_fn("pa_read_f32")
local pa_wf32  = load_fn("pa_write_f32")

if not pa_copy or not pa_wf32 then
    print("!! DLL 函数缺失")
    return
end

local p = Mech.GetPlayer()
print("玩家 = " .. tostring(p))

-- 生成 fake player
local DEFAULT_VEHICLE = "assets/data/vics/units/rig_volta_carmine_01.json"
local px, py = p:GetPosition()
local face = p:GetOrient() or 0
local fx = px + math.cos(face) * 4
local fy = py + math.sin(face) * 4
local fake = Mech.Create(DEFAULT_VEHICLE, Vec2.New(fx, fy), face, 0, 0)
if not fake then print("!! fake 生成失败") return end
print("Fake = " .. tostring(fake))

-- 先关掉 fake 自己的游荡 AI
fake:DisableAI()
print("DisableAI 调用完毕")

-- 拷 Player_Action
print("Copying PA...")
local ok = pcall(pa_copy, fake, p)
print("  copy ok=" .. tostring(ok))

-- 先读一遍 fake 拷后状态
print("--- 拷后 fake 关键字段 ---")
local offsets = {
    {0x0008, "float_A"},
    {0x000C, "float_B"},
    {0x0400, "PA_main_f58"},
    {0x0404, "PA_next"},
    {0x0702, "speed_coef"},
    {0x0706, "time_coef"},
    {0x0758, "triplet1_f"},
    {0x07BC, "triplet2_f"},
    {0x07D4, "triplet3_f"},
}
for _, c in ipairs(offsets) do
    local ok2, v = pcall(pa_rf32, fake, c[1])
    print(string.format("  +0x%04X %s: %s", c[1], c[2], tostring(ok2 and v or "ERR")))
end

-- 对比读玩家的同样字段
print("--- 玩家同样字段 ---")
for _, c in ipairs(offsets) do
    local ok3, v = pcall(pa_rf32, p, c[1])
    print(string.format("  +0x%04X %s: %s", c[1], c[2], tostring(ok3 and v or "ERR")))
end

print("=== 现在试试直接写字段 ===")
print("去控制台输入:")
print('  lua local pa_w = package.loadlib("pa_probe.dll","pa_write_f32"); pa_w(__vs_fake, 0x0400, 100.0)')
print('然后看 fake 会不会有反应')
print()
print('或者试试 +0x0702 (speed_coef):')
print('  lua local pa_w = package.loadlib("pa_probe.dll","pa_write_f32"); pa_w(__vs_fake, 0x0702, 2.0)')
