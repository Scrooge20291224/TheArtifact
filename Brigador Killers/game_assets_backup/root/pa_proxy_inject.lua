-- pa_proxy_inject.lua v2 — proxy DLL 已经在自动 PA 注入
-- 这个脚本只负责创建 fake + DisableAI, 剩下的交给 proxy SDL2 hook
print("=== pa_proxy_inject v2 ===")
print("proxy DLL 已在后台每 16ms memcpy player PA → fake PA")

local player = Mech.GetPlayer()
if not player then print("!! Mech.GetPlayer() 失败"); return end

local rx, ry = player:GetPosition()
local face = player:GetOrient() or 0
print(string.format("玩家 pos=(%.2f, %.2f)", rx, ry))

local DEFAULT_VEHICLE = "assets/data/vics/units/rig_volta_carmine_01.json"
local fx, fy = rx + math.cos(face) * 6, ry + math.sin(face) * 6

local ok, fake = pcall(Mech.Create, DEFAULT_VEHICLE, Vec2.New(fx, fy), face, 0, 0)
if not ok or not fake then print("!! fake 创建失败"); return end
print("Fake 创建成功: " .. tostring(fake))

-- DisableAI: 关掉 fake 的自主行为, 让 proxy 的 PA 数据驱动它
pcall(fake.DisableAI, fake)
print("DisableAI 完成")

print("")
print("========================================")
print(" 现在移动你的玩家!")
print(" 观察: fake 会不会跟着一起动?")
print("  - 会 = PA 注入成功! 层级 B 可行!")
print("  - 不会 = PA 是输出, 引擎覆盖了")
print("========================================")
