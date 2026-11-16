-- pa_test28.lua — 用动力服创建 fake (跟玩家同类型组件)
local function lf(name)
    local ok, f = pcall(package.loadlib, "pa_probe.dll", name)
    return (type(f) == "function") and f or nil
end

local pa_copy = lf("pa_copy_player_action")
local pa_read_f32 = lf("pa_read_f32")
local pa_read_qword = lf("pa_read_qword")

print("=== pa_test28: 动力服 fake + PA copy ===")

local player = Mech.GetPlayer()
local rx, ry = player:GetPosition()
print("玩家 = " .. tostring(player) .. " pos=" .. string.format("%.2f, %.2f", rx, ry))

-- 试试几个动力服
local suits = {
    "assets/data/vics/units/suit_spc_juke_01.json",
    "assets/data/vics/units/suit_corv_sawbuck_01.json",
    "assets/data/vics/units/suit_exotic_stringer_01.json",
    "assets/data/vics/units/suit_loy_mongoose_01.json",
}

local face = player:GetOrient() or 0
local fx, fy = rx + math.cos(face) * 10, ry + math.sin(face) * 10

local fake = nil
for _, path in ipairs(suits) do
    local ok, m = pcall(Mech.Create, path, Vec2.New(fx, fy), face, 0, 0)
    if ok and m then
        print("OK " .. path)
        if fake == nil then fake = m end
    else
        print("FAIL " .. path)
    end
end

if not fake then print("!! 没有动力服能创建 fake"); return end

print("")
print("Fake = " .. tostring(fake) .. " pos=" .. string.format("%.2f, %.2f", fx, fy))

-- MoveTo 离远点
fake:MoveTo(Vec2.New(fx + 30, fy + 30))

-- 读 fake 原始 type 和查找表
if pa_read_qword then
    local _, f_type = pcall(pa_read_qword, fake, 0x0000)
    local _, f_pa = pcall(pa_read_qword, fake, 0x0230)
    print(string.format("fake 原始 type=0x%X, +0x230=0x%X", f_type or 0, f_pa or 0))
end

print("")
print("--- 拷 PA ---")
if pa_copy then
    local ok2, res = pcall(pa_copy, fake, player)
    print("copy ok=" .. tostring(ok2))
end

-- 读 fake 拷后关键字段
if pa_read_f32 then
    print("拷后 fake 关键字段:")
    for _, off in ipairs({0x0008, 0x0400, 0x0404, 0x0700}) do
        local _, v = pcall(pa_read_f32, fake, off)
        print(string.format("  +0x%04X = %s", off, tostring(v)))
    end
end

print("")
print("=== 完成! 观察: 动力服 fake 跟 rig fake 行为一样吗? ===")
