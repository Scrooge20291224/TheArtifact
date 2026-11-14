# Brigador Killers 队友 / 载具生成 Mod

纯 Lua 实现，不修改 exe，不依赖外部 DLL。通过游戏控制台命令生成载具、队友 NPC，并支持靠近弹对话框。

---

## 一、安装

### 1. 前置

- 游戏必须是 **PC 版 Brigador Killers**（Steam）
- 进关卡后需要能用游戏控制台执行 `luaload` / `lua` 命令

### 2. 文件拷贝

把本目录下的文件复制到游戏根目录对应位置（`<游戏根目录>` 一般是
`C:\Program Files (x86)\Steam\steamapps\common\Brigador Killers`）：

| 本目录文件 | 复制到 |
|---|---|
| `vehicle_spawner.lua` | `<游戏根目录>\assets\scripts\mods\vehicle_spawner.lua` |
| `dialogue.json` | `<游戏根目录>\assets\scripts\data\dialogue_data\dialogue.json`（**覆盖**） |

> ⚠️ `dialogue.json` 是**必须覆盖**的。游戏原版这个文件是空的 `{}`，引擎能异步加载的 dialogue 文件只有它一个；我们的对话条目（storylet）写在这里面。不覆盖的话，`vs_talk()` 会报
> `Lua attempted to open a non-existent storylet`。
>
> 原文件备份在 `_gamefiles_backup\dialogue.json`，需要还原时直接拷回去。

### 3. 生效

覆盖 `dialogue.json` 后**必须重启游戏（或至少重进一次关卡）**，引擎只在加载关卡时读该文件。

之后每次进关卡，在控制台执行：

```
luaload assets/scripts/mods/vehicle_spawner.lua
```

看到 `[载具生成器] 已加载，输入 lua vs_help() 查看用法` 即成功。
脚本可以重复 `luaload`，不会重复挂逻辑（内部用代号机制让旧回调失效）。

---

## 二、快速上手

```
luaload assets/scripts/mods/vehicle_spawner.lua
lua vs_help()                    -- 查看全部命令
lua vs_spawn_companion()         -- 生成一个红甲队友（Rig Carmine）
```

生成的队友会：
- 与玩家同队（不会互相攻击）
- 距离超过 8 单位时跟过来，保持在玩家周围 6 单位左右
- 玩家主动贴到约 1.4 单位（撞上）时弹一次对话框
- 说完后必须退开 5 单位以上，才会再次触发（防刷屏）

---

## 三、命令参考

### 生成载具

| 命令 | 说明 |
|---|---|
| `vs_spawn([载具], [距离], [loadout])` | 生成载具并让玩家上车。默认 Team=平民、Behavior=空 AI |
| `vs_spawn_player_team([载具])` | Team=玩家(0)、Behavior=普通 AI |
| `vs_spawn_enemy([载具])` | Team=敌人(1)、Behavior=普通 AI |
| `vs_spawn_at_cursor([载具])` | 在鼠标位置生成 |
| `vs_spawn_companion([载具])` | 生成独立 NPC 队友：跟随 + 靠近弹对话框 |

载具路径默认 `assets/data/vics/units/rig_volta_carmine_01.json`（红甲 Rig Carmine）。
换其它载具直接传路径，例如：

```
lua vs_spawn_companion("assets/data/vics/units/rig_volta_carmine_01.json")
```

### 参数覆盖（影响下一次生成）

| 命令 | 说明 |
|---|---|
| `vs_set_team(n)` | 队伍：0=玩家 1=敌人 2=平民 |
| `vs_set_behavior(n)` | 行为：0=玩家 1=普通 4=平民 8=空 |
| `vs_set_loadout(path)` | 指定 loadout JSON；传空省略则用单位自带默认 |

### 对话

| 命令 | 说明 |
|---|---|
| `vs_talk([句子名])` | 弹出对话框（默认说最近生成的同伴那句） |
| `vs_speak([句子名])` | 让同伴喊话（文字气泡，不是对话框） |
| `vs_set_dialogue(句子名)` | 更换默认对话句 |
| `vs_add_storylet(name, text, [显示名])` | 运行时注册新对话句 |

内置三句：`mods_companion-00` / `-01` / `-02`，靠近队友时按顺序轮换。

### 诊断

| 命令 | 说明 |
|---|---|
| `vs_help()` | 命令列表 |
| `vs_companion_status()` | 所有队友的位置、距离、状态 |
| `vs_companion_follow([true/false])` | 开关跟随模式；不带参数=切换。关闭后队友会主动与玩家保持距离 |
| `vs_companion_halt()` | 打断所有队友当前的移动指令并暂停跟随/对话 |
| `vs_companion_resume()` | 恢复队友跟随/对话逻辑 |
| `vs_dump_mech()` | 打印引擎暴露的全部 Mech 方法 |
| `vs_debug()` | 接口与坐标诊断 |

### 载具参数热改（实验性）

通过改写 legs JSON 并重载玩家载具实现。**会修改游戏原文件**，首次改动前自动生成 `.vsbak` 备份。

| 命令 | 说明 |
|---|---|
| `vs_tune_probe()` | 探测 io 读写 / reload 命令是否可用 |
| `vs_tune_get(路径, 字段)` | 读取数值 |
| `vs_tune_set(路径, 字段, 值)` | 改数值 + `reload player` |
| `vs_tune_restore(路径)` | 从 `.vsbak` 还原 |

示例：

```
lua vs_tune_set("assets/data/vics/lowers/rig_volta_carmine_01_lo.json", "max_forward_speed", 2.5)
lua vs_tune_restore("assets/data/vics/lowers/rig_volta_carmine_01_lo.json")
```

可用字段：`max_forward_speed`、`max_side_speed`、`max_reverse_speed`、
`max_forward_acceleration`、`max_side_acceleration`、`max_steering_angle`、
`friction_coefficient`、`handbrake_friction_coefficient`。

---

## 四、已知限制

1. **玩家队（team=0）的载具不会自主战斗**
   引擎把 team=0 视为玩家槽位，不会跑自主索敌 AI。它会跟随、会被敌人打，但不会主动开火。想要会开枪的队友，只能生成 team=1 的敌人（但它会把玩家当敌人）。

2. **没有 E 键交互**
   `Mech` 没有交互组件，"按 E 对话"是关卡里预置 console 对象的专属能力
   （见官方 `suit_valet.lua`）。纯 Lua 无法给 Mech 动态添加交互组件，所以队友只能靠距离触发对话框。

3. **对话框文字**
   `dialogue.json` 里 `text` 字段目前是文本 key（`mods_companion.hello` 等）。如需换成实际文案，直接把这些 key 改成想要的字符串即可。

4. **修改载具参数的副作用**
   `vs_tune_set` 改的是游戏原始数据文件，所有同型号载具都会受影响。务必用 `vs_tune_restore` 还原。

---

## 五、卸载

1. 删除 `<游戏根目录>\assets\scripts\mods\vehicle_spawner.lua`
2. 把 `_gamefiles_backup\dialogue.json` 拷回
   `<游戏根目录>\assets\scripts\data\dialogue_data\dialogue.json`
3. 如果有 `.vsbak` 文件，执行 `vs_tune_restore` 或手动还原

---

## 六、目录说明

```
vehicle_spawner/
├── vehicle_spawner.lua          # 主脚本
├── dialogue.json                # 覆盖到 assets/scripts/data/dialogue_data/
├── README.md                    # 本文档
├── _gamefiles_backup/           # 被覆盖的游戏原文件备份
│   └── dialogue.json            # 原版（空 {}）
└── data/                        # 早期尝试（引擎不会加载，可删）
    ├── dialogue_data/mods_companion.json
    └── strings/{en,cn_s}/mods_companion.json
```

`data/` 目录是探索阶段留下的，实际不生效——引擎不会扫描新增的 dialogue 文件，对话只能写在 `dialogue.json` 里。保留仅供参考。
