-- pa_test13.lua — 备份 fake → 全拷 → 恢复 fake 自己的组件指针
print("=== pa_test13: FULL copy + restore components ===")

local function load_fn(name)
    local ok, f = pcall(package.loadlib, "pa_probe.dll", name)
    return (type(f) == "function") and f or nil
end

local pa_copy_pa    = load_fn("pa_copy_player_action")
local pa_read_u32   = load_fn("pa_read_u32")
local pa_read_f32   = load_fn("pa_read_f32")

local real = Mech.GetPlayer()
print("玩家 = " .. tostring(real))

local DEFAULT_VEHICLE = "assets/data/vics/units/rig_volta_carmine_01.json"
local rx, ry = real:GetPosition()
local face = real:GetOrient() or 0
local fx, fy = rx + math.cos(face)*5, ry + math.sin(face)*5
local fake = Mech.Create(DEFAULT_VEHICLE, Vec2.New(fx, fy), face, 0, 0)
print("Fake = " .. tostring(fake))

print("\n--- Step 1: 全 memcpy fake = player (v9) ---")
local ok, err = pcall(pa_copy_pa, fake, real)
print("  copy ok=" .. tostring(ok) .. " err=" .. tostring(err))

if ok then
    -- 现在立即恢复 fake 自己的组件!
    -- 从之前的 diff, 组件指针区域是:
    --   +0x0238~+0x0250  (heap ptrs: 组件引用)
    --   +0x04C0~+0x04D0  (team/state dwords)
    --   +0x0500~+0x0660  (大量 heap ptrs: Vehicle/Chassis/Gun/AI 等)
    --   +0x0720          (AI 指针!)
    
    print("\n--- Step 2: 恢复 fake 的组件指针 (防止 AI crash) ---")
    
    -- 重新创建一个 temp fake 来备份组件指针
    -- 或者直接在这里写死要恢复的偏移 (从 diff 来)
    -- 但实际上我们需要另一种方式...
    
    -- 让 DLL 提供: pa_restore_components(fake, backup_ptr)
    -- 或者 Lua 层直接从原始 fake 读...
    
    -- 简单办法: 先 DisableAI 再全拷
    -- 如果 DisableAI 在全拷之后调用已经没用了...
    
    -- 让我们试试: 先 DisableAI 原来的 fake (拷贝前!), 再拷
    -- 不对, 拷贝后 fake 已经不是原来的 fake 了...
    
    print("\n=== 这个脚本只是测试 v9 不调用 MoveTo 会不会自然 crash ===")
    print("等几秒看看 fake 自己会不会崩...")
end
