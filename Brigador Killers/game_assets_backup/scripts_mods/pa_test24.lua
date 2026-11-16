-- pa_test24.lua — v15.1: 用跟玩家相同类型的 vehicle json
local function lf(name)
    local ok, f = pcall(package.loadlib, "pa_probe.dll", name)
    return (type(f) == "function") and f or nil
end

local pa_copy = lf("pa_copy_player_action")
local pa_read_f32 = lf("pa_read_f32")
if not pa_copy then print("!! pa_copy_player_action 缺失") return end

print("=== pa_test24: v15.1 匹配玩家类型 ===")

local player = Mech.GetPlayer()
local rx, ry = player:GetPosition()
print("玩家 = " .. tostring(player))
print("玩家位置 = " .. string.format("%.2f, %.2f", rx, ry))

-- 先用 rig, 然后让 fake 用 MoveTo 自己走开
local face = player:GetOrient() or 0
local fx, fy = rx + math.cos(face)*5, ry + math.sin(face)*5

-- 试试让 fake 走离玩家远点
local fake = Mech.Create("assets/data/vics/units/rig_volta_carmine_01.json", Vec2.New(fx, fy), face, 0, 0)
if not fake then print("!! fake 创建失败") return end
print("Fake = " .. tostring(fake))

print("--- 先让 fake 自己 MoveTo 离开玩家 ---")
local tx, ty = fx + 30, fy + 30
fake:MoveTo(Vec2.New(tx, ty))
print("MoveTo(" .. string.format("%.1f, %.1f", tx, ty) .. ") done")

print("--- 调用 pa_copy_player_action ---")
local ok2, res = pcall(pa_copy, fake, player)
print("copy ok=" .. tostring(ok2) .. " res=" .. tostring(res))

print("")
print("--- 拷后读几个字段 ---")
if pa_read_f32 then
    for _, off in ipairs({0x0400, 0x0404, 0x0700, 0x0704}) do
        local ok3, v = pcall(pa_read_f32, fake, off)
        if ok3 and v then
            print(string.format("  fake +0x%04X = %s", off, tostring(v)))
        end
    end
end

print("")
print("=== 完成! 观察: fake 独立走, 玩家正常 ===")
print("如果玩家又变成载具, 说明 Mech.Create 有 bug")
