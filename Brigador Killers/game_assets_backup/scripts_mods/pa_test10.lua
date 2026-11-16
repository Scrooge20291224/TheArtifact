-- pa_test10.lua — 重新生成玩家 vs fake 的原始 hex dump, 精确 diff
print("=== pa_test10: 原始 hex dump + 精确 diff ===")

local function load_fn(name)
    local ok, f = pcall(package.loadlib, "pa_probe.dll", name)
    return (type(f) == "function") and f or nil
end

local pa_dump = load_fn("pa_dump")
if not pa_dump then print("!! pa_dump 缺失") return end

local real = Mech.GetPlayer()
print("玩家 = " .. tostring(real))
pcall(pa_dump, real)

local DEFAULT_VEHICLE = "assets/data/vics/units/rig_volta_carmine_01.json"
local rx, ry = real:GetPosition()
local face = real:GetOrient() or 0
local fx, fy = rx + math.cos(face)*5, ry + math.sin(face)*5
local fake = Mech.Create(DEFAULT_VEHICLE, Vec2.New(fx, fy), face, 0, 0)
if not fake then print("!! fake 失败") return end
print("Fake = " .. tostring(fake))
pcall(pa_dump, fake)

print("=== Dump 完成, 去 log 看 ===")
