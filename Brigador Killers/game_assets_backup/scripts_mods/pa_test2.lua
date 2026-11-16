-- pa_test2.lua — 对比 dump：玩家 Mech vs 队友 Mech vs 敌人 Mech
-- 用法: luaload assets/scripts/mods/pa_test2.lua
-- 然后看游戏目录下 pa_probe.log（会有多次 dump）

print("=== pa_test2: 对比 dump ===")

if not package or not package.loadlib then
    print("!! package.loadlib 不可用")
    return
end

local ok, f = pcall(package.loadlib, "pa_probe.dll", "pa_dump")
if type(f) ~= "function" then
    print("!! loadlib 失败: " .. tostring(ok) .. " " .. tostring(f))
    return
end

local function dump_mch(label, mch)
    if not mch then
        print(label .. " = nil")
        return
    end
    print(label .. " = " .. tostring(mch))
    if mch.Valid then
        local ok2, v = pcall(function() return mch:Valid() end)
        print(label .. ":Valid() = " .. tostring(ok2 and v))
    end
    if mch.GetPosition then
        local ok3, x, y = pcall(function() return mch:GetPosition() end)
        if ok3 then
            print(label .. " pos = (" .. tostring(x) .. ", " .. tostring(y) .. ")")
        end
    end
    local ok4, err = pcall(f, mch)
    print("pa_dump(" .. label .. "): ok=" .. tostring(ok4) .. " err=" .. tostring(err))
end

-- 1) 真玩家
local player = Mech.GetPlayer()
dump_mch("PLAYER", player)

-- 2) 队友（NORMAL + PLAYER_TEAM）
local DEFAULT_VEHICLE = "assets/data/vics/units/rig_volta_carmine_01.json"
local px, py = player:GetPosition()
local face = player:GetOrient() or 0
local cx = px + math.cos(face) * 6
local cy = py + math.sin(face) * 6

local bh_normal = (BEHAVIOR and BEHAVIOR.BEHAVIOR_NORMAL) or 1
local tm_player = (TEAMS and TEAMS.PLAYER_TEAM) or 0

local companion = Mech.Create(DEFAULT_VEHICLE, Vec2.New(cx, cy), face, bh_normal, tm_player)
dump_mch("COMPANION(NORMAL+PLAYER)", companion)

-- 3) 敌人（NORMAL + ENEMY_TEAM）
local cx2 = px + math.cos(face + 3.14) * 6
local cy2 = py + math.sin(face + 3.14) * 6
local tm_enemy = (TEAMS and TEAMS.ENEMY_TEAM) or 1

local enemy = Mech.Create(DEFAULT_VEHICLE, Vec2.New(cx2, cy2), face, bh_normal, tm_enemy)
dump_mch("ENEMY(NORMAL+ENEMY)", enemy)

-- 4) Fake Player（PLAYER behavior + PLAYER team）
local cx3 = px + math.cos(face + 1.57) * 6
local cy3 = py + math.sin(face + 1.57) * 6
local bh_player = 0

local fake = Mech.Create(DEFAULT_VEHICLE, Vec2.New(cx3, cy3), face, bh_player, tm_player)
dump_mch("FAKE_PLAYER(PLAYER+PLAYER)", fake)

print("=== 全部 dump 完成，检查 pa_probe.log ===")
