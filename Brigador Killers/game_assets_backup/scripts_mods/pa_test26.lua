-- pa_test26.lua — DisableAI + PA copy, 验证 PA 是否绕过 AI 驱动 Mech
local function lf(name)
    local ok, f = pcall(package.loadlib, "pa_probe.dll", name)
    return (type(f) == "function") and f or nil
end

local pa_copy = lf("pa_copy_player_action")
local pa_read_f32 = lf("pa_read_f32")
if not pa_copy then print("!! pa_copy_player_action 缺失") return end

print("=== pa_test26: DisableAI + PA copy ===")

local player = Mech.GetPlayer()
local rx, ry = player:GetPosition()
print("玩家 = " .. tostring(player) .. " pos=" .. string.format("%.2f, %.2f", rx, ry))

local DEFAULT_VEHICLE = "assets/data/vics/units/rig_volta_carmine_01.json"
local face = player:GetOrient() or 0
local fx, fy = rx + math.cos(face) * 8, ry + math.sin(face) * 8

local ok_c, fake = pcall(Mech.Create, DEFAULT_VEHICLE, Vec2.New(fx, fy), face, 0, 0)
if not ok_c or not fake then print("!! fake 创建失败") return end
print("Fake = " .. tostring(fake) .. " pos=" .. string.format("%.2f, %.2f", fx, fy))

print("")
print("--- Phase 1: 先 DisableAI 关掉游荡 ---")
pcall(fake.DisableAI, fake)
print("DisableAI 调用完毕")

print("")
print("--- Phase 2: 拷 Player_Action 数据 ---")
local ok2, res = pcall(pa_copy, fake, player)
print("copy ok=" .. tostring(ok2))

if pa_read_f32 then
    print("拷后 fake 关键字段:")
    for _, off in ipairs({0x0008, 0x0400, 0x0404, 0x0700}) do
        local _, v = pcall(pa_read_f32, fake, off)
        print(string.format("  +0x%04X = %s", off, tostring(v)))
    end
end

print("")
print("=== 完成! 观察: DisableAI 之后 fake 还动不动? ===")
print("  如果还走 = PA 数据绕过 AI 直接驱动 Mech!!!")
print("  如果不走 = AI 还是控制者, PA 数据只是被动数据")
