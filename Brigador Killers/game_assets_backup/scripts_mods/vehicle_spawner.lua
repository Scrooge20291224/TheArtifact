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

-- 引入 Dialogue 模块，用来在 Lua 里直接注册 storylet（不依赖 JSON）
local Dialogue = require "assets.scripts.lib.dialogue"

local DEFAULT_VEHICLE = "assets/data/vics/units/rig_volta_carmine_01.json"
-- loadout 是可选参数：不传时引擎会读取单位 JSON 的 default_loadout。
-- 注意空串 "" 不等于"不传"，可能被当成显式空 loadout 顶掉默认值，
-- 所以这里保持 nil，并在调用时按需省略第 6 个参数。
local DEFAULT_LOADOUT = nil
local DEFAULT_DISTANCE = 3.0

-- 这两个必须在任何使用它们的函数之前声明成 local，
-- 否则后面的函数会读到同名的全局变量（nil），team/behavior 设置永远不生效。
local _vs_team = nil
local _vs_behavior = nil
local _vs_loadout = nil
local _vs_dialogue = "mods_companion-00"

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
local function behavior_normal()
    if BEHAVIOR then
        return BEHAVIOR.BEHAVIOR_NORMAL or BEHAVIOR.NORMAL or 1
    end
    return 1
end

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

local function spawn_and_enter(vehicle_path, x, y, orient, loadout)
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

    local use_team = _vs_team or civilian_team()
    local use_behavior = _vs_behavior or behavior_null()
    local use_loadout = _vs_loadout or loadout or DEFAULT_LOADOUT

    -- loadout 为空时只传 5 个参数，让引擎回落到单位的 default_loadout
    local mech
    if use_loadout == nil or use_loadout == "" then
        mech = Mech.Create(vehicle_path, Vec2.New(x, y), orient, use_behavior, use_team)
    else
        mech = Mech.Create(vehicle_path, Vec2.New(x, y), orient, use_behavior, use_team, use_loadout)
    end

    if not mech then
        log("生成失败，检查路径是否存在: " .. tostring(vehicle_path))
        return nil
    end

    log(string.format(
        "已生成 %s 于 (%.2f, %.2f) team=%s behavior=%s loadout=%s",
        vehicle_path, x, y, tostring(use_team), tostring(use_behavior), tostring(use_loadout)
    ))

    -- 用全局变量记录最近生成的队友，避免脚本重载后 register_update 闭包拿不到新值
    __vs_last_mech = mech
    __vs_talked = false
    ensure_auto_talk()

    if try_enter(player, mech) then
        log("玩家已进入载具")
        return mech
    end

    log("自动上车失败（已跳过距离检测），载具留在原地，手动走到边上按 E 上车")
    return mech
end

-- 在玩家正前方生成一辆并上车
function vs_spawn(vehicle_path, distance, loadout)
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
        face,
        loadout
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

-- 弹出模态对话框。
-- 引擎对话框由 C++ 渲染，读 assets/scripts/data/dialogue_data/*.json 里的 storylet。
-- 我们的 mods_companion-XX 已写进 dialogue.json（exe 唯一硬编码加载的文件），
-- 所以这里直接用引擎全局 open_dialogue。
function vs_talk(name)
    name = name or _vs_dialogue

    if not open_dialogue then
        log("当前 VM 没有 open_dialogue")
        return false
    end

    local ok, err = pcall(open_dialogue, name)
    if ok then
        log("已请求弹出对话框: " .. name)
        return true
    end

    log("对话框打开失败: " .. tostring(err))
    return false
end

-- 让最近的同伴喊话（气泡/语音，不是对话框）
function vs_speak(name)
    name = name or _vs_dialogue
    local m = __vs_last_mech
    if m and m:Valid() then
        local ok = pcall(function()
            m:Speak(name)
        end)
        if ok then
            log("同伴喊话: " .. name)
            return true
        end
    end
    log("喊话失败: " .. tostring(name))
    return false
end

-- 玩家靠近队友时自动触发一次对话（只注册一次）
function ensure_auto_talk()
    if _G.__vs_auto_talk_registered then
        return
    end
    _G.__vs_auto_talk_registered = true

    register_update_function(function(_)
        if __vs_talked then
            return
        end

        local m = __vs_last_mech
        if not m or not m:Valid() then
            return
        end

        local p = get_player()
        if not p then
            return
        end

        -- vs_spawn 会把玩家塞进载具，此时 m 就是玩家自己，别自言自语
        if m == p then
            return
        end

        local px, py = p:GetPosition()
        local mx, my = m:GetPosition()
        local dx, dy = mx - px, my - py
        if dx * dx + dy * dy <= 9 then
            if vs_talk() then
                __vs_talked = true
            end
        end
    end)
end

-- ===== 独立 NPC 同伴系统 =====
-- Mech 没有交互组件，按 E 对话是关卡 console 对象专有的能力，
-- 纯 Lua 做不到。这里改用官方 Holger 的配方：
--   Mech.Create(..., BEHAVIOR_CIVILIAN, TEAMS.CIVILIAN_TEAM) + 脚本 MoveTo 跟随
-- 靠距离触发 Speak，等效于"走到旁边他就开口"。
--
-- 状态挂在 _G 上：luaload 重载脚本时旧 update 闭包仍在跑，
-- 用 local 会读到新 chunk 的 nil，导致跟随/说话失效。
local _vs_companion_sentences = {
    "mods_companion-00",
    "mods_companion-01",
    "mods_companion-02",
}

-- 每次 luaload 都会注册一个新的 update，并用「代号」让旧的自动失效。
-- 不能再用 bool 防重：旧标志一旦为 true，重载后新代码永远注册不上，
-- 而旧闭包读的是旧 chunk 的 local（nil），表现就是既不跟随也不说话。
local function register_companion_update()
    _G.__vs_companion_gen = (_G.__vs_companion_gen or 0) + 1
    local my_gen = _G.__vs_companion_gen

    register_update_function(function(time)
        if _G.__vs_companion_gen ~= my_gen then
            return
        end

        -- 暂停时不发任何新指令，避免覆盖手动 Halt 的结果
        if _G.__vs_companion_paused then
            return
        end

        local list = _G.__vs_companions
        if not list or #list == 0 then
            return
        end

        local p = get_player()
        if not p or not p:Valid() then
            return
        end

        local px, py = p:GetPosition()
        local t = (time and time.totalWall) or 0

        -- 清理已失效的同伴
        local alive = {}
        for i = 1, #list do
            local m = list[i]
            if m and m:Valid() then
                alive[#alive + 1] = m
            end
        end
        _G.__vs_companions = alive
        list = alive

        -- 所有同伴独立跟随
        local talker = nil
        for i = 1, #list do
            local m = list[i]
            local mx, my = m:GetPosition()
            local dx, dy = mx - px, my - py
            local dist2 = dx * dx + dy * dy

            local follow = _G.__vs_companion_follow
            if follow == nil then
                follow = true
            end

            if follow then
                -- 跟随距离可调：默认 8 单位。
                -- 队友有 NORMAL 索敌 AI，会自己追出去打；阈值太小会不停打断交火。
                -- 用 vs_companion_range(30) 放宽，让它能跑远点打架。
                local follow_range = _G.__vs_companion_range or 8
                if dist2 > follow_range * follow_range then
                    -- 目标是"玩家周围 6 单位处"，不是玩家脚点。
                    -- 否则 NPC 会自己贴脸，变成被动触发对话。
                    local len = math.sqrt(dist2)
                    local gx = px + (dx / len) * 6
                    local gy = py + (dy / len) * 6
                    m:MoveTo(Vec2.New(gx, gy))
                end
            else
                -- 非跟随模式：主动与玩家保持距离。
                -- 玩家进入 10 单位内就退到 16 单位外。
                if dist2 < 100 then
                    local len = math.sqrt(dist2)
                    if len < 0.001 then
                        len = 0.001
                        dx = 1
                        dy = 0
                    end
                    local gx = px + (dx / len) * 16
                    local gy = py + (dy / len) * 16
                    m:MoveTo(Vec2.New(gx, gy))
                end
            end

            -- 必须几乎叠在一起（约 1.4 单位）才触发，等同"撞上"。
            -- 每个同伴触发后上锁，离开 5 单位才解锁，避免贴着反复弹个没完。
            local mid = i
            if m.GetID then
                local ok, id = pcall(function()
                    return m:GetID()
                end)
                if ok and id then
                    mid = id
                end
            end

            _G.__vs_talk_latch = _G.__vs_talk_latch or {}

            if _G.__vs_talk_latch[mid] then
                if dist2 > 25 then
                    _G.__vs_talk_latch[mid] = nil
                end
            elseif dist2 <= 2 then
                _G.__vs_talk_latch[mid] = true
                if not talker then
                    talker = m
                end
            end
        end

        -- 全局冷却：一次只弹一个对话框，避免多个同伴同时刷屏
        if talker and t >= (_G.__vs_companion_next_talk or 0) then
            _G.__vs_companion_next_talk = t + 5
            _G.__vs_companion_idx = ((_G.__vs_companion_idx or 0) % #_vs_companion_sentences) + 1
            vs_talk(_vs_companion_sentences[_G.__vs_companion_idx])
        end
    end)
end

-- 生成一个独立 NPC 同伴（不抢玩家座位），会跟随并在靠近时弹对话框
function vs_spawn_companion(vehicle_path)    -- 默认是红甲 Rig Carmine
    vehicle_path = vehicle_path or DEFAULT_VEHICLE

    local p = get_player()
    if not p then
        log("找不到玩家单位，无法生成同伴")
        return nil
    end

    local px, py = p:GetPosition()
    local face = p:GetOrient() or 0
    local x = px + math.cos(face) * 4
    local y = py + math.sin(face) * 4

    -- 队友用玩家队，避免被当成敌人；NORMAL 行为才响应 MoveTo 跟随。
    -- 平民行为（CIVILIAN）不会执行跟随指令。
    local bh = (BEHAVIOR and BEHAVIOR.BEHAVIOR_NORMAL) or 1
    local tm = (TEAMS and TEAMS.PLAYER_TEAM) or 0

    local m = Mech.Create(vehicle_path, Vec2.New(x, y), face, bh, tm)
    if not m then
        log("同伴生成失败，检查路径: " .. tostring(vehicle_path))
        return nil
    end

    m:SetName("Companion")
    _G.__vs_companions = _G.__vs_companions or {}
    table.insert(_G.__vs_companions, m)
    _G.__vs_companion_mech = m
    _G.__vs_companion_idx = 1
    -- 生成时已弹过 00，下一句至少 5 秒后
    local now = 0
    if get_time then
        local ok, tt = pcall(get_time)
        if ok and tt and tt.totalWall then
            now = tt.totalWall
        end
    end
    _G.__vs_companion_next_talk = now + 5
    __vs_last_mech = m
    __vs_talked = false

    register_companion_update()
    log(string.format("同伴已生成于 (%.1f, %.1f)，会跟随你，靠近时弹对话框", x, y))

    -- 生成后立即弹一次开场白
    vs_talk("mods_companion-00")

    return m
end

-- ===== 实验：behavior=PLAYER 的独立单位 =====
-- 已验证：
--   * MoveTo 可立即覆盖之前的游荡 AI，等效于"抢占控制"
--   * Halt 无效，但 MoveTo 当前位置可替代停住
--   * GetPlayer() 不指向它，不会抢玩家相机/输入
-- 尚未验证：team=0 时敌人是否会打它、它是否会反击

function vs_spawn_fake_player(vehicle_path)
    vehicle_path = vehicle_path or DEFAULT_VEHICLE
    local p = get_player()
    if not p then
        log("找不到玩家")
        return nil
    end

    local px, py = p:GetPosition()
    local face = p:GetOrient() or 0
    local x = px + math.cos(face + math.pi * 0.5) * 4
    local y = py + math.sin(face + math.pi * 0.5) * 4

    local m = Mech.Create(vehicle_path, Vec2.New(x, y), face, 0, 0)
    if not m then
        log("生成失败，检查路径: " .. tostring(vehicle_path))
        return nil
    end

    m:SetName("FakePlayer")
    _G.__vs_fake_player = m
    log(string.format("已生成 BEHAVIOR_PLAYER 单位于 (%.1f,%.1f)，ID=%s",
        x, y, tostring(m:GetID())))
    log("GetPlayer() 是否指向它 = " .. tostring(p:GetID() == m:GetID()))
    log("可用 MoveTo 抢占控制；停住请 MoveTo 它当前位置")
    return m
end

function vs_fake_status()
    local m = _G.__vs_fake_player
    if not m then
        log("没有 fake player 记录")
        return
    end
    if not m:Valid() then
        log("fake player 已失效")
        return
    end
    local mx, my = m:GetPosition()
    local px, py = 0, 0
    local p = get_player()
    if p then
        px, py = p:GetPosition()
    end
    log(string.format("FakePlayer=(%.1f,%.1f) 玩家=(%.1f,%.1f) 距离=%.1f",
        mx, my, px, py, math.sqrt((mx - px) * (mx - px) + (my - py) * (my - py))))
    if p then
        log("GetPlayer() 是否指向它 = " .. tostring(p:GetID() == m:GetID()))
    end
end

-- 测试 1：MoveTo（AI 指令层，可立即覆盖游荡）
function vs_fake_move(x, y)
    local m = _G.__vs_fake_player
    if not m or not m:Valid() then
        log("没有有效的 fake player")
        return false
    end
    if not x then
        local p = get_player()
        local px, py = p:GetPosition()
        x, y = px + 8, py
    end
    m:MoveTo(Vec2.New(x, y))
    local mx, my = m:GetPosition()
    log(string.format("MoveTo(%.1f,%.1f) 已下发，当前位置 (%.1f,%.1f)", x, y, mx, my))
    return true
end

-- 替代 Halt：把目标设为当前位置即可"停住"
function vs_fake_stop()
    local m = _G.__vs_fake_player
    if not m or not m:Valid() then
        log("没有有效的 fake player")
        return false
    end
    local mx, my = m:GetPosition()
    m:MoveTo(Vec2.New(mx, my))
    log(string.format("已发送 MoveTo 当前位置 (%.1f,%.1f)，应停住", mx, my))
    return true
end

-- 测试 3：SetPosition（物理层强制位移，绕过 AI）
function vs_fake_teleport(dx, dy)
    local m = _G.__vs_fake_player
    if not m or not m:Valid() then
        log("没有有效的 fake player")
        return false
    end
    local mx, my = m:GetPosition()
    m:SetPosition(Vec2.New(mx + (dx or 5), my + (dy or 0)))
    local nx, ny = m:GetPosition()
    log(string.format("SetPosition -> (%.1f,%.1f)", nx, ny))
    return true
end

-- 实验 B：NORMAL 行为 + team=0
-- 目的：验证 NORMAL 索敌 AI 是否把 team=1 当敌人、是否会自动开火
function vs_spawn_combat_friend(vehicle_path)
    vehicle_path = vehicle_path or DEFAULT_VEHICLE
    local p = get_player()
    if not p then
        log("找不到玩家")
        return nil
    end

    local px, py = p:GetPosition()
    local face = p:GetOrient() or 0
    local x = px + math.cos(face + math.pi * 0.5) * 5
    local y = py + math.sin(face + math.pi * 0.5) * 5

    -- Mech.Create(resource, pos, orient, behavior, team)
    -- behavior=1 (NORMAL), team=0 (PLAYER)
    local m = Mech.Create(vehicle_path, Vec2.New(x, y), face, 1, 0)
    if not m then
        log("生成失败")
        return nil
    end

    m:SetName("CombatFriend")
    _G.__vs_combat_friend = m
    log(string.format("已生成 BEHAVIOR_NORMAL+team=0 单位于 (%.1f,%.1f)", x, y))
    log("进战斗场景，把它 MoveTo 敌人附近，观察是否自动开火")
    return m
end

-- ===== 实验 C：DisableAI + MoveTo 组合 =====
-- 目的：验证 DisableAI 关掉游荡 AI 后，MoveTo 是否仍能驱动 fake player
-- 如果成立 → 得到"脚本完全控，引擎只负责物理/渲染/碰撞"的理想状态
function vs_spawn_driven(vehicle_path)
    vehicle_path = vehicle_path or DEFAULT_VEHICLE
    local p = get_player()
    if not p then log("找不到玩家"); return nil end

    local px, py = p:GetPosition()
    local face = p:GetOrient() or 0
    local x = px + math.cos(face + math.pi * 0.5) * 6
    local y = py + math.sin(face + math.pi * 0.5) * 6

    local m = Mech.Create(vehicle_path, Vec2.New(x, y), face, 0, 0)
    if not m then log("生成失败"); return nil end

    -- 立即关掉游荡 AI
    if m.DisableAI then
        m:DisableAI()
        log("已 DisableAI() — 游荡 AI 应该停了")
    else
        log("警告：DisableAI 方法不存在")
    end

    m:SetName("Driven")
    _G.__vs_driven = m
    log(string.format("已生成 DRIVEN 单位于 (%.1f,%.1f)", x, y))
    log("等 5 秒看它还会不会自己走动；然后 vs_driven_move() 验证 MoveTo 是否仍生效")
    return m
end

function vs_driven_move(x, y)
    local m = _G.__vs_driven
    if not m or not m:Valid() then log("没有有效的 Driven 单位"); return false end
    if not x then
        local p = get_player(); local px, py = p:GetPosition()
        x, y = px + 10, py
    end
    m:MoveTo(Vec2.New(x, y))
    local mx, my = m:GetPosition()
    log(string.format("MoveTo(%.1f,%.1f) 已下发，当前 (%.1f,%.1f)", x, y, mx, my))
    return true
end

function vs_driven_look(tx, ty)
    local m = _G.__vs_driven
    if not m or not m:Valid() then log("没有有效的 Driven 单位"); return false end
    m:Look(Vec2.New(tx, ty))
    log(string.format("Look(%.1f,%.1f) 已下发", tx, ty))
    return true
end

-- 打断所有同伴当前的移动指令并暂停跟随
function vs_companion_halt()
    _G.__vs_companion_paused = true
    local list = _G.__vs_companions or {}
    local n = 0
    for i = 1, #list do
        local m = list[i]
        if m and m:Valid() then
            m:Halt()
            n = n + 1
        end
    end
    log("已打断 " .. n .. " 个同伴的移动指令，跟随已暂停（vs_companion_resume 恢复）")
    return n
end

-- 恢复同伴跟随/对话逻辑
function vs_companion_resume()
    _G.__vs_companion_paused = false
    log("同伴逻辑已恢复")
end

-- 开关队友跟随模式
-- 用法: lua vs_companion_follow()       -- 切换
--       lua vs_companion_follow(true)   -- 开启跟随
--       lua vs_companion_follow(false)  -- 关闭跟随（主动保持距离）
function vs_companion_follow(on)
    if on == nil then
        local cur = _G.__vs_companion_follow
        if cur == nil then
            cur = true
        end
        on = not cur
    end
    _G.__vs_companion_follow = on and true or false
    log("队友跟随模式: " .. (_G.__vs_companion_follow and "开（跟随玩家）" or "关（主动保持距离）"))
    return _G.__vs_companion_follow
end

-- 设置队友的跟随距离（单位）。队友有索敌 AI，会追出去打；
-- 阈值太小会不停把它拽回来，导致交火中断。
--   lua vs_companion_range(30)   -- 放宽到 30 单位，让它能跑远点打
--   lua vs_companion_range()     -- 查看当前值
function vs_companion_range(units)
    if units == nil then
        log("当前跟随距离 = " .. tostring(_G.__vs_companion_range or 8) .. " 单位")
        return _G.__vs_companion_range or 8
    end
    if type(units) ~= "number" or units <= 0 then
        log("参数必须是正数（单位）")
        return
    end
    _G.__vs_companion_range = units
    log("队友跟随距离设为 " .. tostring(units) .. " 单位")
    return units
end

-- 诊断同伴状态（跟不跟、距离多少、update 代号）
function vs_companion_status()
    local list = _G.__vs_companions or {}
    local p = get_player()
    if not p then
        log("找不到玩家")
        return
    end
    local px, py = p:GetPosition()
    log(string.format("同伴数量=%d gen=%s next_talk=%s 玩家=(%.1f,%.1f)",
        #list, tostring(_G.__vs_companion_gen), tostring(_G.__vs_companion_next_talk), px, py))
    for i = 1, #list do
        local m = list[i]
        if m and m:Valid() then
            local mx, my = m:GetPosition()
            local d = math.sqrt((mx - px) * (mx - px) + (my - py) * (my - py))
            log(string.format("  [%d] %s 位置=(%.1f,%.1f) 距离=%.1f",
                i, tostring(m:GetResourcePath()), mx, my, d))
        else
            log(string.format("  [%d] 已失效", i))
        end
    end
end

function vs_set_dialogue(name)
    _vs_dialogue = name
    log("队友对话句: " .. tostring(name))
end

-- 动态注册一个新的 storylet（在控制台随时可以加新句子）
-- 用法: lua vs_add_storylet("hello", "Hi there!", "CAVALIER")
function vs_add_storylet(name, text, display_name)
    if not Dialogue then
        log("Dialogue 模块不可用")
        return false
    end
    name = name or ("mods_" .. math.random(10000))
    text = text or "..."
    display_name = display_name or "CAVALIER"

    local ok, err = pcall(function()
        Dialogue({
            name = name,
            text = text,
            speaker_name = "",
            portrait = "",
            remote = false,
            sound = "",
            begin_callback = "",
            duration = 5,
            end_callback = "",
            response = "",
            theme_path = "assets/data/ui/dialogue/theme_default.json",
            display_name = display_name,
            freeze_player = false,
        })
    end)

    if ok then
        log("已注册 storylet: " .. name .. ' = "' .. text .. '"')
        return true
    else
        log("注册失败: " .. tostring(err))
        return false
    end
end

-- ==== 载具参数热改 ====
-- 原理：io 读写 legs JSON → 正则替换字段 → cmd("reload", "player") 重载
-- 首次修改前自动备份到 <path>.vsbak，可用 vs_tune_restore 还原。

local function vs_fs_read(path)
    local f = io and io.open(path, "rb")
    if not f then
        return nil
    end
    local s = f:read("*a")
    f:close()
    return s
end

local function vs_fs_write(path, content)
    local f = io and io.open(path, "wb")
    if not f then
        return false
    end
    f:write(content)
    f:close()
    return true
end

-- 探测 io / 写权限 / reload 命令是否可用
function vs_tune_probe()
    log("io = " .. tostring(io))
    log("io.open = " .. tostring(io and io.open))
    log("loadfile = " .. tostring(loadfile))
    log("pack_read = " .. tostring(pack_read))
    log("JsonDecode = " .. tostring(rawget(_G, "JsonDecode")))
    log("JsonEncode = " .. tostring(rawget(_G, "JsonEncode")))

    local legs = "assets/data/vics/lowers/rig_volta_carmine_01_lo.json"
    local s = vs_fs_read(legs)
    log("直接读 " .. legs .. " = " .. (s and ("成功 " .. #s .. " 字节") or "失败"))

    local probe = "assets/scripts/mods/_vs_write_test.txt"
    local ok = vs_fs_write(probe, "ok")
    log("写文件测试 = " .. tostring(ok) .. " -> " .. probe)
end

-- 读取某个数值字段
-- 用法: lua vs_tune_get("assets/data/vics/lowers/rig_volta_carmine_01_lo.json", "max_forward_speed")
function vs_tune_get(path, field)
    local s = vs_fs_read(path)
    if not s then
        log("读不到文件: " .. tostring(path))
        return nil
    end
    local v = s:match('"' .. field .. '"%s*:%s*([-+0-9%.eE]+)')
    log(string.format("%s = %s", tostring(field), tostring(v)))
    return tonumber(v)
end

-- 修改某个数值字段并重载玩家载具
-- 用法: lua vs_tune_set("assets/data/vics/lowers/rig_volta_carmine_01_lo.json", "max_forward_speed", 2.5)
function vs_tune_set(path, field, value)
    local s = vs_fs_read(path)
    if not s then
        log("读不到文件: " .. tostring(path))
        return false
    end

    -- 首次改动前备份
    if not vs_fs_read(path .. ".vsbak") then
        if vs_fs_write(path .. ".vsbak", s) then
            log("已备份 -> " .. path .. ".vsbak")
        end
    end

    local pat = '("' .. field .. '"%s*:%s*)[-+0-9%.eE]+'
    local new, n = s:gsub(pat, function(prefix)
        return prefix .. tostring(value)
    end)

    if n == 0 then
        log("文件里找不到字段: " .. tostring(field))
        return false
    end

    if not vs_fs_write(path, new) then
        log("写入失败: " .. tostring(path))
        return false
    end

    log(string.format("已修改 %s = %s（%d 处）", tostring(field), tostring(value), n))
    if cmd then
        cmd("reload", "player")
        log("已执行 reload player")
    end
    return true
end

-- 从 .vsbak 还原
function vs_tune_restore(path)
    local b = vs_fs_read(path .. ".vsbak")
    if not b then
        log("没有备份: " .. tostring(path))
        return false
    end
    if not vs_fs_write(path, b) then
        log("恢复失败: " .. tostring(path))
        return false
    end
    log("已还原: " .. path)
    if cmd then
        cmd("reload", "player")
    end
    return true
end

function vs_help()
    log([[
命令：
  vs_spawn([载具路径], [距离], [loadout路径])  生成并上车
  vs_spawn_companion([载具路径])        生成独立 NPC 同伴（跟随+靠近自动弹对话框）
  vs_companion_status()                打印同伴位置/距离/update 状态
  vs_companion_follow([true/false])    开关跟随（关=主动与玩家保持距离）
  vs_companion_halt()                  打断所有同伴移动指令并暂停跟随
  vs_companion_resume()                恢复同伴跟随/对话
  --- 实验：behavior=PLAYER 独立单位 ---
  vs_spawn_fake_player([载具路径])     生成 behavior=0 team=0 的独立单位
  vs_fake_status()                     打印它的位置/距离/是否被 GetPlayer 认领
  vs_fake_move([x, y])                 对它下发 MoveTo（默认玩家右侧 8 单位）
  vs_fake_halt()                       对它 Halt
  vs_fake_teleport([dx, dy])           物理层强制位移（验证脚本是否完全可控）
  vs_spawn_player_team([载具路径])     玩家 team + NORMAL AI
  vs_spawn_enemy([载具路径])           敌人 team + NORMAL AI
  vs_spawn_at_cursor([载具路径])       鼠标位置生成（用当前 team/behavior）
  vs_set_team(n) / vs_set_behavior(n)  手动设置下次 spawn 参数
  vs_set_loadout(路径)                 设置下次 spawn 的 loadout（空串=用单位自带）
  vs_talk([句子名])                    弹出对话框（最近同伴 / 指定 storylet）
  vs_speak([句子名])                   让同伴喊话（气泡/语音，不是对话框）
  vs_set_dialogue(句子名)              换一句默认对话
  vs_add_storylet(name, text, [名字])  动态注册新对话句
  vs_dump_mech()                       打印 Mech 全部方法（查 AI/team 接口）
  vs_debug()                           打印接口与坐标诊断
  vs_tune_probe()                      探测 io 读写 / reload 命令是否可用
  vs_tune_get(路径, 字段)              读取 legs JSON 里的数值
  vs_tune_set(路径, 字段, 值)          改数值 + reload player（自动备份 .vsbak）
  vs_tune_restore(路径)                从 .vsbak 还原
  默认载具：]] .. DEFAULT_VEHICLE .. [[

TEAMS: PLAYER=0 ENEMY=1 CIVILIAN=2
BEHAVIOR: PLAYER=0 NORMAL=1 CIVILIAN=4 NULL=8
注意：Mech 没有交互组件，按 E 对话是关卡 console 对象专有，
      纯 Lua 给 Mech 加不了；同伴用"靠近自动说话"替代。
]])
end

-- 打印 Mech 类和玩家实例上的全部方法，用来找 AI/team 相关接口
function vs_dump_mech()
    local keys = {}
    if Mech then
        for k, v in pairs(Mech) do
            if type(k) == "string" then
                keys[#keys + 1] = string.format("Mech.%s (%s)", k, type(v))
            end
        end
    end
    local p = get_player()
    if p then
        local mt = getmetatable(p)
        local methods = mt and (mt.__index or mt)
        if type(methods) == "table" then
            for k, v in pairs(methods) do
                if type(k) == "string" then
                    keys[#keys + 1] = string.format("mech:%s (%s)", k, type(v))
                end
            end
        end
    end
    table.sort(keys)
    log("=== Mech 接口 ===\n" .. table.concat(keys, "\n"))
end

-- 加载时自动 dump 关键常量（控制台会截断长命令，所以放脚本里跑）
local function auto_dump()
    local function dump_table(name, t, keys)
        if not t then
            log(name .. " = nil")
            return
        end
        if keys then
            for _, k in ipairs(keys) do
                log(string.format("  %s.%s = %s", name, k, tostring(t[k])))
            end
        else
            for k, v in pairs(t) do
                log(string.format("  %s.%s = %s", name, k, tostring(v)))
            end
        end
    end

    log("=== 常量自动 dump ===")
    dump_table("TEAMS", TEAMS)
    dump_table("BEHAVIOR", BEHAVIOR)
    if TEAMS then
        vs_set_team(TEAMS.CIVILIAN_TEAM)
    end
    log("===================")
end

-- 设置下次 spawn 用的 team / behavior
function vs_set_team(team)
    _vs_team = team
    log("下次 spawn 使用 team = " .. tostring(team))
end
function vs_set_behavior(bh)
    _vs_behavior = bh
    log("下次 spawn 使用 behavior = " .. tostring(bh))
end
function vs_set_loadout(path)
    _vs_loadout = path
    log("下次 spawn 使用 loadout = " .. tostring(path))
end

-- 以玩家方 team + NORMAL AI 生成会打敌人的友军
function vs_spawn_player_team(vehicle_path)
    if not TEAMS or not TEAMS.PLAYER_TEAM then
        log("TEAMS.PLAYER_TEAM 不可用")
        return nil
    end
    local old_team, old_bh = _vs_team, _vs_behavior
    _vs_team = TEAMS.PLAYER_TEAM
    _vs_behavior = behavior_normal()
    local r = vs_spawn(vehicle_path)
    _vs_team, _vs_behavior = old_team, old_bh
    return r
end

-- 以敌方 team 生成（测试用）
function vs_spawn_enemy(vehicle_path)
    if not TEAMS or not TEAMS.ENEMY_TEAM then
        log("TEAMS.ENEMY_TEAM 不可用")
        return nil
    end
    local old_team, old_bh = _vs_team, _vs_behavior
    _vs_team = TEAMS.ENEMY_TEAM
    _vs_behavior = behavior_normal()
    local r = vs_spawn(vehicle_path)
    _vs_team, _vs_behavior = old_team, old_bh
    return r
end

-- 在 Lua 里直接注册 storylet（不依赖 JSON 文件，绕过引擎固定加载列表）
-- 全局函数：vs_talk 在调用前会再跑一次，防止章节/脚本重载后 DialogueSystem 被清空。
local _vs_storylet_texts = {
    { "mods_companion-00", "Commander, I'm right here. Just say the word." },
    { "mods_companion-01", "Nice ride. Where are we headed?" },
    { "mods_companion-02", "Taking fire! Keep your head down." },
}

function vs_register_storylets()
    if not Dialogue then
        log("Dialogue 模块不可用，跳过 storylet 注册")
        return
    end

    for _, line in ipairs(_vs_storylet_texts) do
        local name, text = line[1], line[2]

        -- 直接覆盖注册，避免 GetStorylet 找不到时刷 "Unkown dialogue"
        local ok, err = pcall(function()
            Dialogue({
                name = name,
                text = text,
                speaker_name = "",
                portrait = nil,
                remote = false,
                sound = nil,
                begin_callback = "",
                duration = 5,
                end_callback = "",
                response = "",
                theme_path = "assets/data/ui/dialogue/theme_default.json",
                display_name = "dname.buddy",
                freeze_player = false,
            })
        end)
        if not ok then
            log("storylet " .. name .. " 注册失败: " .. tostring(err))
        end
    end
end

auto_dump()
vs_register_storylets()
log("已加载，输入 lua vs_help() 查看用法")
