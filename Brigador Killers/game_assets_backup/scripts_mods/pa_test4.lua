-- pa_test4.lua — 精确拷 Player_Action 小段，验证不 crash
print("=== pa_test4: Precise copy, verify returns ===")

if not package or not package.loadlib then
    print("!! package.loadlib 不可用")
    return
end

local function load_fn(name)
    local ok, f = pcall(package.loadlib, "pa_probe.dll", name)
    if type(f) == "function" then return f end
    print(string.format("  [%s] FAIL: %s", name, tostring(f)))
    return nil
end

local pa_copy_pa = load_fn("pa_copy_player_action")
local pa_read_f32 = load_fn("pa_read_f32")
local pa_read_u32 = load_fn("pa_read_u32")
local pa_write_f32 = load_fn("pa_write_f32")

if not pa_copy_pa or not pa_read_f32 then
    print("!! 关键函数缺失")
    return
end

local p = Mech.GetPlayer()
print("玩家 = " .. tostring(p))

-- 先测读返回值（确认 settop 修复）
print("--- 测试返回值 ---")
local ok, val = pcall(pa_read_f32, p, 0x0008)
print(string.format("  read_f32(player, 0x0008): ok=%s val=%s", tostring(ok), tostring(val)))

ok, val = pcall(pa_read_f32, p, 0x0400)
print(string.format("  read_f32(player, 0x0400): ok=%s val=%s", tostring(ok), tostring(val)))

ok, val = pcall(pa_read_u32, p, 0x04C4)
print(string.format("  read_u32(player, 0x04C4) team: ok=%s val=%s", tostring(ok), tostring(val)))

-- 生成 fake player
local DEFAULT_VEHICLE = "assets/data/vics/units/rig_volta_carmine_01.json"
local px, py = p:GetPosition()
local face = p:GetOrient() or 0
local fx = px + math.cos(face) * 4
local fy = py + math.sin(face) * 4

local fake = Mech.Create(DEFAULT_VEHICLE, Vec2.New(fx, fy), face, 0, 0)
if not fake then print("!! fake 生成失败") return end
print("Fake = " .. tostring(fake))

-- 拷 Player_Action（精确小段，跳过 AI 指针）
print("Copying precise regions...")
local ok2 = pcall(pa_copy_pa, fake, p)
print("  copy ok=" .. tostring(ok2))

-- 拷完后读几个关键字段，确认有值
print("--- 拷后字段验证 ---")
local checks = {
    {0x0008, "float1"},
    {0x0400, "PA_main"},
    {0x0618, "PA_data"},
    {0x0702, "speed_f"},
    {0x0758, "PA_triplet"},
    {0x0720, "fake_AI_ptr(应不变)"},
}
for _, c in ipairs(checks) do
    local ok3, v = pcall(pa_read_f32, fake, c[1])
    print(string.format("  +0x%04X %s: %s", c[1], c[2], tostring(ok3 and v or "ERR")))
end

print("=== 完成。去 log 看细节。试试 fake 会不会自己有反应 ===")
