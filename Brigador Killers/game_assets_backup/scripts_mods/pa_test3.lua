-- pa_test3.lua — 把玩家的 Player_Action 拷到 fake player，测试能否控制
-- 注意: 这个脚本只生成 1 个 fake player，不生成敌人

print("=== pa_test3: Copy Player_Action ===")

if not package or not package.loadlib then
    print("!! package.loadlib 不可用")
    return
end

-- 加载所有 DLL 函数
local function load_fn(name)
    local ok, f = pcall(package.loadlib, "pa_probe.dll", name)
    if type(f) == "function" then
        print(string.format("  [%s] OK", name))
        return f
    else
        print(string.format("  [%s] FAIL: ok=%s fn=%s", name, tostring(ok), tostring(f)))
        return nil
    end
end

local pa_dump = load_fn("pa_dump")
local pa_ptr  = load_fn("pa_ptr")
local pa_copy_pa = load_fn("pa_copy_player_action")
local pa_copy_region = load_fn("pa_copy_region")
local pa_read_u32  = load_fn("pa_read_u32")
local pa_read_f32  = load_fn("pa_read_f32")
local pa_write_u32 = load_fn("pa_write_u32")
local pa_write_f32 = load_fn("pa_write_f32")

if not pa_copy_pa then
    print("!! 关键函数加载失败，退出")
    return
end

-- 1) 生成一个 fake player（BEHAVIOR_PLAYER + PLAYER_TEAM）
local p = Mech.GetPlayer()
print("玩家 = " .. tostring(p))

local DEFAULT_VEHICLE = "assets/data/vics/units/rig_volta_carmine_01.json"
local px, py = p:GetPosition()
local face = p:GetOrient() or 0
local fx = px + math.cos(face) * 4
local fy = py + math.sin(face) * 4

local fake = Mech.Create(DEFAULT_VEHICLE, Vec2.New(fx, fy), face, 0, 0)
if not fake then
    print("!! fake player 生成失败")
    return
end
print("Fake player = " .. tostring(fake))

-- 2) 先 dump fake player 原始状态（确认它没有 Player_Action）
if pa_dump then
    print("Dumping fake player 原始状态...")
    local ok = pcall(pa_dump, fake)
    print("  dump ok=" .. tostring(ok))
end

-- 3) 拷 Player_Action
print("Copying Player_Action from player to fake...")
local ok = pcall(pa_copy_pa, fake, p)
print("  copy ok=" .. tostring(ok))

-- 4) dump 拷完后的 fake（确认变化）
if pa_dump then
    print("Dumping fake player AFTER copy...")
    local ok2 = pcall(pa_dump, fake)
    print("  dump ok=" .. tostring(ok2))
end

-- 5) 读几个关键字段验证
if pa_read_u32 and pa_read_f32 then
    print("--- 读字段验证 ---")
    local offsets = {0x0008, 0x0040, 0x0400, 0x0404, 0x0702, 0x0706}
    for _, off in ipairs(offsets) do
        local ok3, val3 = pcall(pa_read_f32, fake, off)
        print(string.format("  +0x%04X f32 = %s", off, tostring(ok3 and val3 or "ERR")))
    end
end

print("=== 测试完成，看游戏目录下 pa_probe.log ===")
print("现在试试在控制台手动控制 fake player:")
print('  lua fake:DisableAI()')
print('  lua fake:MoveTo(Vec2.New(' .. string.format("%.1f", px + 10) .. ', ' .. string.format("%.1f", py) .. '))')
