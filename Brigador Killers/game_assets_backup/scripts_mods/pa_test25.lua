-- pa_test25.lua — 逐段测试, 修复 pcall 返回值 bug
local function lf(name)
    local ok, f = pcall(package.loadlib, "pa_probe.dll", name)
    return (type(f) == "function") and f or nil
end

local pa_copy_slice = lf("pa_copy_slice")
if not pa_copy_slice then print("!! pa_copy_slice 缺失") return end

print("=== pa_test25: slice-by-slice crash test ===")

local player = Mech.GetPlayer()
local rx, ry = player:GetPosition()

local slices = {
    {0x0008, 0x0010, "float_A/B (8b)"},
    {0x0040, 0x0044, "float_C (4b)"},
    {0x0400, 0x0410, "PA_main+next (16b)"},
    {0x0700, 0x0710, "speed_region (16b)"},
}

local DEFAULT_VEHICLE = "assets/data/vics/units/rig_volta_carmine_01.json"
local face = player:GetOrient() or 0

for i, slice in ipairs(slices) do
    local s, e, label = slice[1], slice[2], slice[3]
    print("")
    print(string.format("[%d] 创建 fake 并拷 +0x%04X~+0x%04X (%s)", i, s, e, label))

    local fx, fy = rx + math.cos(face) * (5 + i * 3), ry + math.sin(face) * (5 + i * 3)
    local ok, fake = pcall(Mech.Create, DEFAULT_VEHICLE, Vec2.New(fx, fy), face, 0, 0)
    if not ok or not fake then
        print("  !! 创建失败") goto continue
    end

    fake:MoveTo(Vec2.New(fx + 20, fy + 20))
    print("  fake 创建 OK")

    local ok2, res = pcall(pa_copy_slice, fake, player, s, e)
    print("  copy ok=" .. tostring(ok2))

    ::continue::
end

print("")
print("=== 全部完成, 退出游戏看 pa_probe.log ===")
