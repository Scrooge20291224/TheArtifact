-- pa_test15.lua — 对比 DisableAI vs 不 DisableAI 的 MoveTo 效果
print("=== pa_test15: AI vs MoveTo 对比 ===")

local function load_fn(name)
    local ok, f = pcall(package.loadlib, "pa_probe.dll", name)
    return (type(f) == "function") and f or nil
end

local pa_copy_pa = load_fn("pa_copy_player_action")

local real = Mech.GetPlayer()
print("玩家 = " .. tostring(real))
local rx, ry = real:GetPosition()
print("玩家位置: " .. string.format("(%.1f, %.1f)", rx, ry))

local DEFAULT_VEHICLE = "assets/data/vics/units/rig_volta_carmine_01.json"
local face = real:GetOrient() or 0

-- === 测试 1: 不 DisableAI, 只 MoveTo ===
print("\n--- Test 1: 不 DisableAI, 直接 MoveTo ---")
local fx1, fy1 = rx + 10, ry - 5
local fake1 = Mech.Create(DEFAULT_VEHICLE, Vec2.New(fx1, fy1), face, 0, 0)
print("Fake1 (MoveTo only) = " .. tostring(fake1))
pcall(pa_copy_pa, fake1, real)  -- v10 全拷
local tx1, ty1 = rx + 20, ry - 5
print("  MoveTo 目标 (" .. string.format("%.1f, %.1f", tx1, ty1) .. ")")
pcall(function() fake1:MoveTo(Vec2.New(tx1, ty1)) end)
print("  [观察] Fake1 会不会走过去? 还是继续游荡?")

-- === 测试 2: DisableAI 后 MoveTo ===
print("\n--- Test 2: DisableAI + MoveTo ---")
local fx2, fy2 = rx + 10, ry + 5
local fake2 = Mech.Create(DEFAULT_VEHICLE, Vec2.New(fx2, fy2), face, 0, 0)
print("Fake2 (DisableAI + MoveTo) = " .. tostring(fake2))
pcall(pa_copy_pa, fake2, real)
print("  DisableAI...")
pcall(function() fake2:DisableAI() end)
local tx2, ty2 = rx + 20, ry + 5
print("  MoveTo 目标 (" .. string.format("%.1f, %.1f", tx2, ty2) .. ")")
pcall(function() fake2:MoveTo(Vec2.New(tx2, ty2)) end)
print("  [观察] Fake2 会不会走? 还是站着不动?")

-- === 测试 3: 只 MoveTo, 不拷 PA ===
print("\n--- Test 3: 只 MoveTo (不拷 PA, 对照组) ---")
local fx3, fy3 = rx, ry - 10
local fake3 = Mech.Create(DEFAULT_VEHICLE, Vec2.New(fx3, fy3), face, 0, 0)
print("Fake3 (base AI only) = " .. tostring(fake3))
local tx3, ty3 = rx, ry + 10
print("  MoveTo 目标 (" .. string.format("%.1f, %.1f", tx3, ty3) .. ")")
pcall(function() fake3:MoveTo(Vec2.New(tx3, ty3)) end)
print("  [观察] Fake3 会不会走过去?")

print("\n=== 对比三个 fake 的行为 ===")
print("重点: DisableAI 之后 MoveTo 还管用吗?")
