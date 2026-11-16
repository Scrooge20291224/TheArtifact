-- pa_test11.lua — 精确拷贝 Player_Action 安全区 (跳过 +0x0230 查找表指针)
print("=== pa_test11: v7 精确安全区拷贝 ===")

local function load_fn(name)
    local ok, f = pcall(package.loadlib, "pa_probe.dll", name)
    return (type(f) == "function") and f or nil
end

local pa_copy_pa  = load_fn("pa_copy_player_action")
local pa_read_u32 = load_fn("pa_read_u32")
local pa_read_f32 = load_fn("pa_read_f32")
local pa_dump     = load_fn("pa_dump")

if not pa_copy_pa then print("!! pa_copy_player_action 缺失") return end

local real = Mech.GetPlayer()
print("玩家 = " .. tostring(real))

-- 读取玩家 type
local pt = pa_read_u32(real, 0x0000)
print("玩家 +0x0000 type = " .. tostring(pt))

local DEFAULT_VEHICLE = "assets/data/vics/units/rig_volta_carmine_01.json"
local rx, ry = real:GetPosition()
local face = real:GetOrient() or 0
local fx, fy = rx + math.cos(face)*5, ry + math.sin(face)*5
local fake = Mech.Create(DEFAULT_VEHICLE, Vec2.New(fx, fy), face, 0, 0)
if not fake then print("!! fake 创建失败") return end
print("Fake = " .. tostring(fake))

-- 读 fake 原始 type
local ft_before = pa_read_u32(fake, 0x0000)
print("Fake 原始 +0x0000 type = " .. tostring(ft_before))

-- === 精确拷贝 Player_Action ===
print("--- 拷贝 Player_Action 安全区 ---")
local ok, err = pcall(pa_copy_pa, fake, real)
print("  copy ok=" .. tostring(ok) .. " err=" .. tostring(err))

if ok then
    -- 验证拷贝结果
    local ft_after = pa_read_u32(fake, 0x0000)
    print("\n--- 拷后验证 ---")
    print("Fake +0x0000 type 变为 = " .. tostring(ft_after) .. " (应为 6)")
    
    local f_0400 = pa_read_f32(fake, 0x0400)
    local r_0400 = pa_read_f32(real, 0x0400)
    print("Fake +0x0400 PA_main = " .. tostring(f_0400) .. " (玩家 = " .. tostring(r_0400) .. ")")
    
    -- 验证 fake 自己的查找表指针没被覆盖 (应该还是 0)
    local f_0230 = pa_read_qword and pa_read_qword(fake, 0x0230) or "unknown"
    print("Fake +0x0230 查找表指针 应仍为 0: " .. tostring(f_0230))
    
    print("\n=== 拷贝完成! 测试 fake ===")
    print("试试在控制台:")
    print("  __vs_fake:DisableAI()  -- 关掉游荡")
    print("  __vs_fake:MoveTo(Vec2.New(" .. string.format("%.1f", rx) .. ", " .. string.format("%.1f", ry+10) .. "))")
    print("观察 fake 会不会走过去/自动开火")
end
