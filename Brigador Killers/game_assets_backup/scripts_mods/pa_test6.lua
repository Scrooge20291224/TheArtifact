-- pa_test6.lua — 改全局指针让 GetPlayer() 返回 fake player
print("=== pa_test6: Swap GetPlayer() target ===")

local function load_fn(name)
    local ok, f = pcall(package.loadlib, "pa_probe.dll", name)
    return (type(f) == "function") and f or nil
end

local pa_getp   = load_fn("pa_get_player_ptr")
local pa_setp   = load_fn("pa_set_player")
local pa_restp  = load_fn("pa_restore_player")
local pa_ptr    = load_fn("pa_ptr")

if not pa_setp then print("!! pa_set_player 缺失") return end

local real = Mech.GetPlayer()
print("真实玩家 = " .. tostring(real))

-- 1) 读全局指针看值
local ok, gptr = pcall(pa_getp)
print(string.format("全局 g_player = %s (0x%s)", tostring(gptr),
    ok and string.format("%X", math.floor(gptr)) or "?"))

-- 2) 生成 fake player
local DEFAULT_VEHICLE = "assets/data/vics/units/rig_volta_carmine_01.json"
local rx, ry = real:GetPosition()
local face = real:GetOrient() or 0
local fx, fy = rx + math.cos(face)*5, ry + math.sin(face)*5
local fake = Mech.Create(DEFAULT_VEHICLE, Vec2.New(fx, fy), face, 0, 0)
if not fake then print("!! fake 失败") return end
print("Fake = " .. tostring(fake))

-- 3) 确认两个 mech 的实际地址
local ok2, fake_addr = pcall(pa_ptr, fake)
local ok3, real_addr = pcall(pa_ptr, real)
print(string.format("real mech addr = 0x%X", math.floor(real_addr)))
print(string.format("fake mech addr = 0x%X", math.floor(fake_addr)))

-- 4) 改全局指针!
print("--- 改 g_player 指向 fake ---")
local ok4 = pcall(pa_setp, fake)
print("  set_player ok=" .. tostring(ok4))

-- 5) 验证: GetPlayer() 现在应该返回 fake!
local new_p = Mech.GetPlayer()
print("GetPlayer() now = " .. tostring(new_p))
if new_p == fake then
    print("!! 成功! GetPlayer() 现在返回 fake!")
else
    print("?? 不对，可能 RVA 0xB56838 不是这个全局指针")
end

print()
print("=== 测试 fake 能不能被玩家输入控制 (如果不 crash 的话) ===")
print("移动一下看看 fake 会不会跟着玩家输入动...")
print("如果 crash 了，说明方向对但还需要解绑相机等")
print()
print("如果要恢复，控制台输:")
print('  lua local p = Mech.GetPlayer(); local real = 你原来的玩家对象; pa_restore_player(real)')
