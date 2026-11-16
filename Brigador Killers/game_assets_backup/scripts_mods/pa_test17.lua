-- pa_test17.lua — 极端值验证 0x0700/0x0704/0x0618 到底管什么
print("=== pa_test17: 极端值对照 ===")

local function load_fn(name)
    local ok, f = pcall(package.loadlib, "pa_probe.dll", name)
    return (type(f) == "function") and f or nil
end

local pa_copy_pa   = load_fn("pa_copy_player_action")
local pa_write_f32 = load_fn("pa_write_f32")
local pa_read_f32  = load_fn("pa_read_f32")

local real = Mech.GetPlayer()
local rx, ry = real:GetPosition()
local face = real:GetOrient() or 0
print(string.format("玩家 (%.1f, %.1f)", rx, ry))

local VIC = "assets/data/vics/units/rig_volta_carmine_01.json"
local groups = {}

local function spawn(tag, ox, oy, tx, ty, patch)
    local f = Mech.Create(VIC, Vec2.New(rx + ox, ry + oy), face, 0, 0)
    if not f then print("!! " .. tag .. " 失败") return end
    pcall(pa_copy_pa, f, real)
    if patch then patch(f) end
    pcall(function() f:MoveTo(Vec2.New(tx, ty)) end)
    print(string.format("%s 出生(%.0f,%.0f) 目标(%.0f,%.0f)", tag, rx+ox, ry+oy, tx, ty))
    groups[#groups + 1] = { tag = tag, mech = f, tx = tx, ty = ty }
end

-- A: 0x0700 写成 0.0 (疑似速度/时间系数)
spawn("A_speed0",  15, -12, rx + 115, ry - 12, function(f)
    print("  A: +0x700 = 0.0 (原 " .. tostring(pa_read_f32(f, 0x700)) .. ")")
    pcall(pa_write_f32, f, 0x700, 0.0)
end)

-- B: 0x0700 写成 20.0
spawn("B_speed20", 15,   0, rx + 115, ry,     function(f)
    print("  B: +0x700 = 20.0")
    pcall(pa_write_f32, f, 0x700, 20.0)
end)

-- C: 不动 (对照组, 原值 1.0)
spawn("C_control", 15,  12, rx + 115, ry + 12, function(f)
    print("  C: 保持原值 " .. tostring(pa_read_f32(f, 0x700)))
end)

function _G.__p17_pos()
    for _, g in ipairs(groups) do
        local ok, x, y = pcall(function()
            local px, py = g.mech:GetPosition()
            return px, py
        end)
        if ok then
            local d = math.sqrt((x - g.tx) ^ 2 + (y - g.ty) ^ 2)
            print(string.format("%-9s 当前(%.1f,%.1f) 剩余距离 %.1f", g.tag, x, y, d))
        else
            print(g.tag .. " 位置读取失败")
        end
    end
end

print("\n三个都朝 +100 单位外的远点走。等一下后输入 __p17_pos() 对比剩余距离:")
print("  A(0.0) 不动/B 超快/C 正常 -> 说明 0x700 是速度系数")
print("  三个速度差不多 -> 这字段没用")
