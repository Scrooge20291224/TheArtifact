-- pa_test16.lua — 3 组对照 + 全局变量 + 位置打印 (可随时复查)
print("=== pa_test16: 客观测量版 ===")

local function load_fn(name)
    local ok, f = pcall(package.loadlib, "pa_probe.dll", name)
    return (type(f) == "function") and f or nil
end

local pa_copy_pa = load_fn("pa_copy_player_action")

local real = Mech.GetPlayer()
local rx, ry = real:GetPosition()
local face = real:GetOrient() or 0
print(string.format("玩家 (%.1f, %.1f) face=%.2f", rx, ry, face))

local VIC = "assets/data/vics/units/rig_volta_carmine_01.json"

-- 记录每组: mech, 目标点
local groups = {}

local function spawn(tag, ox, oy, tx, ty, do_disable, do_copy)
    local f = Mech.Create(VIC, Vec2.New(rx + ox, ry + oy), face, 0, 0)
    if not f then print("!! " .. tag .. " 创建失败") return end
    print(string.format("%s 出生 (%.1f, %.1f)", tag, rx + ox, ry + oy))

    if do_copy then pcall(pa_copy_pa, f, real) end
    if do_disable then pcall(function() f:DisableAI() end) end

    local ok, err = pcall(function() f:MoveTo(Vec2.New(tx, ty)) end)
    print(string.format("  %s copy=%s disable=%s MoveTo=%s %s",
        tag, tostring(do_copy), tostring(do_disable), tostring(ok), tostring(err)))

    groups[#groups + 1] = { tag = tag, mech = f, tx = tx, ty = ty }
    _G["__p16_" .. tag] = f
end

spawn("F1", 10, -5,  rx + 20, ry - 5,  false, true)
spawn("F2", 10,  5,  rx + 20, ry + 5,  true,  true)
spawn("F3",  0, -10, rx,      ry + 10, false, false)

-- 全局函数: 控制台随时调用 __p16_pos() 查看三个 fake 的当前位置
function _G.__p16_pos()
    for _, g in ipairs(groups) do
        local ok, x, y = pcall(function()
            local px, py = g.mech:GetPosition()
            return px, py
        end)
        if ok then
            local dist = math.sqrt((x - g.tx) ^ 2 + (y - g.ty) ^ 2)
            print(string.format("%s 当前 (%.1f, %.1f) 目标 (%.1f, %.1f) 距离 %.1f",
                g.tag, x, y, g.tx, g.ty, dist))
        else
            print(g.tag .. " 读取位置失败: " .. tostring(x))
        end
    end
end

print("\n已生成 3 个 fake。等几秒后控制台输入:")
print("  __p16_pos()")
print("看谁动了、谁没动。")
