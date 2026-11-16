-- pa_test27.lua — 查玩家 vehicle json
local player = Mech.GetPlayer()
print("玩家 = " .. tostring(player))

-- 查几个可能的方法
local fields = {"GetVehicle", "GetChassis", "GetGun", "GetChassisName", "GetName"}
for _, f in ipairs(fields) do
    if type(player[f]) == "function" then
        local ok, v = pcall(player[f], player)
        if ok and v then print(f .. " = " .. tostring(v)) end
    end
end

-- 列出 Mech.Create 可接受的 json
print("")
print("=== 试试动力服 JSON ===")

-- 先列几个常见的动力服路径
local suits = {
    "assets/data/vics/units/suit_cw_standard.json",
    "assets/data/vics/units/suit_faction_marine.json",
    "assets/data/vics/units/suit_volkov_spetsnaz.json",
}

for _, path in ipairs(suits) do
    local face = player:GetOrient() or 0
    local rx, ry = player:GetPosition()
    local ok, m = pcall(Mech.Create, path, Vec2.New(rx+5, ry), face, 0, 0)
    if ok and m then
        print("OK " .. path .. " -> " .. tostring(m))
        m:Delete()
    else
        print("FAIL " .. path)
    end
end
