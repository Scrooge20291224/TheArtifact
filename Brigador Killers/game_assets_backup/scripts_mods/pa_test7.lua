-- pa_test7.lua — 改玩家指针让 GetPlayer() 返回 fake
-- 这次用精确链: state->+0x40->+0x1C468
print("=== pa_test7: Swap GetPlayer() via state chain ===")

local function load_fn(name)
    local ok, f = pcall(package.loadlib, "pa_probe.dll", name)
    return (type(f) == "function") and f or nil
end

local pa_getp  = load_fn("pa_get_player_ptr")
local pa_setp  = load_fn("pa_set_player")
local pa_backp = load_fn("pa_backup_player")
local pa_restp = load_fn("pa_restore_player")

if not pa_setp or not pa_backp then print("!! DLL 函数缺失") return end

local real = Mech.GetPlayer()
print("真实玩家 Lua obj = " .. tostring(real))

-- 备份!
pcall(pa_backp)

-- 读当前玩家 Mech*
local ok, cur_ptr = pcall(pa_getp)
print(string.format("当前 GetPlayer mech* = 0x%s",
    ok and string.format("%X", math.floor(cur_ptr)) or "ERR"))

-- 生成 fake player
local DEFAULT_VEHICLE = "assets/data/vics/units/rig_volta_carmine_01.json"
local rx, ry = real:GetPosition()
local face = real:GetOrient() or 0
local fx, fy = rx + math.cos(face)*5, ry + math.sin(face)*5
local fake = Mech.Create(DEFAULT_VEHICLE, Vec2.New(fx, fy), face, 0, 0)
if not fake then print("!! fake 失败") return end
print("Fake = " .. tostring(fake))

-- 改!
print("--- 改玩家指针指向 fake ---")
local ok2 = pcall(pa_setp, fake)
print("  set_player ok=" .. tostring(ok2))

-- 验证
local new_p = Mech.GetPlayer()
print("GetPlayer() now = " .. tostring(new_p))
print("和 fake 同一个? " .. tostring(new_p == fake))
print("和 real 同一个? " .. tostring(new_p == real))

if new_p == fake then
    print("!! 成功!")
    print()
    print("现在试试移动, 看玩家输入会不会作用到 fake (如果不 crash)")
    print("或者在控制台试:")
    print('  __vs_fake:DisableAI()')
    print("然后移动试试...")
else
    print("?? 不对... 可能 state 链有问题")
end

print()
print("=== 如果 crash 要恢复, 重进游戏或者: ===")
print("  lua package.loadlib('pa_probe.dll','pa_restore_player')()")
