-- pa_test8.lua — 扫 Mech 里的 heap 指针，找 Player_Action 指针
print("=== pa_test8: Find Player_Action Pointer ===")

local function load_fn(name)
    local ok, f = pcall(package.loadlib, "pa_probe.dll", name)
    return (type(f) == "function") and f or nil
end

local pa_dq = load_fn("pa_dump_qwords")

if not pa_dq then print("!! pa_dump_qwords 缺失") return end

local real = Mech.GetPlayer()
print("真实玩家 = " .. tostring(real))

-- dump 玩家的 qwords
print("--- Dump 玩家的 heap 指针 ---")
pcall(pa_dq, real)

-- 生成 fake player
local DEFAULT_VEHICLE = "assets/data/vics/units/rig_volta_carmine_01.json"
local rx, ry = real:GetPosition()
local face = real:GetOrient() or 0
local fx, fy = rx + math.cos(face)*5, ry + math.sin(face)*5
local fake = Mech.Create(DEFAULT_VEHICLE, Vec2.New(fx, fy), face, 0, 0)
if not fake then print("!! fake 失败") return end
print("Fake = " .. tostring(fake))

-- dump fake 的 qwords
print("--- Dump fake 的 heap 指针 ---")
pcall(pa_dq, fake)

print("=== 完成! 去 log 看两个 dump 的差异 ===")
print("(扫 Mech +0x0000~+0x2000 里玩家独有但 fake 为 0 的 qword)")
