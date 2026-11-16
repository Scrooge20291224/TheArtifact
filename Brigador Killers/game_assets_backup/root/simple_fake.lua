-- simple_fake.lua — 最简脚本, 不依赖任何 DLL, 只创建 fake + DisableAI
-- proxy DLL 已经在后台自动做 PA 注入, 这里不需要调 pa_probe
print("=== simple_fake: 创建 fake, 让 proxy DLL 驱动它 ===")

local player = Mech.GetPlayer()
if not player then print("!! Mech.GetPlayer() 失败"); return end

local rx, ry = player:GetPosition()
local face = player:GetOrient() or 0
print(string.format("玩家 pos=(%.2f, %.2f) face=%.2f", rx, ry, face))

local ok_c, fake = pcall(Mech.Create,
    "assets/data/vics/units/rig_volta_carmine_01.json",
    Vec2.New(rx + math.cos(face) * 8, ry + math.sin(face) * 8),
    face, 0, 0)

if not ok_c or not fake then
    print("!! fake 创建失败 ok=" .. tostring(ok_c))
    return
end

print("Fake 创建成功: " .. tostring(fake))
pcall(fake.DisableAI, fake)
print("DisableAI 完成")

print("")
print("现在移动你的玩家, 看 fake 会不会跟着动!")
print("(proxy DLL 每 16ms 自动把玩家 PA 数据拷给 fake)")
