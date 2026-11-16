-- pa_test9.lua — 验证 +0x0230 是不是 Player_Action 指针
print("=== pa_test9: 验证 Player_Action 指针 ===")

local function load_fn(name)
    local ok, f = pcall(package.loadlib, "pa_probe.dll", name)
    return (type(f) == "function") and f or nil
end

local pa_rq  = load_fn("pa_read_qword")
local pa_peek = load_fn("pa_peek")
local pa_cq  = load_fn("pa_copy_qword")

if not pa_rq or not pa_peek then print("!! DLL 函数缺失") return end

local real = Mech.GetPlayer()
print("玩家 = " .. tostring(real))

-- 1) 读玩家 +0x0230
local ok1, player_pa_ptr = pcall(pa_rq, real, 0x0230)
print(string.format("玩家 +0x0230 = 0x%s",
    ok1 and string.format("%X", math.floor(player_pa_ptr)) or "ERR"))

-- 2) peek 那个地址（看虚表是不是 PlayerControlled）
if ok1 and player_pa_ptr and player_pa_ptr ~= 0 then
    print("--- Peek Player_Action 对象头 ---")
    pcall(pa_peek, player_pa_ptr, 64)
end

-- 3) 生成 fake player
local DEFAULT_VEHICLE = "assets/data/vics/units/rig_volta_carmine_01.json"
local rx, ry = real:GetPosition()
local face = real:GetOrient() or 0
local fx, fy = rx + math.cos(face)*5, ry + math.sin(face)*5
local fake = Mech.Create(DEFAULT_VEHICLE, Vec2.New(fx, fy), face, 0, 0)
if not fake then print("!! fake 失败") return end
print("Fake = " .. tostring(fake))

-- 4) 读 fake +0x0230
local ok2, fake_pa_ptr = pcall(pa_rq, fake, 0x0230)
print(string.format("Fake +0x0230 = 0x%s",
    ok2 and string.format("%X", math.floor(fake_pa_ptr)) or "ERR"))

if ok2 and fake_pa_ptr == 0 then
    print("!! 确认! Fake +0x0230 是 0, 玩家 +0x0230 有值")
    print("!! +0x0230 就是 Player_Action 指针!")
end

-- 5) 实验: 把玩家的 Player_Action 指针复制到 fake
print("--- 复制 Player_Action 指针到 fake ---")
local ok3 = pcall(pa_cq, fake, real, 0x0230)
print("  copy_qword ok=" .. tostring(ok3))

-- 6) 再读确认
local ok4, fake_pa_ptr2 = pcall(pa_rq, fake, 0x0230)
print(string.format("复制后 fake +0x0230 = 0x%s",
    ok4 and string.format("%X", math.floor(fake_pa_ptr2)) or "ERR"))

print()
print("=== 现在试试 fake 有没有 Player_Action 功能 ===")
print("试试移动、开火... 如果不 crash 说明方向对了")
