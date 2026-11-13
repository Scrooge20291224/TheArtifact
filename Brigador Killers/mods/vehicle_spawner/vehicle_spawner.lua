-- Brigador Killers 载具生成器（纯 Lua Mod）
-- 作用：在关卡里凭空生成一台载具，并让玩家直接坐进去开走。
-- 原理：Mech.Create 生成单位 + Mech:GetInto 让玩家上车，
--       与游戏自带的 assets/scripts/level_objects/offscreen_action.lua 同一套调用。
--
-- 安装位置（游戏目录）：
--   assets/scripts/mods/vehicle_spawner.lua
--
-- 控制台用法（先开控制台）：
--   1) 加载脚本（二选一）
--        luaload assets/scripts/mods/vehicle_spawner.lua
--        lua require("assets.scripts.mods.vehicle_spawner")
--   2) 生成并上车
--        lua vs_spawn()
--        lua vs_spawn("assets/data/vics/units/rig_volta_carmine_01.json")
--        lua vs_spawn_at_cursor("assets/data/vics/units/car_civ_panelvan_upgun.json")
--        lua vs_debug()
--        lua vs_help()

local DEFAULT_VEHICLE = "assets/data/vics/units/rig_volta_carmine_01.json"
local DEFAULT_LOADOUT = "assets/data/loadouts/ldt_null.json"
local DEFAULT_DISTANCE = 3.0

local function log(msg)
    print("[载具生成器] " .. tostring(msg))
end

local function get_player()
    local p = Mech.GetPlayer()
    if p and p:Valid() then
        return p
    end
    return nil
end

-- Mech.Create 的第 4、5 个参数在游戏脚本里实际是 (behavior, team)，
-- 虽然 bindingstubs.lua 的注释写的是 (team, behavior)，这里以实际脚本为准。
local function behavior_null()
    if BEHAVIOR then
        return BEHAVIOR.BEHAVIOR_NULL or BEHAVIOR.NULL or 8
    end
    return 8
end

local function civilian_team()
    if TEAMS then
        return TEAMS.CIVILIAN_TEAM or 2
    end
    return 2
end

-- 玩家上车。游戏内有两种调用形式，逐个试，跳过距离检测（false）。
local function try_enter(passenger, mech)
    local ok, res = pcall(function()
        return passenger:GetInto(mech, false)
    end)
    if ok and res then
        return true
    end

    ok, res = pcall(function()
        return passenger:GetInto(mech, "", false)
    end)
    if ok and res then
        return true
    end

    return false
end

local function spawn_and_enter(vehicle_path, x, y, orient)
    vehicle_path = vehicle_path or DEFAULT_VEHICLE

    local player = get_player()
    if not player then
        log("找不到玩家单位，无法生成载具")
        return nil
    end

    local px, py = player:GetPosition()
    local face = player:GetOrient() or 0

    if x == nil or y == nil then
        x = px + math.cos(face) * DEFAULT_DISTANCE
        y = py + math.sin(face) * DEFAULT_DISTANCE
        orient = orient or face
    end
    orient = orient or 0

    local mech = Mech.Create(
        vehicle_path,
        Vec2.New(x, y),
        orient,
        behavior_null(),
        civilian_team(),
        DEFAULT_LOADOUT
    )

    if not mech then
        log("生成失败，检查路径是否存在: " .. tostring(vehicle_path))
        return nil
    end

    log(string.format("已生成 %s 于 (%.2f, %.2f)", vehicle_path, x, y))

    if try_enter(player, mech) then
        log("玩家已进入载具")
        return mech
    end

    log("自动上车失败（已跳过距离检测），载具留在原地，手动走到边上按 E 上车")
    return mech
end

-- 在玩家正前方生成一辆并上车
function vs_spawn(vehicle_path, distance)
    local player = get_player()
    if not player then
        log("找不到玩家单位")
        return nil
    end

    distance = distance or DEFAULT_DISTANCE
    local px, py = player:GetPosition()
    local face = player:GetOrient() or 0
    return spawn_and_enter(
        vehicle_path,
        px + math.cos(face) * distance,
        py + math.sin(face) * distance,
        face
    )
end

-- 在鼠标位置生成并上车（若 get_mouse_position 返回的不是世界坐标，坐标会明显偏大，先跑 vs_debug 确认）
function vs_spawn_at_cursor(vehicle_path)
    if not get_mouse_position then
        log("当前 VM 没有 get_mouse_position，改为在玩家前方生成")
        return vs_spawn(vehicle_path)
    end

    local ok, mx, my = pcall(get_mouse_position)
    if not ok or type(mx) ~= "number" or type(my) ~= "number" then
        log("get_mouse_position 返回无效 (" .. tostring(mx) .. ", " .. tostring(my) .. ")，改为在玩家前方生成")
        return vs_spawn(vehicle_path)
    end

    return spawn_and_enter(vehicle_path, mx, my)
end

-- 诊断：打印当前 VM 里这些接口是否存在、鼠标坐标长什么样
function vs_debug()
    local lines = {}
    local function add(k, v)
        lines[#lines + 1] = string.format("  %s = %s", k, tostring(v))
    end

    add("Mech.Create", type(Mech and Mech.Create))
    add("Mech.GetPlayer", type(Mech and Mech.GetPlayer))
    add("change_player_base", type(change_player_base))
    add("get_mouse_position", type(get_mouse_position))
    add("get_mouse_position_canvas", type(get_mouse_position_canvas))
    add("Screen.ToCanvas", type(Screen and Screen.ToCanvas))

    local player = get_player()
    if player then
        local x, y, z = player:GetPosition()
        add("玩家位置", string.format("(%.2f, %.2f, %.2f)", x, y, z))
        add("玩家朝向", tostring(player:GetOrient()))
        add("玩家载具", tostring(player:GetResourcePath()))
    else
        add("玩家", "未找到")
    end

    if get_mouse_position then
        local ok, mx, my = pcall(get_mouse_position)
        if ok then
            add("鼠标原始坐标", string.format("(%s, %s)", tostring(mx), tostring(my)))
        else
            add("鼠标原始坐标", "调用失败: " .. tostring(mx))
        end
    end

    log("诊断结果:\n" .. table.concat(lines, "\n"))
end

function vs_help()
    log([[
命令：
  vs_spawn([载具路径], [距离])         在玩家前方生成并上车
  vs_spawn_at_cursor([载具路径])       在鼠标位置生成并上车
  vs_debug()                           打印接口与坐标诊断
  默认载具：]] .. DEFAULT_VEHICLE .. [[

示例：
  lua vs_spawn()
  lua vs_spawn("assets/data/vics/units/rig_volta_carmine_01.json", 5)
]])
end

log("已加载，输入 lua vs_help() 查看用法")
