# Brigador Killers — exe 静态逆向笔记（游戏流程机制）

> 目标：用 exe 二进制证据回答"输入→玩家动作→多玩家可行性"。
> 方法：`pefile` + `capstone` 线性反汇编 + IAT/延迟导入交叉引用（REA CLI 当前不可用，见文末）。
> 所有地址为 **RVA**，绝对地址 = `ImageBase 0x140000000 + RVA`。

---

## 1. 二进制基本事实（已观测）

| 项 | 值 |
|---|---|
| 文件 | `brigadorkillers.exe`（5,462,016 字节） |
| 架构 | PE32+ / x86-64 (`Machine 0x8664`)，GUI 子系统 |
| ImageBase | `0x140000000` |
| EntryPoint | RVA `0x3968A0` |
| .text | RVA `0x1000`，虚拟大小 `0x3A9671` |
| .rdata | RVA `0x3AB000` |
| .data | RVA `0x489000`（虚拟大小 `0x732650`，写入区只有 `0x14C00`） |
| 节数 | 7（`.text .rdata .data .pdata _RDATA .rsrc .reloc`） |

---

## 2. 导入面：输入只走 SDL，**exe 内没有任何网络栈**

### 直接导入（383 个）
`ole32(2) dxgi(1) MSVCP140(117) SHELL32(2) USER32(7) KERNEL32(75) IMM32(4) VCRUNTIME140(19) VCRUNTIME140_1(1) + 12 个 api-ms-win-crt-*`

关键观察：
- **USER32 只有 7 个函数，全是剪贴板 / 图标 / SendMessageW**。
  没有 `GetAsyncKeyState` / `GetKeyboardState` / `RegisterRawInputDevices` / `SetWindowsHookEx`。
- **没有 `WS2_32` / `ws2_32` / `WSAStartup` / `socket` / `sendto` / `connect`** → 引擎自身零网络能力。
- KERNEL32 有 `CreateThread / LoadLibraryExA/W / GetProcAddress / VirtualProtect / CreateProcessW / AllocConsole / AttachConsole / MapViewOfFile`（支持控制台与动态加载）。

### 延迟导入（关键）
SDL2 是 **delay import**，所以直接导入表里看不到它：

| 延迟导入 DLL | 函数数 | 与需求的关系 |
|---|---|---|
| **SDL2.dll** | **60** | ★ 唯一输入源 |
| OPENGL32.dll | 47 | 渲染 |
| GLU32.dll | 6 | 渲染 |
| FreeImage.dll | 19 | 贴图 |
| icuuc57.dll | 26 | i18n |
| **steam_api64.dll** | **2**（`SteamAPI_RunCallbacks`、`SteamAPI_Shutdown`） | 仅回调泵，未见 P2P |
| fmod.dll / fmodstudio.dll | 7 / 60 | 音频 |

**SDL2 中用到的输入类函数**：
`SDL_PumpEvents`、`SDL_PollEvent`、`SDL_GetMouseState`、`SDL_WarpMouseInWindow`、`SDL_ShowCursor`、
`SDL_StartTextInput`、`SDL_StopTextInput`、
`SDL_NumJoysticks`、`SDL_JoystickNameForIndex`、`SDL_JoystickInstanceID`、`SDL_GameControllerAddMapping`、
`SDL_GameControllerOpen/Close/Name/GetJoystick`、
`SDL_GetScancodeFromKey/FromName`、`SDL_GetKeyFromScancode`、`SDL_GetKeyName`、`SDL_GetScancodeName`（按键重绑定用）。

**没有导入 `SDL_PushEvent`**（但自己写 proxy DLL 时可以直接从 SDL2 取来用）。

> 结论：**输入的唯一入口是 SDL2 事件队列**，proxy `SDL2.dll` 是唯一可以在"输入层"下手的点；网络必须完全自建。

---

## 3. 游戏主循环（已确认）

```
入口链：
  RVA 0x68530  ← 循环体
    0x6858D  call 0x6D8E0            ; 帧前处理（计时/开始帧）
    0x68592..0x68599  call 0x74DF0   ; ★ App::frame()  → 返回 al = 是否继续
    0x6859E..0x685A8  call 0x6F280   ; 帧后清理（销毁本帧临时对象 + 写全局 =0）
    0x685AD  test bl,bl
    0x685AF  jne 0x68530             ; 继续下一帧
  退出：
    0x685B5  CoUninitialize
    0x685C0  SDL_Quit
    0x685C9  SDL_DestroyWindow
    0x685D1  SDL_GL_DeleteContext
```

- `0x74DF0` **只有一个调用者**（`0x68599`）→ 它就是这个游戏的 `frame()`。
- 渲染侧：`SDL_GL_SwapWindow` 在函数 `0x3D300` 内（`0x3D476`），该函数 **无直接调用者、也不在 .rdata/_RDATA 的 vtable 里** → 通过间接方式（.data 内 vtable 或回调注册）调用。
- 全局小工具 `0x3D4C0`：`return *(void**)(rcx+8) + 0x18;`（74 个调用者）→ GL/渲染上下文 getter。

---

## 4. 输入管线（核心，0x74DF0 内的事件段）

```
0x74F5C  call SDL_PumpEvents            (delay thunk RVA 0x316F26)
0x74F61  rcx = [r14 + 0x28D0]           ; r14 = App 上下文, +0x28D0 = InputManager*
0x74F68  call 0x59C30                   ; InputManager::beginFrame()
0x74F6D  rcx = &ev  (rbp+0x2D0)
0x74F74  call SDL_PollEvent             (thunk RVA 0x316F38)
0x74F79  test eax,eax ; je 0x7509D      ; 无事件 → 跳出事件循环
   switch (ev.type):
     0x100 SDL_QUIT        → 0x75609
     0x200 SDL_WINDOWEVENT → 0x755E2
     0x300 SDL_KEYDOWN     → 0x7526C
     0x301 SDL_KEYUP       → 0x75006
     0x303 SDL_TEXTINPUT   → 0x74FDA（逐字符 0x9C850）
     0x401 / >0x401        → 0x75650 / 0x75616（鼠标键、滚轮、摇杆、手柄）
0x75061  lea rcx,&ev ; 回到 0x75068 继续 PollEvent 循环
0x75068  call SDL_PollEvent → jne 0x74F90（还有事件）
之后（关键帧数据收集）：
0x750CC  call SDL_GetMouseState(mgr+0x494, mgr+0x498)   (thunk 0x316E96)
0x750DD  getAxis(10)
0x750F1  getAxis(9)
0x75106  getAxis(12)
0x7511A  getAxis(11)                    ; 手柄扳机/摇杆轴
```

### KEYDOWN 分支（0x7526C）
```
scancode = ev.key.keysym.scancode          ; ev+0x2E0
0xA5D00(scancode)                          ; 写全局键盘镜像 = 1
down = (ev.key.state == 1)                 ; ev+0x2DC
InputManager::onKey(mgr, scancode, down)    ; 0x59AD0
sym = ev.key.keysym.sym                    ; ev+0x2E4
if sym == 0x4000003A (F1) → 0xA6B50()      ; 调试热键
跳转表命中区（F2..F13 及特殊键）→ 0x7F32C 表
if sym == 0x31 (SDLK_1) 且 g_flag → 翻转某个全局开关
```
### KEYUP 分支（0x75006）
```
0xA5DB0(scancode)  → 全局键盘镜像 = 0
InputManager::onKey(mgr, scancode, false)
```

### InputManager 结构（由 0x59C30 反推，可靠）
| 偏移 | 类型 | 含义 |
|---|---|---|
| `+0x000`..`+0x1FF` | `u8[512]` | `keyDown[scancode]` 当前按下 |
| `+0x200`..`+0x3FF` | `u8[512]` | `keyEdge[scancode]` 边沿计数（`(v+1)|2`） |
| `+0x444` | `float[12]` | 模拟轴（手柄摇杆/扳机）原始值 |
| `+0x48C / +0x490` | i32 | 上一帧鼠标 X/Y |
| `+0x494 / +0x498` | i32 | 本帧鼠标 X/Y（由 SDL_GetMouseState 写入） |
| `+0x49C` | i32 | 滚轮 |
| `+0x4A8 / +0x4A9` | u8 | 设备连接标志 |
| `+0x4AC` | i32 | 当前设备索引（键盘 = `-1`） |
| `+0x4B0` | ptr | **轴绑定表**（每 action 32 字节 = 4 个 `{u32 设备类型, u32 code}`） |
| `+0x4B8` | ptr | **按键绑定表**（同构） |

InputManager 关键函数：
- `0x59C30` `beginFrame()`：清 `+0x200..0x3FF`、清鼠标增量、`lastMouse = mouse`、钳 `+0x4AC`
- `0x59AD0` `onKey(scancode, down)`：状态未变则返回；否则写 `keyDown`、`keyEdge=(v+1)|2`；`down==true` 时把 `+0x4AC` 置 `-1`（切回键盘）
- `0x586D0` `getAxis(actionIndex)`：读 `[+0x4B0] + idx*32` 的 4 个来源，逐个 `0x59840` 取设备值后 `maxss` 取最大
- `0x59840` `deviceValue(deviceKind, code)`：`kind==4` 且 `0<=code<12` → `float[12]@+0x444`
- `0x599C0` / `0x59A50` 两个按键查询虚函数（`keyDown` / `keyEdge` 组合判定），**直接调用者 0 个** → 通过 vtable 被 gameplay 调用

> 绑定表（`+0x4B0/+0x4B8`）的存在意味着：**"动作 → (设备, 键码)" 是可配置的映射表**，这正好是给"额外玩家分配独立按键"的天然挂点。

---

## 5. 全局键盘镜像（第二套状态）

- 全局 App 指针：`[RVA 0xBAE4D0]`，可用对象基址 = `*(0xBAE4D0) + 8`（getter `0x27A010`：`mov rax,[rip+..]; add rax,8; ret`）
- 事件直接写 `App + 0x35E0 + scancode`：
  - `0xA5D00` → `= 1`（按下）
  - `0xA5DB0` → `= 0`（抬起）
- 读取点：`0xD3009`、`0x1B0E11`、`0x20B532`、`0x21A528`

> ⚠️ 待澄清：上述 3 个"读取点"实际把 `App+0x35E0` 当作**计数**、`App+0x35E8` 当作 **stride `0xF0` 的结构体数组**，并用反射注册字段名。经解析，这些字段名是
> `pilot_seat` / `socket` / `name` / `linked_door` / `ejection_socket` / `upper_anim` / `lower_anim` / `flags` / `exclude_flags` / `seatbelt` / `animate_with_parent`
> → 这是**座位/挂点定义表**，不是玩家输入数组。
> 因此 `+0x35E0/+0x35E8` 有两套解释，需运行期确认二者是否为不同对象（很可能 `0xA5D00` 用的全局与消费者用的 `r14` 不是同一个）。

---

## 6. 世界 / 单位管理（沿用既有结论 + 本次确认）

- World 单例：`[RVA 0xB38850]`，`+0x2788` → `MechManager`
- `MechManager` 遍历结构（`pa_probe.c` 已实现）：
  `[mgr+0x00]=arr1.begin, [mgr+0x08]=arr1.end`，元素 24B `{sub_begin, sub_end, ?}`；sub 元素 16B `{u32 id, pad, Mech*}`

### RTTI 类清单（.rdata，已观测）
```
ChassisPlayerControlled      RVA 0x49B7C8     LegPlayerControlled   RVA 0x49B4A0
MechVehicle                  RVA 0x49AF38     MechAbilitySet        RVA 0x49AB68
Gun  ProjectileGun  LaserGun  ArtilleryGun  HornGun
SalvageFSM   ChassisPanic   ChassisPoint   FirePrediction_
World::DetermineLooseObjects
MechFunctions::Update(WorldInputs const&, std::vector<Mech*> const&, Pack::GlobalData*)
```

> `MechFunctions::Update(WorldInputs, mechs, globalData)` 是**输入 → 单位行为**的主入口签名。
> `WorldInputs` 是我们要找的"上游输入结构"，`ChassisPlayerControlled` / `LegPlayerControlled` 是"玩家控制底盘/腿"的类。

### Mech 的 Lua API（.rdata 字符串表，RVA 0x3D2A90 起）
```
Create, GetPlayer, GetPlayerHovered, Valid,
SetOnLevelExit, SetOnDeath, GetOnDeath, SetOnBail,
GetOnReady, SetOnReady, GetOnAlert, SetOnAlert,
GetPosition, SetPosition, GetHeight, SetHealth, Gib,
DisableAI, GetOrient, SetOrient, Look, MoveTo,
AddInventory, TakeInventory, IsInInventory, IsGunEquipped, GetInventory, SetEntryPredicate
```

### Lua 全局注册函数（.rdata，RVA 0x3CACA0 起）
```
register_init_function / register_update_function / register_draw_function
register_levelexit_function / register_win_function / register_defeat_function
register_alarm_function / add_usable_item / freeze_player
get_total_enemies / get_killed_enemies / _objective / fail_objective
```

---

## 7. `Player_Action` 的真实性质（重要修正）

字符串 `Player_Action` / `Gun_Windup` / `ejector` / `Lateral` 位于 RVA `0x3ACB68 ~ 0x3ACBE8`，
其引用点集中在 `0x28CEA / 0x29BB6 / 0x2AE75 / 0x2AF05 / 0x2B151 / 0x2B1C0 / 0x2B1DE`，
并且伴随 `"src\Gun.cpp"`（RVA `0x3ACBC8`）与行号常量（`0x37D`、`0x37E`）。

`0x2B120..0x2B250` 的实际用法：
```
0x1A6160(anim_reg, [Gun+0x1290])              ; 查询命名通道是否存在
0x392B64(ctx, "Player_Action", 1, xmm6)        ; 按名字注册/查找通道
0x392B64(ctx, "Vehicle_Filter", 1, xmm9)
0x1A6240([rdi+0x120], "Gun_Windup", 1, [rdi+0x7C])
0x1A6240([rdi+0x128], "Gun_Windup", 1, [rdi+0x7C])   ; 同一 float 写两个通道
0x1A6200([rdi+0x110 / 0x118 / 0x120 / 0x128], ...)   ; 逐通道提交
```
`0x29BB6`（"ejector"）用法：`rsi = [Gun+0x68] → rsi = [rsi]`，其后读 `[rsi+0x88]` 计数、`[rsi+0x90]` 数组指针。

**结论**：`Player_Action` 是 **每台 Mech 的"姿势/表现参数字块"**（Gun 预热、侧倾、抛壳、速度、时间…），
它由运动学/动画层**从真实运动状态派生出来**，再作为**命名通道**喂给动画系统。

这正好解释了此前的实验现象：
- 拷贝这几十字节 → **上半身姿态动了/抽搐**（因为改的是动画通道的值）
- 但**腿不走**、停下就弹回（因为移动不读这里；下一帧派生值把通道覆盖回去）

> **因此 `Player_Action` 是下游（输出），不是上游（输入）。这条注入路线应正式关闭。**

---

## 8. 对"多人联机"的结论与下一步

### 已排除
1. ❌ 改 `Player_Action` 数据区驱动移动 —— 它是派生输出。
2. ❌ 依赖引擎自带网络 —— exe 内无任何 socket API。
3. ❌ 用 Steam P2P —— 只导入了 `SteamAPI_RunCallbacks` / `SteamAPI_Shutdown`，未做初始化/网络接口。

### 可行注入点（按优先级）
| # | 注入点 | 证据 | 侵入性 | 备注 |
|---|---|---|---|---|
| **A** | **`WorldInputs`**（`MechFunctions::Update` 的第一个参数） | 函数签名 RTTI | 低-中 | 与用户设想完全一致：每玩家一个 `WorldInputs`，网络线程填它 |
| **B** | InputManager 的**绑定表** `+0x4B0 / +0x4B8` | `getAxis` 反汇编 | 低 | 给额外玩家一套"动作→键码"映射；但全局只有 1 个 InputManager，需复制实例 |
| **C** | `SDL_PollEvent` / `SDL_PushEvent` | 延迟导入 + 主循环 0x74F74 | 低 | 只能定向影响"当前焦点玩家"（用户已指出这个局限） |
| **D** | `ChassisPlayerControlled` / `LegPlayerControlled` 虚函数 | RTTI 存在 | 高 | 需要 vtable 定位与更多逆向 |

### 建议的下一步（静态，无需开游戏）
1. **定位 `MechFunctions::Update` 的地址** → 从它的第一个参数反推 `WorldInputs` 的**字段布局**（这就是"每玩家输入包"的协议定义）。
2. **追 `WorldInputs` 的填充者** → 确认它是"帧级全局单例"还是"可复制结构"。这决定多人方案是"多实例"还是"逐帧改写"。
3. 同时确认 `App + 0x35E0` 的双重解释（键盘镜像 vs 座位表）——运行期读一次即可判定。

---

## 9. 复现方式

分析脚本位于 `C:\Users\Scrooge\AppData\Local\Temp\bk_re\`（一次性工具，未纳入项目）：

| 脚本 | 作用 |
|---|---|
| `01_pe_info.py` | PE 头 / 节表 / 导入统计 |
| `03_delay_sdl.py` | **SDL2 延迟导入 60 函数清单** |
| `06_xref2.py` | 带 `skipdata` 的稳健 IAT 交叉引用（关键：不加 skipdata 只解出 2.9 万条指令） |
| `07_callers.py` | SDL thunk 调用点 + 上下文 |
| `08_input_mgr.py` | InputManager `beginFrame/onKey/getAxis` 反汇编 |
| `12_call_graph.py` | 主循环 / 渲染函数调用序列 |
| `14_loop_body.py` | 顶层循环体（0x68480..0x68640） |
| `16_rtti.py` | RTTI 类名 + 关键字串搜索 |
| `19_field_names.py` | 反射字段名解析 |
| `21_pa_field_access.py` | `Player_Action` 实际用法 |

### 已知环境阻塞
- **REA（reverse-engineer-anything 的 MCP 引擎）不可用**：`npx rea-agents@latest` 要求 Node `>=22.23.4`，当前为 `v22.17.0`。
  按技能约定不擅自升级 Node，故改用 `pefile` + `capstone` 完成等价静态分析。
- 经验：`capstone` 必须设 `md.skipdata = True`，否则在第一个无法解码的字节处停止（本 exe 会停在 RVA `0x20EFC`，丢失 97% 代码）。

---

# 第二轮：动作/绑定系统 与 玩家控制路径

> 目标：确认"玩家输入"是全局单例还是可多实例 —— 决定多人能否成立。
> 结论先行：**输入采样 API 全部是 `this=InputManager*` 的成员函数，没有任何一处写死全局**。
> 因此"多玩家"= 多份 InputManager + 把正确的实例指针喂给对应 Mech 的控制函数。

## 10. InputManager 完整布局（大小 `0x4C0`）

App 构造时分配（`0x6E196: mov rcx,[rsi+0x2728]; mov edx,0x4c0; mov r8d,0x10; call 0x2204F0`）：

```
0x6E1A2  mov [rsi+0x28D0], rax        ; App+0x28D0 = InputManager*（全局唯一实例）
0x6E1B1  call 0x398B3E(rax, 0, 0x4C0) ; memset 清零
0x6E1C0  mov [rax+0x4B0], r14         ; 轴绑定表
0x6E1CE  mov [rax+0x4B8], rbx         ; 键绑定表
```

| 偏移 | 类型 | 含义 | 证据 |
|---|---|---|---|
| `+0x000` | `u8[512]` | `keyDown[scancode]` | `0x59A80`: `cmp edx,0x200; cmp byte [rcx+rdx],0` |
| `+0x200` | `u8[512]` | `keyEdge[scancode]`（`(v+1)|2`） | `0x59AA0`: `[rcx+rdx+0x200] + [rcx+rdx]` |
| `+0x400` | `u8[7]` | `padDown[7]` | `0x59B20` |
| `+0x407` | `u8[7]` | `padEdge[7]` | `0x59BA0` |
| `+0x40E` | `u8[14]` | `axisDown[14]`（手柄轴数字化） | `0x597F0` |
| `+0x41C` | `u8[14]` | `axisEdge[14]` | `0x597F0` |
| `+0x444` | `float[12]` | 处理后的模拟轴值 | `0x59840` |
| `+0x470` | `i16[14]` | 手柄原始轴（SDL 原始值） | `0x593B0`: `movd xmm,[rcx+rax*4+0x470]` |
| `+0x48C/+0x490` | `i32` | 上帧鼠标 X/Y | `0x59C30` |
| `+0x494/+0x498` | `i32` | 本帧鼠标 X/Y | `0x750CC SDL_GetMouseState` |
| `+0x49C` | `i32` | 滚轮累计 | `0x59BF0` |
| `+0x4A8` | `u8` | **鼠标已连接** | `0x58878`(`kind==2` 时检查) |
| `+0x4A9` | `u8` | **键盘已连接** | `0x58886`(`kind==1`) |
| `+0x4AA` | `u8` | **手柄已连接** | `0x588CD`(`kind==3`) |
| `+0x4AB` | `u8` | 是否有模拟输入（`0x7512A` 判空） | |
| `+0x4AC` | `i32` | 当前设备（键盘 `-1`，手柄 `1`） | `0x59BA0`/`0x597F0` |
| `+0x4B0` | `ptr` | **轴绑定表**（72 动作 × 4 条 × 8B） | `0x586D0`/`0x5884E` |
| `+0x4B8` | `ptr` | **键绑定表**（同构，`0x59D4D` 清零 `0xA00`=2560B=72×4×8+64） | `0x588A8` |

> ⚠️ 修正第一轮笔记：`0x599C0/0x59A50` 并不是两个按键查询函数（全文件 0 处引用）。
> 真实 API 是下面一组（都在 `0x58600..0x59E00` 区间）。

## 11. 动作 / 绑定系统（多人方案的核心）

- **动作总数 = 72**（`0x47`）。每个 API 入口都有 `cmp edx,0x47; ja`。
- **每个动作 8 条绑定**：`+0x4B0` 表的 4 条 + `+0x4B8` 表的 4 条。
- **每条绑定 8 字节**：`{ u32 deviceKind, u32 code }`
  - `deviceKind == 1` → 键盘，`code` = SDL scancode；需 `[mgr+0x4A9]`
  - `deviceKind == 2` → 鼠标，`code` = 鼠标键/轴；需 `[mgr+0x4A8]`
  - `deviceKind == 3` → 手柄，`code < 14` 为轴；需 `[mgr+0x4AA]`
  - `deviceKind == 4` → 手柄轴模拟值（`0x59840` → `float[12]@+0x444`）

### 动作查询 API（全部 `this=InputManager*`，`edx=action`，范围 0..71）

| 地址 | 语义 | 调用点数 |
|---|---|---|
| `0x586D0` | `float getAxis(action)`：取 8 条绑定的模拟值 `maxss` | 24 |
| `0x58830` | `bool actionHeld(action)`：8 条绑定 OR | 27 |
| `0x58980` | `bool actionHeldOrPressed(action)` = `0x58830 || 0x58CE0` | 14 |
| `0x589C0` | `bool`（轴 + 键混合 OR） | 18 |
| `0x58CE0` | `bool`（`0x599F0` 边缘 → `0x59950` → `0x598C0` 三级 OR） | **72（最高频）** |
| `0x598C0` | 单条绑定"当前按下" | 内部 6 |
| `0x59950` | 单条绑定"本帧刚按下" | 内部 5 |
| `0x599F0` | 单条绑定第三种判定 | 内部 1 |
| `0x58520` | `void moveVector(vec2* out /rcx, InputManager* /rdx, float* optMag /r8)`：`x=axis(3)-axis(2)`，`y=axis(4)-axis(5)`，归一化 + 死区；`r8` 是**可选输出**（`if (rsi) *rsi = mag`），不是玩家索引 | 1（被 0x2FA40 调用） |

**动作索引锚点（已确认）**
- `2 / 3` → 移动 X 负 / 正（左右平移）
- `4 / 5` → 移动 Y 负 / 正（前后）
- `0x1C (28)` → 瞄准/武器举升（`WheeledVehicle` 里控制武器位姿）
- `9/10/11/12` → 鼠标/手柄视角增量（App::frame `0x750DD..0x7511A`）

## 12. 玩家控制入口：`WheeledVehicle` 虚函数

```
vtable @ 0x3ACCF0（.rdata）  安装点: 0x2D92B, 0x2DE1B（构造函数）
  [0]  0x2DE10
  [1]  0x2FF50
  [2]  0xCA5A0   [3] 0xCA5A0
  [4]  0x208C0   (纯虚/占位)
  [5]  0x2FA40   ★ 玩家控制更新（PlayControl）
  [6]  0x2F760   [7] 0xF8E70   [8] 0xF8D40
  [9]  0x2FC80   (瞄准/朝向计算，用 atan2)
  [10] 0x2DEB0 ...
```

`0x2FA40` 的签名（由寄存器使用反推）：

```
void WheeledVehicle::PlayUpdate(?, const vec2* aimish / r8, InputManager* mgr / r9)
    rcx = this（载具）
    r8  = 指向 vec2（0x2FA4F/0x2FA57 读 [r8], [r8+4] 后 atan2）
    r9  = InputManager*    ★ 传参，不是全局
```

函数体行为：

```
0x2FA91  call 0x58520(&local_vec2, mgr, 0)   ; 取出移动向量（玩家索引 0）
0x2FA96  if (local.y > 0) { 0xF9150(); 0x2F4C0(); } else if (< 0) { 0xF9150(); 0xF86A0(); }
0x2FAC8  vehicle+0x1E8 = 结果 * local.y      ; 油门/刹车输出
0x2FB21  edx=0x1C; rcx=mgr; call 0x58830     ; 动作 28 是否按住
           → 按住时把武器位姿数据写入 [this+0x190] 的 4 个槽
0x2FC07  edx=0x1C; call 0x589C0             ; 本帧刚切到 28？→ 0x2F520()（收枪/换姿态）
0x2FC36  xmm0 = local.x 取反（若 [gunData+0xA9]）
0x2FC5A  xmm0 *= [gunData+0x8C]
0x2FC70  (double)vehicle+0x1B0 = xmm0        ; 转向输出
```

> **这是"输入 → Mech 行为"的最终合同**：一个 `vec2`（油门/转向）+ 若干动作布尔值。
> 只要能让另一台载具的 `PlayUpdate` 收到另一份 `InputManager`，就实现了"第二个玩家"。

## 13. 对多人方案的判定（更新）

**好消息**：输入层没有任何硬编码全局。`getAxis` / `actionHeld` / `moveVector` 全部通过 `rcx` 收 `InputManager*`，
`WheeledVehicle::PlayUpdate` 通过 `r9` 收 `InputManager*`。

**剩余未知（唯一关键缺口）**：谁调用 vtable slot 5 并决定传哪个 `InputManager*`？
- 该调用是**虚调用**，静态无直接引用（44 处 `call [reg+0x28]` 里没有紧邻 `+0x28D0` 的）。
- 需要 `.pdata` 函数边界 + 反查"把 `[App+0x28D0]` 传给虚函数"的那一处，或运行期 hook `InputManager::getAxis` 抓调用栈。

**三条可行路线（按侵入性排序）**

| # | 方案 | 做法 | 评估 |
|---|---|---|---|
| **A** | **多 InputManager + 指针重定向** | 分配 2..N 份 `0x4C0` 实例，把每台 Mech 的 `PlayUpdate` 的 `r9` 指针改成对应玩家的实例 | 最贴近用户设想；改动集中在一处调用点 |
| **B** | **动作查询层分流** | Hook `0x58830/0x58CE0/0x586D0`，按"当前正在更新哪台 Mech"选择读哪份输入状态 | 需要 per-frame 的"当前玩家"上下文变量 |
| **C** | **SDL 事件复用** | 网络线程把远端输入翻译成 `SDL_PushEvent` | 只能驱动 1 个玩家（用户已否定） |

**网络输入落地方式（不变）**：exe 零 socket → 必须自建：
1. proxy `SDL2.dll`（已确认 SDL2 是 delay import，可整包替换）；
2. 或注入 DLL 开 `Winsock`，在帧边界把 TCP 报文写入 `InputManager` 的 `keyDown/padDown/axis` 字节区。

> 由于 `keyDown[512]` / `padDown[7]` / `axisDown[14]` 都是**纯字节数组**，
> 网络线程可以直接按 scancode 下标写字节 —— **不需要模拟按键事件，也不会被 SDL 焦点限制**。
> 这是当前最干净的 TCP 输入接口：`mgr->keyDown[scancode] = 1`。

## 14. 待办（下一步）

1. 用 `.pdata` 建立函数边界表 → 反查 vtable slot 5 的调用者（约 44 个候选点里筛）。
2. 确认 `WorldInputs` 结构（`MechFunctions::Update` 第一参数）是否就是 `{vec2 move; vec2 aim; InputManager* mgr; ...}`。
3. ~~把 `0x58520` 第三个参数（玩家索引 `0`）追清楚~~ → **已否证**：`r8` 是可选 `float*` 幅值输出，不是索引。
4. 确认 `+0x4B0/+0x4B8` 两张绑定表的初始化点（默认可执行文件内，可能在 `0x673xx` 配置加载处）。

---

## 15. 绑定表的物理位置（可直接 patch）

App 构造函数 `0x6E11E..0x6E1CE`：

```
0x6E11E  lea r14, [rip+0xad3c23]        ; r14 = 0xB41D48   ← 轴/主绑定表（静态数组）
0x6E125  cmp byte [rip+0xad3c16], 0     ; 0xB41D42  "表已初始化" 标志
0x6E13C  mov rcx, r14
0x6E13F  add rdx, 0x1D778               ; rdx = [App+0x2A40] + 0x1D778  ← Pack 内存数据
0x6E146  mov r8d, 0xA00
0x6E14C  call 0x398B20                  ; memcpy(dst=0xB41D48, src=pack+0x1D778, 0xA00)

0x6E151  lea rbx, [rip+0xad45f0]        ; rbx = 0xB42748   ← 键绑定表
0x6E172  add rdx, 0x1E178               ; src = [App+0x2A40] + 0x1E178
0x6E179  mov r8d, 0xA00
0x6E17F  call 0x398B20                  ; memcpy(dst=0xB42748, ...)

0x6E1C0  mov [InputMgr+0x4B0], r14      ; = 0xB41D48
0x6E1CE  mov [InputMgr+0x4B8], rbx      ; = 0xB42748
```

- 每张表 **`0xA00` = 2560 字节 = 80 动作 × 32 字节**（每动作 4 条绑定 × 8 字节）。
- API 只校验 `action <= 0x47`（71）→ 实际使用 72 个动作，分配 80 个。
- 表内容来自 **Pack 数据**（`App+0x2A40` 是资源包对象），偏移 `0x1D778` / `0x1E178`；
  即**默认键位不是硬编码在 .text 里**，而是随资源包加载。
- 两张表地址固定（`.data` 区），**运行期可直接读写/整表替换** —— 这是"给玩家 2 换一套键位"的最省事挂点。

> 想拿到完整 72 动作 ↔ 默认键位 的映射，需要在运行时 dump `0xB41D48` / `0xB42748`（各 2560B），
> 或在资源包里定位 `0x1D778` 那个 blob。静态到此为止。

## 16. 可复用工具（本轮新增）

| 脚本 | 作用 |
|---|---|
| `22_worldinputs.py` | .rdata 字符串 + RIP 相对 lea/mov 交叉引用（一次扫描全 .text，约 4 秒） |
| `24_rtti_vtable.py` | 类名 → TypeDescriptor → COL → vtable → 槽位函数 + 引用点 |
| `26_vt_find.py` | 给定函数 RVA，反查它出现在哪个"表块"的哪个槽位 |
| `29_dumpdata.py` | 带指针解引用的数据区转储 |
| `32_fullscan.py` | 全量线性反汇编 → `insns.pkl` 缓存（986,848 条指令） |
| `33_hits.py` | 在 `insns.pkl` 上按字段偏移检索所有访问点 |
| `34_callers_range.py` | 给定地址区间，列出被调用函数 + 调用点 + 所属函数 |
| `35_pdata.py` | **`.pdata` 函数边界表（13,437 个函数）**，可精确判定"某指令属于哪个函数" |

> `.pdata` 解析后 `0x2FA40` 所在函数大小 574B；`0x74DF0`（App::frame）大小 `0xA7FE`（43KB 巨型函数）。
> 这是后续所有"反查调用者"的基础设施。

## 17. 架构层面的结论（对 multiplayer 的判决）

**输入侧完全"可多实例"**：所有采样入口都是 `this=InputManager*` 的成员函数，没有一处直接引用全局。

**但游戏本身是单玩家设计**：
- `App+0x28D0` 只有一个 `InputManager` 指针，构造时分配一次。
- 全局搜索 `playerIndex / player_index / controllerIndex / localPlayer / InputDevice` **零命中**。
- 唯一的"玩家"访问器是 `0x178F30([App+0x2CA0])` → 单个 Player 对象。

**因此多人的最小可行形态**：
1. 额外分配 N-1 份 `0x4C0` 的 `InputManager`，绑定表直接指向同一对静态表（`0xB41D48/0xB42748`）或复制一份改键位；
2. 网络线程把 TCP 报文翻译成 `keyDown[scancode] / padDown[i] / axisDown[i] / rawAxes[i]` 的直接字节写入；
3. 在"喂给某台 Mech 的控制更新"处，把 `InputManager*` 换成该玩家对应的实例。
   当前障碍：该处是虚调用（`slot +0x28`），静态没定位到具体调用点（44 个候选均不匹配），
   **需要运行期 hook `InputManager::getAxis(0x586D0)` 抓调用栈一次性定位**。
4. 每帧对每台玩家 Mech 重复该流程 → 即"多 Mech 同时接收输入"。

---

# 第三轮：AI 与玩家控制是否共用同一组字段（决定"改造 NPC"是否可行）

## 18. Lua → C++ 函数表（直接给出所有 Mech 操作的实现地址）

表结构：连续的 `{ char* name; void* fn; }` 对，位于 `.rdata` **`0x3D26B0 ~ 0x3D28B0`**。

| Lua 名 | 实现 RVA | Lua 名 | 实现 RVA |
|---|---|---|---|
| `GetPlayer` | `0x1A86A0` | `GetPosition` | `0x1A8FE0` |
| `SetOnDeath` | `0x1A8D60` | `SetHealth` | `0x1A92A0` |
| `Gib` | `0x1A9360` | **`DisableAI`** | **`0x1A93D0`** |
| **`Look`** | **`0x1A9490`** | **`SetOrient`** | `0x1A95D0` |
| **`MoveTo`** | **`0x1A9640`** | `IsGunEquipped` | `0x1A9A90` |
| `GetInventory` | `0x1A9B50` | | |

### 通用调用形态（所有 Mech API 一致）

```
0x319380(lua, -1)              ; 取第 1 个参数 → userdata 内的 handle
0x24C80([World]+0x2788, h)     ; MechManager::FindMech(handle) → Mech*
                               ;   注：[World] = [[RVA 0xB38850]]，+0x2788 = MechManager ✓
0x3182D0 / 0x319320 / 0x318A10 ; 取后续数值参数（double/float）
```

## 19. `DisableAI` 的真实数据流（`0xDE910`，最有价值的一条）

```
0xDE9F3 lea rcx, [m + 0x500]      ; 通道 A（上层朝/瞄准基准）
0xDE9EC rax = [m + 0x240]         ; 组件指针（Chassis/Leg）
0xDEA0E xmm2 = [rax + 0x0C]       ; 当前朝向角
0xDEA13 call 0xBA6B0              ; 写 m+0x500 = 当前朝向   ← 冻结
0xDEA1D lea rcx, [m + 0x528]      ; 通道 B（下层/腿）
0xDEA18 xmm2 = [m + 0x0C]
0xDEA2A call 0xC7890              ; 写 m+0x528 = 当前朝向   ← 冻结
0xDEA39 m+0x6F8 = 0               ; 清标志
0xDEA40 m+0x6F0 = -3600.0 (double); ; AI 相关计时/阈值
0xDEA57 m+0xB58 &= ~0x20          ; 清一个能力位
0xDEA5E edx = [m+0x4C4]; call 0xE7B70   ; 用旧控制者 ID 做清理
0xDEA7B m+0x4C4 = -1              ; ★★ 控制者置空
0xDEA85 call 0x13A260(m+0xB20, World+0x28E0)
0xDEA8D [m+0x478] → 断言（带字符串常量）
```

> **`Mech+0x4C4` = 当前控制者 ID（`-1` = 无 / AI 已剥离）**
> `Mech+0x4C0` / `+0x4C4` 成对读写（`0xDE95C/0xDE950/0xDE96A` 处一起被读进调试输出）。
> 这一对极可能是 `{控制类型, 控制者索引}` —— 就是"谁在开这台机器"。

**结论：`DisableAI` 不是"让 AI 停下"，而是"把控制权从 AI 剥离 + 冻结当前朝向 + 控制者置空"。**
剥离之后这台 Mech 就是一张白纸，等你写意图字段。

## 20. `MoveTo` / `Look` 写的字段（= 外部控制的官方接口）

### `MoveTo(target, speed)` — `0x1A9640`

```
0x1A968F lea rdx, [World + 0x28E0]   ; 帧上下文/时间
0x1A9699 lea rcx, [m + 0x178]        ; ★ 移动目标点结构
0x1A96A0 call 0x21070                ; 写入目标（vec3 + 参数）
0x1A96BB m+0x1D8 = 6                 ; ★★ 行为状态机 = 6（"执行外部移动指令"）
0x1A96A5 rcx = [m+0x550]; rcx = [rcx+0x50]
0x1A96AF edx = [m+0x4C4]             ; 控制者 ID
0x1A96B5 r8d = 3; r9d = 0
0x1A96C9 call 0xE7A80                ; 通知移动子系统
```

### `Look(angle)` — `0x1A9490`

```
0x1A9507 lea rcx, [m + 0x500]; r9 = m; xmm2 = angle ; call 0xBA6B0
0x1A952E lea rcx, [m + 0x528]; r9 = m; xmm2 = angle ; call 0xC7890
```

### 推导出的 Mech 意图字段表

| 偏移 | 含义 | 写入者 |
|---|---|---|
| `+0x0C` | 当前朝向（float） | 物理/运动学 |
| `+0x178` | **移动目标点** | `MoveTo` |
| `+0x1D8` | **行为状态机**（`6` = 外部移动指令） | `MoveTo` |
| `+0x240` | 底盘/腿组件指针 | — |
| `+0x4C0/+0x4C4` | **控制者 {类型, ID}** | `DisableAI` 置 `-1` |
| `+0x478` | 调试名 / 资源名 | — |
| `+0x500` | **朝向通道 A** | `Look` / `DisableAI` |
| `+0x528` | **朝向通道 B** | `Look` / `DisableAI` |
| `+0x550 → +0x50` | 移动子系统对象 | — |
| `+0x6F0/+0x6F8` | AI 计时/标志 | `DisableAI` |
| `+0xB20` | 某状态结构 | `DisableAI` |
| `+0xB58` | 能力标志位（`&~0x20`） | `DisableAI` |

## 21. 回答："能不能把 NPC 改成由外部输入控制？"

**能，而且引擎已经给了官方的"半成品"入口。** 原因：

1. **AI 与外部控制共用同一组意图字段**（`+0x178` 目标、`+0x1D8` 状态、`+0x500/+0x528` 朝向）。
   AI 只是这些字段的一个写入者，`MoveTo/Look` 是另一个写入者 —— **数据流在下游合流**。
2. **`DisableAI` 已经能把 AI 这个写入者摘掉**，并把 `+0x4C4` 控制者置 `-1`。
3. 玩家控制路径（`WheeledVehicle::PlayUpdate` @ `0x2FA40`）**自己不碰这些字段**，它只写
   油门 `+0x1E8` / 转向 `+0x1B0`。所以"载具式控制"和"MoveTo 式控制"是两套并行接口。

**三条改造路线（按工作量递增）**

| 路线 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| **L1｜纯 Lua 脚本** | `DisableAI` + 每帧 `MoveTo/Look` | 零二进制改动，官方支持 | 只有"移动/朝向"，没有开火/挂载；受脚本沙箱限制 |
| **L2｜注入 DLL 复用同一组字段** | 直接调 `0xDE910` + 写 `+0x178/+0x1D8/+0x500/+0x528` | 完全可控，仍是官方字段 | 需要自己解算"输入 → 意图" |
| **L3｜换控制器组件** | 把 Mech 的 Chassis/Leg 组件换成 `ChassisPlayerControlled`/`LegPlayerControlled`，走 `PlayUpdate` | 手感与玩家完全一致（含武器） | 需要吃透组件挂载与 `InputManager*` 传递链 |

> **L3 才是最接近用户设想的做法**（"NPC 变成第二个玩家"），并且已有 RTTI 证据：
> `ChassisPlayerControlled`(`0x49B7C8`) / `LegPlayerControlled`(`0x49B4A0`) 这两个类名本身就说明
> **引擎把"玩家控制的底盘/腿"做成了独立组件类型**。同一台 Mech 换组件即可切换控制方式。

**下一步（若要推进 L3）**：反汇编 `0x49B7B8` 与 `0x49B490` 对应的构造函数，
确认组件如何挂到 `Mech+0x240`，以及 `WorldInputs` 里是否带着 `InputManager*`。

---

# 第四轮：能力分层 —— 为什么 NPC 做不到"上下车 / 拾取 / 选取"

## 22. `Mech` 的完整脚本 API（59 个方法，表 @ `0x3D26E0`）

这是引擎对 Lua 暴露的**全部** `Mech` 能力（`{名字, 实现 RVA}` 表，59 项）：

```
元信息   : GetName 0x1A8970, SetName 0x1A89F0, Valid 0x1A8910, GetID 0x1A8CF0,
           GetResourcePath 0x1A8A70, GetLoreName 0x1A9BC0, DumpInventory 0x1AA5F0, Is 0x1AABB0
变换     : GetPosition 0x1A8FE0, SetPosition 0x1A90A0, GetHeight 0x1A9110,
           GetOrient 0x1A9410, SetOrient 0x1A95D0, Look 0x1A9490, MoveTo 0x1A9640, Halt 0x1AA690
生命     : SetHealth 0x1A92A0, GetMaxHealth 0x1AACA0, Gib 0x1A9360, Delete 0x1AA640
武器     : GetGuns 0x1A8AE0, IsGunEquipped 0x1A9A90, GetInventory 0x3B850
背包     : AddInventory 0x1A96F0, TakeInventory 0x1A97E0, IsInInventory 0x1A98D0,
           SetEntryPredicate 0x1A9B50
座位     : GetSeats 0x1A9F10, GetMechInSeat 0x1AA9A0, GetInto 0x1A9C20,
           EjectSeat 0x1A9E20, EjectAll 0x1AA300, SetSeatLocked 0x1AA750,
           SetLocked 0x1AA6E0, IsMounted 0x1AAC40, IsMountedIn 0x1AAEE0, SetOnMount 0x1AA820
AI       : DisableAI 0x1A93D0, SetOrder 0x1AA040, QueueAIState 0x1AA110, GetAIState 0x1AA1C0,
           SetExitingFlee 0x1AA240, Bail 0x1AA2B0, GetUnitThreat 0x1AAD10, Speak 0x1AA3A0
事件回调 : SetOnLevelExit 0x1A8EC0, SetOnDeath 0x1A8D60, GetOnDeath 0x1A8F60, SetOnBail 0x1A8E10,
           GetOnReady 0x1AAFE0, SetOnReady 0x1AB050, GetOnAlert 0x1AB110, SetOnAlert 0x1AB180
其他     : FlagTest 0x1AA520, ToTable 0x1AA8D0, SaveToCharacter 0x1AAAD0,
           SetImpoundable 0x1AAD80, GetImpoundable 0x1AAE10, GetReveal 0x1AAE70
```

静态命名空间（表 @ `0x3D2690`）：`Mech.New 0x1A85A0`, `Mech.Create 0x1A8740`,
**`Mech.GetPlayer 0x1A86A0`**, **`Mech.GetPlayerHovered 0x1A91A0`**。

### 重大缺口（正对应用户观察）

| 能力 | 是否有 API | 说明 |
|---|---|---|
| **开火 / 扣扳机** | ❌ **完全没有**（无 Fire / Shoot / Trigger / Attack） | 开火不经过脚本层，由控制组件直接驱动 Gun |
| **拾取 / Salvage** | ❌ 只有背包操作（Add/Take/IsIn），没有"拾取"动作 | RTTI 有 `SalvageFSM`，但那是 AI 内部状态机，不暴露 |
| **玩家主动上下车** | ⚠️ 只有程序化的 `GetInto` / `EjectSeat` / `EjectAll` / `Bail` | **没有**"玩家按交互键上下车"的 API |
| **指向/悬停选择** | ⚠️ 只有 `Mech.GetPlayerHovered`（查"玩家正指向谁"） | NPC 没有 hover 概念，这是纯玩家态 |

## 23. 结论：三层结构，NPC 缺的是第三层

```
① 载体层  Mech（所有单位都有）        ：位置/朝向/生命/背包/座位/开火硬件
② 决策层  AI brain 或 玩家输入        ：写意图字段（+0x178 / +0x1D8 / +0x500 / +0x528）
③ 交互层  玩家专属 ability            ：上下车 / 拾取 / 选取 / 交互  ← NPC 完全没有
```

- **NPC 有 ①②，没有 ③。**
- 开火看似属于 ③，其实属于 ①：Gun 组件自带 trigger，AI 和玩家都能触发，**只是外部无法从脚本触发**。
- 上下车 / 拾取 / 选取属于 ③：只在"玩家控制组件"里实现，AI 分支里根本没有对应代码路径。

> 所以"把 NPC 改成玩家"不是换一个输入源就够，
> 必须把 **`ChassisPlayerControlled` / `LegPlayerControlled` 这整套玩家组件（含 ③ 层能力）** 装配上去。
> 这也解释了为什么 `DisableAI` 之后 NPC 会"僵住"——它只剩 ① 层，没有 ③ 层提供行为。

## 24. 补充：键名表与动作名

- SDL 键名表（94 项）@ `0x3E5890`：`Tab, LeftArrow, ..., GamepadRStickDown, MouseLeft, MouseWheelX, ModCtrl, ModShift...`
- 修饰键名表（24 项）@ `0x3E56B0`
- **72 个动作的名字不在 .rdata**（全文件只有 4 个 ≥20 项的字符串指针数组，均非动作名）
  → 动作名与绑定表一起存放在 **Pack 数据**（`[App+0x2A40]+0x1D778`），只能运行期 dump。

---

# 第五轮：引擎里到底有没有 "Player 单例"？（改造可行性的计量）

## 25. 结论：**没有 Player 类，也没有 Player 单例**

RTTI 全表扫描（关键字 `Pilot|Controller|Avatar|Agent|Character|Player|Driver|Seat|Operator`）只命中 3 个真实类型：

```
ChassisPlayerControlled   0x49B7C8
LegPlayerControlled       0x49B4A0
PassengerSeat             0x499950   (另外的 lambda 都是它的成员函数)
```

**没有任何名为 `Player` / `PlayerController` / `Avatar` 的类。**
所谓"玩家"不是一个对象，而是**三处散落的状态**：

| # | 状态 | 位置 | 引用点 | 性质 |
|---|---|---|---|---|
| 1 | 当前玩家单位/载具 | `App+0x2CA0`（经 getter `0x178F30`） | **64** | 单个指针 |
| 2 | 控制方式 | Mech 上的 `Chassis/Leg` 组件（`Mech+0x240`） | — | 每 Mech 一份 |
| 3 | 控制者 ID | `Mech+0x4C0 / +0x4C4`（`-1`=无） | — | 每 Mech 一份 |

附带计量：`App+0x2A90` 有 214 个引用（疑似更大的全局上下文，非玩家）；`App+0x2F10/0x2F14` 仅 8/2 个。

### 引用点分布（决定改造成本的关键）

`App+0x2CA0` 的 64 个引用点，地址几乎全部落在 **`0x6F000 ~ 0x77000`** 区间，
即 **`App::frame`（`0x74DF0`，大小 0xA7FE）及其直接子函数内部**：

```
0x15771, 0x157AA, 0x157D2          ← 启动期（一次性）
0x6DB13                            ← App 构造
0x6F28A, 0x70A6F..0x73D54          ← 帧循环子函数
0x751BA, 0x75356, 0x75460, 0x7645C.. ← App::frame 内部
```

> **玩家逻辑高度集中在一个巨型帧函数里** —— 这对"改成多实例"是极大的利好。

## 26. 两条改造路线，成本差一个数量级

### 路线 A：把 `App+0x2CA0` 改成数组/字典（用户设想的方案）

- 需要**改 64 处引用点**，每处从 `[App+0x2CA0]` 变成 `players[当前索引]`。
- 还要给引擎加"当前玩家索引"这个新概念（原引擎没有）。
- 风险：帧循环里上下文复杂，漏改一处就会出现"玩家 2 操作串到玩家 1"。
- **不推荐**，除非要做真正的"同屏双人同时渲染"。

### 路线 B：**上下文切换（Context Switch）** —— 推荐

保持 `App+0x2CA0` 原样不动，把它当作 **"当前正在处理的玩家"**：

```
每帧：
  for (i = 0; i < playerCount; i++) {
      saved = App->0x2CA0;
      App->0x2CA0 = players[i].mech;      // 切换上下文
      App->0x28D0 = players[i].input;     // 切换输入（上一轮的结论）
      runPlayerFrame(App);                // 复用原有逻辑
      App->0x2CA0 = saved;
  }
```

- **64 处引用点一处都不用改**；
- 复用引擎全部玩家逻辑（含 ③ 层交互能力）；
- 每帧切换 N 次，开销可忽略；
- 与上一轮的"多 InputManager"方案**天然配套**。

## 27. 与前三层结构的对应关系

```
① 载体层  Mech           ← 每个玩家一台，天然支持
② 决策层  AI / 输入      ← 用 InputManager 指针切换（路线 B）
③ 交互层  玩家能力        ← 跟着 App+0x2CA0 一起切换（路线 B 自动获得）
```

> **关键洞察：因为 ③ 层能力是"按当前玩家"动态取的（64 处引用都从 `App+0x2CA0` 出），
> 所以只要切换这一个指针，玩家 2 就能自动获得全部交互能力。**
> 这比"复制能力对象"简单得多，也解释了为什么引擎没有 Player 类 —— 它本来就是"无状态、按上下文取"的设计。

## 28. 待验证

1. `0x178F30(App+0x2CA0)` 的返回类型（Mech* 还是"玩家单位包装"）—— 决定 `players[i]` 该存什么。
2. `App+0x2CA0` 是"当前玩家载具"还是"当前玩家实体"（下车后是否变化）。
3. 若走路线 B，需要确认帧内是否存在"必须只跑一次"的全局副作用（如音效、UI 绑定）。

---

# 第六轮：静态确认"多台 Player 控制的 Mech 能否共存"

## 29. `Mech+0x4C4` = 控制者索引，判定是 **per-Mech 的**（关键证据）

全文件 `Mech+0x4C4` 共 **74 个引用点**，其中判定分支有 3 种典型写法：

### 写法 A：`>= 0` 才算玩家控制
```
0x2A2DB  cmp  dword ptr [rsi+0x4C4], 0
0x2A2E2  jl   0x2A412              ; <0 → 跳过（AI）
0x2A338  test dword ptr [rsi+0xB58], 0x1CC2   ; ★ 能力位掩码
0x2A365  call 0xD9420              ; 交互判定
0x2A36E  mov  qword ptr [rsi+0xB48], rdi      ; 记录交互目标
```

### 写法 B：`!= -1` 才算有人控制
```
0x2ECE0  mov  byte ptr [r14+0x1E8], 0
0x2ECEA  cmp  dword ptr [rax+0x4C4], -1
0x2ECF1  je   0x2EDD5              ; -1 → 跳过（推进/驾驶逻辑）
...
0x2ED2C  rax = [rax+0x238]; rcx = [rax+0xC8]  ; 读控制参数
```

### 写法 C：`== 0` 单独特判（0 号玩家特殊）
```
0x302AB  cmp  dword ptr [rax+0x4C4], 0
0x302B2  jne  0x30575              ; != 0 → 走另一条（AI 或其他玩家）
0x302BB  call 0xF86F0              ; 0 号玩家专属：读速度/转向
```

### 语义结论

```
Mech+0x4C4 = 控制者索引
    -1      = 无控制者（AI）        ← DisableAI 置此值
     0      = 本地玩家（有专门的特判分支）
    >=1     = 其他玩家索引（引擎预留了位置，但没有输入源/UI 实现）
```

**三点关键：**
1. **判定是每台 Mech 自己的字段**，不是查全局单例 → **多台同时"玩家控制"在架构上合法**。
2. 用的是 `>= 0` / `!= -1` 这种**支持多索引**的写法，不是 `bool isPlayer` → 引擎原设计就留了多玩家位。
3. 0 号玩家有单独的特判分支（写法 C）→ 说明 0 是"本地玩家"，1+ 是"其他人"，这是典型的本地多人/网络多人数据结构。

## 30. 附带发现：③ 层能力是 **per-Mech 位掩码** `Mech+0xB58`

```
0x2A338  test dword ptr [rsi+0xB58], 0x1CC2
0xDEA57  and  dword ptr [rbx+0xB58], 0xFFFFFFDF   ; DisableAI 清掉 0x20 位
```

> 交互/能力判断用的是 `Mech+0xB58` 的**标志位**，不是独立的"能力对象"。
> 所以"给 NPC 补上下车/拾取能力"= **置位 `+0xB58` 的对应 bit**，不需要复制任何对象。
> 这比第五轮推断的"能力挂在 Player 上"更乐观。

## 31. 对本轮假设的判定（静态结论）

用户假设："只要 Mech 被判定为 Player 控制，就会走玩家特有逻辑（读鼠标键盘）"

**判定：成立。** 静态证据链完整：

```
每帧遍历所有 Mech
   └─ if (m->0x4C4 >= 0)          // ← 每台独立判定
        进入玩家控制分支
        └─ 读 InputManager（App+0x28D0，全局唯一）
```

**所以同时存在 N 台 Player 控制的 Mech 时，预期行为是**：
- N 台会**全部**进入玩家分支（不会只有一台）；
- 但它们**读的是同一个 `InputManager`** → 表现为 **N 台同步执行同样的动作**（一起走、一起转）；
- 这正是"验证实验"的可观测现象：**如果多台一起动，就证明判定是 per-Mech、输入是共享单例**，那么只需给每台配独立 `InputManager` 即完成多人输入。

**未验证的残余风险**（需运行期确认，静态无法排除）：
1. 是否存在"只有第一次进入玩家分支才做"的全局副作用（音效监听、UI 绑定、相机绑定）。
2. `App+0x2CA0`（当前玩家）在玩家分支被写入时，是否会覆盖成"最后处理的那台"。
3. 相机跟随：预计会跟随 0 号玩家，多台时可能出现相机抖动。

---

# 第七轮：注入框架设计（减少重启）

## 32. 现状盘点：**项目里已经有一套热重载通道**

| 资产 | 位置 | 热重载能力 |
|---|---|---|
| Proxy SDL2 | `proxy_sdl2/` → 编出 `SDL2.dll` (258KB) | ❌ 装好即固定，改一次要重启 |
| `pa_probe.c` | `proxy_sdl2/src/pa_probe.c` (9.7KB) | ❌ 随 proxy 一起重编 |
| **Lua mod** | `mods/vehicle_spawner/vehicle_spawner.lua` | ✅ **`luaload` 可重复执行，旧回调按代号失效** |
| 游戏控制台 | 控制台命令 `luaload` / `lua` | ✅ 已有 |

README 原文：**"脚本可以重复 `luaload`，不会重复挂逻辑（内部用代号机制让旧回调失效）。"**
→ **Lua 侧的热重载已经是现成的**，不需要造轮子。

## 33. 结论：把 hook 逻辑下沉到 Lua，C++ 只保留 3 个原语

```
第 0 层  proxy SDL2.dll       永不改动（一次装好）
         ├─ 转发 60 个导出
         └─ 向 Lua 暴露 3 个原语：
              bk.read(addr, size)     读内存
              bk.write(addr, size, v) 写内存
              bk.hook(rva, cbName)    可选：拦截执行
第 1 层  mods/*.lua           秒级热重载（luaload 即可）
         └─ 全部实验逻辑：每帧写字段、条件判断、开关、参数
```

### 为什么"每帧轮询"能替代大部分 hook

游戏提供 `register_update_function`（Lua 全局注册函数，第一轮已确认）。
单线程、每帧一次、天然安全：

```lua
local tick = 0
register_update_function(function()
  tick = tick + 1
  if not enabled then return end
  for _, m in ipairs(targets) do
    bk.write32(m.addr + 0x4C4, 1)   -- 把 NPC 标记为玩家 1
  end
end)
```

→ **改 Lua 文件 → `luaload` → 立即生效，零重启、零崩溃风险。**

只有"必须拦截调用瞬间"的场景（如改写 `getAxis` 返回值）才需要 `bk.hook`。

## 34. 分层优先级（按收益排序）

| 优先级 | 做什么 | 收益 |
|---|---|---|
| **P0** | 给 Lua 加 `bk.read/write` | 90% 的实验（改 `+0x4C4`、`+0xB58`、`+0x178`）都能零重启做 |
| **P1** | `bk.hook(rva, cb)` + 安全点重载 | 能拦截执行，仍不用重启 |
| **P2** | payload DLL 热重载（FreeLibrary/LoadLibrary） | 只在 Lua 完全做不到时才需要 |

> **不要一上来做 P2。** 它要处理 trampoline 恢复、CRT 状态、残留线程指针，风险最高、收益最低。
> 现有 Lua 通道已经覆盖了本轮所有实验需求。

## 35. 如果要做 P1，安全点选在 `SDL_PollEvent`

每帧必经（`0x74F74`），此刻除自身外没有 hook 在执行：

```c
int SDL_PollEvent(SDL_Event* ev) {
    if (g_reload_pending) reload_payload();   // 安全点
    return real_PollEvent(ev);
}
```

---

# 第八轮：相机跟谁？（多玩家时的镜头归属）

## 36. "当前玩家"是全局单点 `0xB64838`，且有 306 个读点

`Mech.GetPlayer`（`0x1A86A0`）的实现：

```
0x1A86AD  rcx = [rip+0x9BC184]   → 0xB64838      ★ 全局"当前玩家"
0x1A86B9  call 0x178F30          → 解引用 → Mech*
0x1A86D3  xmm0 = [rdi+0x168]     → 读位置 X（double）
0x1A86EB  ecx  = [rdi+0x170]     → 读位置 Y（float）
```

### 计量结果

| 全局 | 读点 | 写点 | 含义 |
|---|---|---|---|
| **`0xB64838`** | **306** | **2**（`0x169F79`, `0x16DA48`） | 当前玩家（相机/UI/准星/交互都从这里取） |
| `0xB64840` | 5 | 0 | 另一个变量（相邻 8 字节，非玩家） |
| `0xB38850` | 893 | 2（`0x6E184`, `0x6F2B7`） | World 单例 |

`App+0x2CA0`（64 个引用）是**另一层级**的玩家引用，与 `0xB64838` 不是同一个存储位置。

RTTI 全表 **没有 `Camera` 类** → 相机是函数式的，不是对象。

## 37. 结论：相机不会乱，且与输入解耦

```
输入是否响应   →  per-Mech 字段 `Mech+0x4C4 >= 0`   （多台可同时为真）
相机/UI 跟随   →  全局单点 `[0xB64838]`             （永远只有一个）
```

**这是两套独立机制。** 所以同时存在 N 台"玩家控制"Mech 时：

- **N 台都会响应键鼠**（因为判定是 per-Mech）；
- **相机稳定跟随 `[0xB64838]` 指向的那一台**，不会在 N 台之间跳动；
- 唯一的相机会话风险是：`[0xB64838]` 的 2 个写点之一被触发（某个"设置玩家"函数），导致相机瞬移。

### 对改造的意义

只有 **2 个写点** → "切换观察视角"的成本极低。
若要实现"玩家 2 的视角"，把 `[0xB64838]` 在帧内临时指向玩家 2 即可；
但注意 306 个读点分布在渲染/UI/物理各处，**切换必须在帧边界**，不能一帧内切两次。

> 若要分屏多人，则需要把 306 个读点改成"按视口取"—— 这是唯一真正昂贵的地方。

---

# 第九轮：静态复核 —— 被忽略的东西

## 38. `WorldInputs` 签名是真的，但它是纯 POD（这是之前找不到的原因）

`.data` @ `0x499600` 起有 lambda 的 RTTI 名，MSVC mangled 解码后：

```
.?AV<lambda_1>@?DO@??Update@MechFunctions@@YAXAEBUWorldInputs@@
    AEBV?$vector@PEAUMech@@V?$allocator@PEAUMech@@@std@@@std@@
    PEAUPack__GlobalData@@@Z@
→ void MechFunctions::Update(const WorldInputs&,
                             const std::vector<Mech*>&,
                             Pack::GlobalData*)
```

**签名完全确认。** 但注意两点：
1. `AEBUWorldInputs@@` 是 `struct`（`U`），不是 `class`（`V`）→ **纯数据 struct，没有虚函数、没有 RTTI**
2. 这串 RTTI 属于函数体内的 **lambda**，不是函数本身

→ 所以无法用"类名交叉引用"定位函数，只能靠**调用形态**（3 参数 + 遍历 `vector<Mech*>`）反查。
`MechFunctions::Update` 至今**未定位到地址**。

## 39. Order / Command 系统实测：只覆盖 AI，不能当联机协议

### `SetOrder`（`0x1AA040`）

```
0x1AA05F  cmp eax, 3          ; LUA_TNUMBER → 0x1CE0F0(数值 order)
0x1AA07A  cmp eax, 4          ; LUA_TSTRING → 0x1CE1A0(命名 order)
0x1AA0B9  rcx = [World] + 0x2788 ; MechManager
0x1AA0CA  call 0x24C80           ; FindMech
```
→ **order 可以是数字或字符串**（命名命令）。

### `QueueAIState`（`0x1AA110`）

```
0x1AA141  cmp eax, 0x1F       ; ★ 状态值上限 = 31（0..31，共 32 个 AI 状态）
0x1AA180  edx = [rax + 0x4C4] ; 检查控制者 ID
0x1AA186  test edx, edx
```
→ AI 状态是 **0..31 的枚举**，共 32 个。

### 结论

| 接口 | 粒度 | 能表达 |
|---|---|---|
| `SetOrder` / `QueueAIState` | **32 个 AI 状态枚举** | NPC 行为切换 |
| 玩家输入（InputManager） | **逐帧模拟量**（72 action + 12 轴） | 精细驾驶/瞄准/开火 |

**命令抽象只覆盖 AI，玩家的精细输入没有任何"命令层"。**
→ 联机**不能**同步"命令"，必须同步原始输入（或输入产生的结果）。

## 40. 真正被忽略的两件事（架构级）

### ① 每帧只有一个"输入快照"

`App::frame`（`0x74DF0`）的结构已经证明：**输入在帧开头集中采样一次**：

```
0x74F5C  SDL_PumpEvents
0x74F68  InputManager::beginFrame
0x74F74  SDL_PollEvent 循环           ← 事件全部消费完
0x750CC  SDL_GetMouseState
0x750DD~0x7511A  getAxis(9..12)
...之后才是 gameplay 更新
```

→ **多 Mech 要接收不同输入，必须在"输入采集之后、gameplay 之前"逐台替换 `App+0x28D0`（InputManager 指针）并各跑一遍。**
这是 multiplayer 的**结构性改造点**，无法绕过。

### ② 渲染不在 `App::frame` 内（好消息）

`SDL_GL_SwapWindow` 位于 `0x3D300`（`0x3D476`），该函数：
- 无直接调用者
- 不在 `.rdata` / `_RDATA` 的 vtable 里

→ 渲染是通过**间接/回调**驱动的，与 `App::frame` 的 gameplay 分离。
**这意味着把 gameplay 循环化成"N 次玩家更新"不会导致 N 次渲染。** 这是 multiplayer 最有利的一条静态结论。

## 41. 仍未静态确认的三件事

| # | 待确认 | 为什么重要 |
|---|---|---|
| 1 | 固定步长 / 确定性 tick（`0x6D8E0` 帧前处理里是否有累加器） | 决定 lockstep 可行性 |
| 2 | RNG 状态与种子 | lockstep 的前提 |
| 3 | 是否有 replay / 录制（字符串 `Replay` @ `0x3B9640` 已找到） | 若有，等于白送一份输入序列协议 |

---

# 第十轮：AI 状态机在 Lua 的暴露程度（含重大发现）

## 42. 三个 API 的精确约束（反汇编确认）

### `GetAIState`（`0x1AA1C0`）— 只读

```
0x1AA1F3  edx = [m + 0x4C4]
0x1AA1F9  test edx, edx
0x1AA1FB  js   0x1AA228      ; <0 → 返回 nil
0x1AA1FD  rcx = [m + 0x550]
0x1AA204  rcx = [rcx + 0x50]      ; 控制子系统
0x1AA208  call 0xE5CC0            ; 取当前状态
0x1AA218  call 0x318A10           ; push number
```
→ 返回**数字**，要求 `+0x4C4 >= 0`。

### `QueueAIState`（`0x1AA110`）— 写入

```
0x1AA141  cmp eax, 0x1F           ; 状态值上限 = 31
0x1AA180  edx = [m + 0x4C4]
0x1AA186  test edx, edx
0x1AA188  jle 0x1AA1A0            ; ★ <=0 → 直接跳过，什么都不做
0x1AA19B  call 0xE7A80            ; 提交指令
```
→ 要求 **`+0x4C4 > 0`（严格大于 0）**，值域 `0..31`，**无返回值**（恒 `xor eax,eax`）。

### `SetOrder`（`0x1AA040`）— 写入

```
0x1AA05F  cmp eax, 3   ; LUA_TNUMBER → 0x1CE0F0（数值 order）
0x1AA07A  cmp eax, 4   ; LUA_TSTRING → 0x1CE1A0（字符串 order）
0x1AA0DF  call 0xDCA40        ; ★ order 的真正实现
0x1AA0E4  movzx edx, al
0x1AA0EE  call 0x318790       ; push boolean
```
→ 返回**布尔**，实现是 `0xDCA40(mech, orderId)`。

## 43. ★ 重大发现：`+0x4C4 > 0` 是「第二玩家及以上」的代码路径

把三个判定并列看：

| API | 判定 | 结论 |
|---|---|---|
| `GetAIState` | `+0x4C4 >= 0` 才可读 | 0 和 1+ 都可以读 |
| `QueueAIState` | **`+0x4C4 > 0`** 才可写 | **0（本地玩家）被排除，只有 1+ 能写** |

**这个不对称不是 bug，是设计：**

```
+0x4C4 = -1  → 纯 AI，不接受 AI 状态覆盖
+0x4C4 =  0  → 本地玩家，不允许被 AI 状态覆盖（保护主视角）
+0x4C4 >= 1  → 其他玩家，允许 AI 覆盖（因为没有人真的在控制它）
```

> **`QueueAIState` 从设计上就是给"玩家 2、3…"用的。**
> 引擎里存在一条**专门服务于"非主视角玩家"的代码路径**，且是完整的（能读状态、能下状态、能走控制子系统）。
> 这是"引擎原本预留了多玩家"的最强静态证据，比之前 `cmp ..., 0` 的推断更硬。

## 44. ★ 统一命令分发器 `0xE7A80`

两个不同 API 都收敛到同一个函数：

```
MoveTo      : 0x1A96C9  call 0xE7A80(ctrl=[m+0x550]+0x50, id=[m+0x4C4], 3, 0)
QueueAIState: 0x1AA19B  call 0xE7A80(ctrl=[m+0x550]+0x50, id=[m+0x4C4], state, 0)
```

签名推测：

```cpp
bool dispatch(uintptr_t ctrl,       // [Mech+0x550]+0x50 控制子系统
              int       ownerId,    // Mech+0x4C4
              int       cmd,        // 3=移动，0..31=AI状态
              int       arg,
              int       reserved);
```

**这是目前找到的最接近"输入注入点"的结构**：
- 它是**所有单位指令的公共出口**
- 它接受 `ownerId`（明确区分是哪个控制者在下令）
- 它是普通函数（可直接调用），不是虚函数

→ 若要在运行期验证"多玩家"，`0xE7A80` 是最干净的观察点/调用点。

## 45. 对"用 Lua 做 AI 队友"的实际建议

| 目的 | 用哪个 | 原因 |
|---|---|---|
| 给 NPC 下命令 | **`SetOrder`**（`0xDCA40`） | 参数宽松，返回成败，支持命名 order |
| 读 NPC 的 AI 状态 | ❌ **做不到** | `GetAIState` 对 `+0x4C4 < 0` 返回 nil |
| 强制改写 NPC 状态 | ❌ **做不到** | `QueueAIState` 要求 `> 0`，NPC 是 `-1` |
| 让 NPC 移动 | `MoveTo` / `Halt` | 已验证可用 |

> **结论：Lua 能"指挥"NPC，但看不到也改不了它的内部状态机。**
> 状态机对外只有"编号"，没有状态图、没有转移条件、没有优先级 —— 这些都在 C++ 里。

## 46. 未暴露（Lua 层完全拿不到）的东西

- AI 状态名称（`SetOrder` 的字符串走 `0x1CE1A0` → `0xF4920` 字符串 intern + FNV-1a 哈希表，名字在 Pack 数据里）
- 状态转移条件 / 优先级 / 权重
- 威胁评估过程（只有结果 `GetUnitThreat`）
- 目标选择（`GetPlayerHovered` 只是"玩家指向谁"）
- 开火决策（完全不可见）

---

# 第十一轮：SetOrder 能设什么？（完整清单）

## 47. `SetOrder` 的实现（`0xDCA40`）

```
0x0DCA4A  cmp byte ptr [m + 0x2AC], 0
0x0DCA57  je  fail                    ; +0x2AC == 0 → 失败
0x0DCA59  cmp dword ptr [m + 0x4C4], 0
0x0DCA60  jl  fail                    ; ★ +0x4C4 < 0 → 失败
0x0DCA65  call 0x1CD710               ; 验证 order 对象
0x0DCA6E  cmp dword ptr [order + 0x38], 0
0x0DCA8A  m + 0xBF0 = order           ; ★ order 对象存这里
0x0DCA84  r8d = 0xC                   ; ★ cmd = 12 下发给控制子系统
0x0DCA95  call 0xE7A80
```

- order 参数是**对象**（不是枚举）
- 存在 `Mech+0xBF0`，共 12 个引用点
- 下发用统一分发器 `0xE7A80`，`cmd=12`

## 48. ★ AISTATE 完整枚举表（`.rdata` @ `0x3BBEF0`，明文可读）

```
BENCH_MEETING            INTEREST_POINT           TRANSIT
PLAYER                   AMBUSH                   SEARCH
GOTO_LAST_KNOWN          SUS_INVESTIGATE          FLEE
IDLE                     STATIONARY_SHOOT         GOTO_FIRING_POS
RETREAT                  FLANK                    ORDER_MOVETO
ORDER_GETIN              ORDERED_DELAY            WAITING
NORMAL_GOTO_FIRING_POSITION   NORMAL_SHOOT_TARGET
NORMAL_INVESTIGATE_POSITION   FLATFOOTED
BIKEJOUST_JOUST          SERPENTINE_GOTO_FIRING_POSITION
SERPENTINE_* (截断)       VETO
```

这些是**战术级行为**，不是简单移动：
- `GOTO_FIRING_POS` / `NORMAL_SHOOT_TARGET` / `STATIONARY_SHOOT` → 战术射击位
- `FLANK` / `RETREAT` / `AMBUSH` / `SERPENTINE_*` → 机动战术
- `BIKEJOUST_JOUST` → 载具骑兵战术（专用）
- `ORDER_MOVETO` / `ORDER_GETIN` → 脚本指令通道

## 49. ★★ 关键实践结论：`DisableAI` 会让所有 order 失效

三个 API 的前置条件并列：

| API | 前置条件 | 失败后果 |
|---|---|---|
| `GetAIState` | `+0x4C4 >= 0` | 返回 nil |
| `QueueAIState` | `+0x4C4 > 0` | 静默跳过 |
| **`SetOrder`** | **`+0x4C4 >= 0`** 且 `+0x2AC != 0` | **返回 false** |

而 `Mech::DisableAI`（`0xDE910`）最后一步正是：

```
0x0DEA7B  m + 0x4C4 = -1
```

> **所以：`DisableAI()` 之后，`SetOrder` / `QueueAIState` / `GetAIState` 全部失效。**
> 这极可能就是此前"AI 队友不听指挥 / NPC 状态读不到"的根因。
> **正确顺序应是：先下 order，最后才考虑 DisableAI（如果确实需要）。**

## 50. order 的两类来源

### A. AISTATE 枚举（固定，`0x3BBEF0` 明文表）
C++ 注册为 Lua 全局表 `AISTATE.WAITING` / `AISTATE.FLEE` / ...（脚本中共用到 9 个：
`AMBUSH, FLEE, GOTO_LAST_KNOWN, IDLE, ORDERED_DELAY, SEARCH, STUNNED, WAITING, WATCHFUL`）

### B. 命名 order（字符串，**可自定义**）
关卡脚本用法：
```lua
local order_id = arg.properties.order      -- ★ order 名来自关卡对象属性
mech:SetOrder(order_id)
mech:SetOrder("appear")
```
内置的 `"appear"` 在 exe 里（`0x3B9842` 是编辑器字符串，非 order 表）；
而 `"JoveRun"` / `"DriverGetIn"` / `"DriveAway"` / `"PickUpBulver"` **不在 exe 里** →
**它们是关卡数据自定义的 order 名**。

> `SetOrder` 的字符串走 `0x1CE1A0` → `0xF4920` 字符串 intern → FNV-1a 哈希表（`0xBBD268`）
> → **order 注册表是运行期 unordered_map，所以自定义 order 完全可行。**

## 51. 控制子系统是"按通道索引"的（多玩家又一条证据）

`0xE9A60`（order/状态消费端）：

```
0x0E9A66  rdi = r8d                  ; ★ 通道索引
0x0E9A6C  r10 = [rax + rdi*4]        ; 索引表
0x0E9A7B  rcx = [[rax+0x160]+0x48][r10*8]   ; 按索引取 Mech*
0x0E9A7F  rax = [rcx + 0xBF0]        ; 取该单位的 order
```

`0xEF540` 同样用 `r14` 作通道索引，访问 `[ctrl+0xa8]` / `[ctrl+0xb8]` / `[ctrl+0x50]` / `[ctrl+0xd0]`
全部是 `base + idx*4` 的**并行数组**。

> **控制子系统原生就是 N 通道结构**，每个通道有独立的状态数组、计时数组、order 指针。
> 这是"引擎原本为多玩家/多控制者设计"的第三条硬证据（前两条：`+0x4C4 > 0` 分支、`0xE7A80` 带 ownerId）。

---

# 第十二轮：companion 为什么不主动攻击（根因）

## 52. BEHAVIOR 完整枚举（`.rdata` @ `0x3ABFB0`，明文）

```
BEHAVIOR_PLAYER
BEHAVIOR_NORMAL
BEHAVIOR_BIKEJOUST
BEHAVIOR_SERPENTINE
BEHAVIOR_CIVILIAN
BEHAVIOR_TANKDESTROYER
BEHAVIOR_INFANTRY_AIMSHOOT      ← 步兵瞄准射击
BEHAVIOR_WAIT
BEHAVIOR_NULL                   （脚本里 `local behavior = 10`，说明有偏移）
BEHAVIOR_DELAYED_NEXT_STATE_OVERRIDE_BUG
```

**没有 "AGGRESSIVE" 之类的项** → 主动攻击不是靠切换 behavior 实现的。

官方对照（`e01_h00_m01_hospital.lua:167`）：
```lua
Mech.Create("car_cop_sedan_01.json", pos, orient,
            BEHAVIOR.BEHAVIOR_NORMAL, TEAMS.ENEMY_TEAM, loadout)
```
→ **敌人也用 `BEHAVIOR_NORMAL`**，与队友相同。差别只在 `TEAM`。

## 53. ★ 根因：每帧 `MoveTo` 把单位钉死在 `ORDER_MOVETO` 状态

`MoveTo`（`0x1A9640`）最后做两件事：

```
0x1A96BB  mov dword ptr [m + 0x1D8], 6      ; ★ 行为状态 = 6
0x1A96C9  call 0xE7A80(ctrl, [m+0x4C4], 3, 0)
```

而 `AISTATE` 表里正好有：

```
ORDER_MOVETO
ORDER_GETIN
```

且 order 消费端 `0xE9A60` 也有同样的写入：

```
0x0E9B00  mov dword ptr [r9 + rdi*4], 6
```

> **`Mech+0x1D8` 是每通道的行为状态机当前值，`6` = `ORDER_MOVETO`。**

`vehicle_spawner.lua` 的跟随逻辑（L363–375）：

```lua
if dist2 > follow_range * follow_range then
    m:MoveTo(Vec2.New(gx, gy))
end
```

在 `register_update_function` 里**每帧执行**。距离超过 8 单位就每帧重发 `MoveTo`
→ **状态机每帧被重置为 6（ORDER_MOVETO）**
→ AI 永远没有机会进入 `WATCHFUL` / `SUS_INVESTIGATE` / `SEARCH` / `GOTO_FIRING_POS`
→ 视野里出现敌人也不会主动交战。

**为什么"被打了会反击"：受伤是事件驱动的即时反应，不经过这条行为状态机**，所以它能正常工作。

这也解释了此前的其他怪现象：
- `GetAIState()` 读不到（对 `+0x4C4 < 0` 返回 nil）
- `Halt()` 无效（`MoveTo` 每帧又覆盖）
- 队友"看起来在跟随但从不主动开火"

## 54. 三个修复方向（静态推导，未实测）

| 方案 | 做法 | 副作用 |
|---|---|---|
| **A. 间歇下发** | 发一次 `MoveTo` 后锁定 1.5～2 秒不再发 | 跟随略有滞后，但能给 AI 留出交战窗口 |
| **B. 距离分级** | 近距离完全不干预（让 AI 自由交战）；只有距离 > 25 才补一次 `MoveTo` | 跟随会明显掉队，但战斗表现最好 |
| **C. 传送兜底** | 平时不发指令，只在距离 > 40 时 `SetPosition` 到玩家附近 | 完全不碰状态机；但会出现"瞬移" |

**推荐 A + B 组合**：近处完全不管（让它打），远处才拉一次，且拉完就停手。

`BEHAVIOR_INFANTRY_AIMSHOOT` 也值得一试——名字直译是"步兵瞄准射击"，可能是专门为
"站定主动开火"设计的行为；但它不改上面的状态覆盖问题，优先级低于 A/B。

---

# 第十三轮：team 对 team 的敌对关系在哪里？

## 55. 结论：**不在配置里，是硬编码的**

### `TEAMS` 枚举（`.rdata` @ `0x48A8B0` 的枚举名表）

```
PLAYER_TEAM   = 0
ENEMY_TEAM    = 1
CIVILIAN_TEAM = 2
MAX_TEAMS     = 3
```

**只有 3 支队伍。**

### 配置文件里没有任何敌对关系

`assets/data/loyalties/` 下 10 个文件，全部只有一行：

```json
{ "archetype": "FIDELIS", "fidelis": "PLAYER" }
```

```
fidelis_player.json    fidelis_cop.json      fidelis_loyalist.json
fidelis_brigador.json  fidelis_chobber.json  fidelis_corvid.json
fidelis_civ.json       fidelis_SNC.json      fidelis_spacer.json
fidelis_unknown.json
```

**全项目搜 `"fidelis"` 只命中这 10 个文件，没有任何"谁敌视谁"的定义。**
→ 敌对矩阵是 **C++ 硬编码**。

### 重要区分：`TEAM`（3 个）≠ `FIDELIS`（10 个）

| 概念 | 数量 | 用途 |
|---|---|---|
| `TEAM` | 3（PLAYER/ENEMY/CIVILIAN） | 粗分类，`Mech.Create` 第 5 参数 |
| `FIDELIS` | 10（PLAYER/COP/LOYALIST/BRIGADOR/CHOBBER/CORVID/CIV/SNC/SPACER/UNKNOWN） | **派系/忠诚度，可能才是真正的敌对判定依据** |

## 56. `Mech.Create` 的参数传递链

```
0x1A87DC  orient  = lua_tonumber(3)
0x1A87EC  pos     = lua_touserdata(2)
0x1A87FF  path    = lua_tostring(1)
0x1A87BC  behavior= lua_tointeger(4)     → rdi
0x1A87CC  team    = lua_tointeger(5)     → r15   ★
0x1A87AC  loadout = lua_tostring(6)      → rsi
...
0x1A8860  if (behavior == -1) behavior = [packData + 0x3494]   ; 默认值来自数据
0x1A88A7  [rsp+0x20] = r15d              ; ★ team 作为第 5 个栈参数
0x1A88AC  call 0x18A050                  ; World::SpawnMech(..., team, behavior, loadout)
```

`0x18A050` 内部把 team 搬到 `[rsp+0x1D8]`（第 5 参数），再往下传给实际构造。

## 57. 尚未解决：敌对判定到底读 team 还是 fidelis

由于矩阵硬编码在 C++，要改必须定位判定函数。目前有两条候选路径：

| 假设 | 现象解释 | 验证方式 |
|---|---|---|
| **H1：矩阵是对称的，但 PLAYER 队 AI 的索敌被禁用** | ENEMY 队完整索敌；PLAYER 队只保留"受伤反击" | 让队友进 ENEMY 队，看它是否攻击玩家 |
| **H2：矩阵不对称，PLAYER→ENEMY 不敌对** | 同上，但根因在数据 | 同上，结果一样 |

**两种假设在静态上无法区分**（因为官方从不生成 PLAYER 队的 AI 单位，没有任何运行时样本）。

→ **必须靠一次最小运行验证**：把 companion 的 team 改成 `TEAMS.ENEMY_TEAM`，观察它是否转而攻击玩家。
- 若**攻击玩家** → 矩阵对称，问题在"PLAYER 队 AI 索敌未启用"，需要 patch 索敌层
- 若**连玩家也不打** → team 值本身没生效，`fidelis` 才是真正的判定依据

## 58. 若要"不重启验证"，这条路必须先有内存写

`Mech.Create` 的 team 是创建时固定的，Lua 无法事后改。
所以要动态试 H1/H2，仍然需要能写 `Mech+team偏移`（偏移未定位）或重新 Create。

**但 `Mech.Create` 本身支持传任意 team** ——
所以最省事的验证是：**新建一个 `TEAMS.ENEMY_TEAM` 的 companion 副本**，
看它是否攻击玩家。这一步纯 Lua 就能做，不需要内存写。

---

# 第十四轮：在二进制里找 team 敌对关系（结果：team 不是判定依据）

## 59. 逐层排除过程

### ① `Mech.Create` 第 5 参数 = team，但只用来计数

栈帧换算（push 8 + sub 0x168 = 0x1A8）：

| 原始栈参数 | 换算后 | 含义 | 去向 |
|---|---|---|---|
| `[rsp+0x20]` | `[rsp+0x1C8]` | — | — |
| `[rsp+0x28]` | `[rsp+0x1D0]` | **team** | → `esi` @ `0x18A0AA` |
| `[rsp+0x30]` | `[rsp+0x1D8]` | behavior | → `r12d` → `[obj+0x60]` ⭐ |
| `[rsp+0x38]` | `[rsp+0x1E0]` | loadout | → `rax` |

`0x18A050` 里 team（`esi`）的全部使用点：

```
0x18A1F2  cmp esi, 1                ; team == ENEMY_TEAM
0x18A1FB  inc qword ptr [rax + 0x1CA10]   ; ★ 敌人计数++
0x18A204  cmp esi, 2                ; team == CIVILIAN_TEAM
0x18A20D  inc qword ptr [rax + 0x1CA30]   ; ★ 平民计数++
```

> **team 只用于两件事：边界校验 + 世界统计计数器。**
> **它没有被写到 `Mech` 的任何明显字段里。**
> `[rsp+0x1D0]` 之后 esi 即被复用为指针，说明值已"消费完毕"。

### ② 排除的高频候选偏移（全部证伪）

在 `insns.pkl` 上做统计（`cmp dword ptr [reg+off], 0|1|2`）：

| 偏移 | 命中 | 实际含义 |
|---|---|---|
| `+0x0010` | 66 | App 帧循环内的枚举（UI/输入） |
| `+0x0020` | 53 | 通用枚举 |
| `+0x003C` | 25 | 载具状态 |
| `+0x0144` | 15 | 玩家交互判定（`0x2A2F5`） |
| **`+0x0044`** | 32（双对象比较） | ❌ **数组长度**：`cmp edx, [rcx+0x44]` + `jge` 是边界检查 |
| **`+0x00C4`** | 28（双对象比较） | ❌ 同一控制子系统的另一计数 |

验证 `+0x44`：
```
0x0E5CC4  cmp edx, dword ptr [rcx + 0x44]   ; edx < count ?
0x0E5CC7  jge 0xE5CDF                        ; 越界返回
0x0E5CC9  mov r8, qword ptr [rcx + 0xD0]     ; 取数组指针
```
典型的 `{size@+0x44, ptr@+0xD0}` 容器布局，与 team 无关。

### ③ 用 `.pdata` 扫"敌对矩阵小函数"—— 零命中

设想形态（两个 0..2 参数互相比较、函数 < 40 条指令）：**0 个候选**。
→ 敌对关系**不是**用 `int teamA, int teamB` 的查表/分支函数实现的。

## 60. 结论与转折：判定依据很可能是 `FIDELIS`，不是 `TEAM`

已确认的事实：

1. `TEAMS` 只有 3 值，且 `team` 参数**基本只用于统计**
2. 配置文件里 10 个 `fidelis_*.json` 只有名字，**没有关系矩阵**
3. 二进制里找不到"3×3 team 敌对函数"

→ **`TEAM` 是粗分类（玩家/敌人/平民），真正的敌对判定走 `FIDELIS`（10 个派系）。**

这解释了为什么"给 companion 设 PLAYER_TEAM 它不主动打"：`PLAYER_TEAM` 只是"玩家阵营"的
统计归属，**并不携带"我敌视 COP"这条信息**。

## 61. 下一步（优先级）

| # | 目标 | 方法 |
|---|---|---|
| **1** | 找 `fidelis` 字段在 `Mech` 的偏移 | 从 `0x3DC400`("fidelis") / `0x3DE281`("FIDELIS") 的代码引用反查加载器 |
| **2** | 找 fidelis 对比较函数 | 搜 `cmp reg, [reg+off]` 且 off 值来自 fidelis 存点 |
| **3** | 找 `Mech.Create` 是否接受 fidelis | 若接受，则纯 Lua 就能给 companion 指定派系 |

**注意**：`fidelis_*.json` 里的 `"fidelis": "PLAYER"` 说明这是**单位数据层**的字段
（每个 unit json 引用一个 fidelis），而不是运行时参数。所以更可能是：
```
unit.json → fidelis 名 → 查表得 fidelis ID → 存进 Mech
```
若要改，可能要换一个单位 json，或改 Mech 的 fidelis 字段。

---

# 第十五轮：companion 的派系是 BRIGADOR（关键发现）

## 62. companion 的 fidelis = BRIGADOR

`mods/vehicle_spawner/vehicle_spawner.lua` 用 `DEFAULT_VEHICLE = "assets/data/vics/units/rig_volta_carmine_01.json"`。

该文件第 9 行：

```json
"loyalty_data": "assets/data/loyalties/fidelis_brigador.json"
```

`fidelis_brigador.json`：`{"archetype":"FIDELIS","fidelis":"BRIGADOR"}`

**`Mech.Create` 没有 fidelis 参数** —— 派系完全由载具 json 的 `loyalty_data` 决定。

> **companion 的 fidelis = `BRIGADOR`。**

## 63. ★ 数据分布揭示了 BRIGADOR 的真实身份

`assets/data/vics/units/*.json` 的 `loyalty_data` 统计（共 198 个）：

| fidelis | 单位数 |
|---|---|
| **brigador** | **115** |
| unknown | 22 |
| cop | 17 |
| corvid | 16 |
| chobber | 12 |
| civ | 6 |
| spacer | 4 |
| SNC | 3 |
| loyalist | 2 |
| **player** | **1** |

**`fidelis_player` 只有 1 个单位：`foot_exit_sweats_01.json`（步兵）。**

结论：

```
fidelis_player  = 1 个步兵单位    ← 玩家本体/撤退点
fidelis_brigador = 115 个单位     ← 玩家的全部可驾驶载具库
```

> **`BRIGADOR` 在引擎里就是"玩家载具派系"。**
> 原版游戏中这批载具**永远由玩家驾驶**（`Mech+0x4C4 >= 0`），
> **从未作为 AI 单位出现过**。

## 64. 为什么 companion 不主动攻击（最终解释）

三条事实叠加：

1. companion 的 fidelis = `BRIGADOR`（玩家载具派系）
2. `Mech.Create(..., TEAMS.PLAYER_TEAM)` 只影响统计计数，**不改派系**
3. 原版里 `BRIGADOR` 载具从不由 AI 驱动 → **该派系的 AI 索敌路径从未被需要/未实现**

同时，敌人（COP/CORVID/CHOBBER）攻击 companion 是**正确的** ——
在它们的敌对表里 BRIGADOR 就是目标。

**不对称由此成立**：`COP → BRIGADOR` 敌对（敌人会打它），
`BRIGADOR → COP` 在 AI 层没有实现（它是玩家派系，玩家自己看屏幕索敌）。

## 65. 可行的解法方向

| # | 方案 | 说明 |
|---|---|---|
| **A** | 给 companion 换一个**敌视 COP 的派系** | 复制一份 unit json，改 `loyalty_data` 指向 `fidelis_loyalist` / `fidelis_SNC` 等，再用 `Mech.Create` 生成 |
| **B** | 用**敌人载具**（COP 等）当 companion，但 `team = PLAYER_TEAM` | AI 索敌正常，但它会被原派系视为友军、被玩家派系视为敌人（需验证） |
| **C** | 放弃"AI 自主索敌"，用 `SetOrder` / `QueueAIState` 强制下命令 | 但需要 `Mech+0x4C4 >= 0`，会把 companion 变成"受控单位" |

**方案 A 最干净**：只改一个 JSON 的 `loyalty_data`，不改 exe、不改 Lua 逻辑。

**需要先确定的**：哪个 fidelis 派系在 AI 矩阵里敌视 `COP`。
候选：`LOYALIST`（2 单位）、`SNC`（3 单位）、`CORVID`（16 单位）。
`CORVID` 单位多且独立派系，最可能是敌对势力之一。

---

# 第十六轮：Davio Causeway 推翻"BRIGADOR 无 AI"假设

## 66. 用户提供的关键反例

**Davio Causeway**（支线 mission，非剧情）：
- 里面出现来自**多个不同 FIDELIS** 的 unit
- **全部 hostile**，会主动 engage 玩家
- **其中包含与 companion 同款的 BRIGADOR 载具**

> **这直接推翻 §64 的推论。**
> 如果 Davio Causeway 里的 BRIGADOR 载具 AI 会打玩家，
> 那 **BRIGADOR 派系的 AI 索敌逻辑是完整实现的**，不是"从未被调用"。

## 67. ★★ 由此推出的关键假设：判定用的是 `+0x4C4`，不是 fidelis

用户的另一个观察是决定性的：

> "Player 永远都是没有这个 friendly NPC，严格意义上 fight with you 的那种 NPC 是没有的，
>  最多就是 civilian。所以要看它到底是哪个 team，**只能看 player 自身控制的那一个 Mech**。"

### 逻辑推演

玩家的 Mech 开的是 **BRIGADOR 载具**（`rig_volta_*`），所以：

```
玩家 Mech         fidelis = BRIGADOR   （因为是 BRIGADOR 载具）
Davio 的敌人单位   fidelis = BRIGADOR   （同款载具）
```

**两者 fidelis 完全相同！**

→ **fidelis 无法区分"玩家"和"敌人"**
→ **判定必须依赖另一个字段**
→ 唯一符合的候选：**`Mech+0x4C4`（控制者索引）**

```
玩家 Mech         +0x4C4 = 0    （被玩家控制）
Davio 的 BRIGADOR 敌人  +0x4C4 = -1  （AI）
companion         +0x4C4 = -1   （AI）
```

### 统一模型（假设）

```
AI 的攻击目标 = { Mech | Mech->0x4C4 >= 0 }   // "被任何人控制"的单位
```

这个模型能解释**全部**已知现象：

| 现象 | 解释 |
|---|---|
| Davio Causeway 里各派系都打玩家 | 玩家 `+0x4C4 = 0` ✓ |
| 不同 fidelis 之间不互相打 | 全是 `+0x4C4 = -1` ✓ |
| companion 不主动攻击任何东西 | 它也在找 `+0x4C4 >= 0` 的目标——而**只有玩家满足** |
| companion 不打玩家 | 它 `team = PLAYER_TEAM`，与玩家同 team，被排除 ✓ |

### ⚠️ 唯一与用户观察冲突的点

用户曾说"敌人会 hit companion"。按上面的模型，companion `+0x4C4 = -1` 不该成为目标。

可能的解释（需复核）：
1. 敌人的**范围伤害**波及到它
2. 观察时 companion 恰好挡在敌人与玩家之间
3. 有第二条独立的判定路径（例如 team 不同也算敌对）

## 68. 回去要读的三个值（方法已定）

以**玩家自己控制的 Mech** 为唯一基准，读同一台载具在两种状态下的字段：

| 字段 | 玩家 Mech | Davio 的 BRIGADOR 敌人 | companion |
|---|---|---|---|
| `+0x4C4` 控制者 | `0` | `-1` | `-1` |
| `+0x60` behavior | ? | ? | `1` (NORMAL) |
| team | `PLAYER_TEAM` | `ENEMY_TEAM`? | `PLAYER_TEAM` |
| fidelis | `BRIGADOR` | `BRIGADOR` | `BRIGADOR` |

**关键**：如果玩家和敌人的 `+0x60` / team / fidelis 全部相同，
**那 `+0x4C4` 就是唯一的敌我开关** —— 这将是整个 multiplayer 项目最重要的一条结论。

## 69. 对 multiplayer 的直接含义

若模型成立：

```
AI 把"+0x4C4 >= 0"等同于"这是必须攻击的目标"
```

那么**把 companion 的 `+0x4C4` 设为 1（"玩家 2"）**会同时产生两个效果：

1. ✅ 所有 AI 都会攻击它（因为它变成"受控单位"）
2. ❓ 它自己是否攻击别人 —— 取决于 AI 索敌是否也认 `+0x4C4`

**这正好回到用户最初想做的实验**：多台 `+0x4C4 >= 0` 的 Mech。
现在这个实验有了双重意义 —— 它同时验证"多人输入"和"AI 队友"两件事。

---

# 第十七轮：★★ 真正的敌我机制是关卡数据里的 `is_enemy`

## 70. 突破：敌对关系是**每个 spawn 的布尔属性**，不是 team/fidelis

### 关卡数据侧（`assets/levels/bkl_causeway.json`）

每个 spawn 对象都带一组属性：

```json
{ "name":"is_enemy",       "type":"string", "value":"false" }
{ "name":"morale_profile", "type":"string", "value":"" }
{ "name":"loadout",        "type":"string", "value":"" }
{ "name":"inventory",      "type":"string", "value":"" }
{ "name":"buddha",         "type":"bool",   "value":false }   // 无敌
{ "name":"immovable",      "type":"string", "value":"false" }
{ "name":"dest_radius",    "type":"float",  "value":1 }
{ "name":"offset_x" / "offset_y" ... }
```

`bkl_causeway.json` 里 `"name":"is_enemy"` 出现 **30+ 次**，值 `"true"` / `"false"`。

> **Davio Causeway 之所以"所有派系全部 hostile"，
> 是因为那个关卡把每个 spawn 的 `is_enemy` 都设成了 `"true"`。**
> 与 team 无关，与 fidelis 无关。

### exe 侧（`0x181ACF`，属性解析函数）

```
0x181ACF  lea rdx, "is_enemy"
0x181AD9  call 0x1FF240            ; 取属性字符串
0x181AE1  movzx edx, [rax + rcx]   ; 逐字节比较
0x181AEE  cmp rcx, 5               ; ★ 5 个字符
0x181AF8  sete byte ptr [rsp + 0x56]   ; == "false" ? 1 : 0
```

`cmp rcx, 5` 正是 `"false"` 的长度。同一函数紧跟其后解析：

```
0x181B00  lea rdx, "buddha"
0x181B15  lea rdx, [0x3CF494]      ; 另一个属性
0x181C19  lea rdx, "immovable"
0x181CA0  lea rdx, "morale_profile"
```

→ 这是一个**关卡对象 spawn 配置解析器**（`0x1819F3` ~ `0x18230F`）。

## 71. 三个模型全部被修正

| 假设 | 状态 |
|---|---|
| 敌我看 `TEAM`（3 值枚举） | ❌ 证伪：`Mech.Create` 的 team 参数只用于统计计数 |
| 敌我看 `FIDELIS`（10 派系） | ❌ 证伪：玩家和 Davio 敌人同为 `BRIGADOR`，却互相攻击 |
| 敌我看 `+0x4C4`（控制者） | ⚠️ 部分成立，但解释不了"companion 被攻击" |
| **敌我看 `is_enemy` 标记** | ✅ **与全部观察一致** |

`is_enemy` 模型能解释：

- Davio Causeway 里所有派系都打玩家 → 那些 spawn 全标了 `is_enemy:true`
- 不同派系之间不互相打 → 都是 `is_enemy:true` 的**同类标记**（彼此不算敌对）
  - 注意：如果"is_enemy"只表示"敌视玩家"，那 AI 之间自然不互打
- companion 被打 → 取决于 `Mech.Create` 生成的单位 `is_enemy` 默认值
- companion 不打别人 → 它没被标记为"需要追击玩家"

## 72. ★ 这对项目的意义：敌人标记是可以改的配置，不是硬编码

| 手段 | 可行性 |
|---|---|
| 改关卡 JSON 的 `is_enemy` | ✅ **纯数据，不改 exe** |
| 给某个 spawn 改成 `false` | ✅ 它就不再敌对玩家 |
| 让 companion 参与战斗 | ❓ 需要知道 `Mech.Create` 的 `is_enemy` 默认值 |

**下一步（静态）**：确认 `is_enemy` 解析结果最终写进 `Mech` 的哪个偏移。
`[rsp+0x56]` 在 `0x1819F0~0x182420` 内只被写、未被读，说明它被搬到了更深的栈帧
或作为参数传给了 `0x181D3A` / `0x181D65` 调用的 `0x189200`（疑似 spawn 入口）。

**下一步（数据）**：在某个关卡里把单个 spawn 的 `is_enemy` 改成 `false`，
观察该单位是否停止攻击玩家 —— 这是最直接的验证，且零风险。

## 2026-11-23 运行时换载具类：全自动链路（bkswap.dll）

结论：Lua 控制台（主线程）内一次性完成 morph → copy → respawn，已实测 Volta→Cinderblock 成功，无需手点调试面板。

### 关键事实
- 资源换装必须用「已加载」的运行时资源：resarr[idx] 非 0 才可拷贝；关卡外的载具（如 rig_faber_01）resarr=0，无法直接换。
- 目标资源取运行时内存（18448B），LEG 由 MECH+0xC0 指向（4528B）；clone 槽 = assets/data/vics/corpse_civ_tuktuk_01.json（idx 9990）。
- 保留运行时非重定位槽：MECH+0x3338、LEG+0x11A0；写回后 MECH+0xC0 = 克隆 LEG。
- mech 解析链（面板同款）：ctrl=[base+0xB64838] → game=[ctrl+0x40] → state=game+0x1C468 → key=[state+0x30]（key[0] 必须为 0）→ container=[state] → mech=0x140024C80(container,key)。
- Copy=0x1401AE1C0(mech, res_root+0x2D28)；Respawn=0x1401892C0(ctrl, res_root+0x2D28)。blob 先由 Copy 用 mech+0x258（unit 资源）序列化，再被 Respawn 拷进 game+0x1E9C8。
- mech+0x258 == clone 资源指针，可作为身份校验。

### 工具
- mods/native/bkswap/bkswap.c（导出 luaopen_bkswap）；命令文件 %TEMP%\bk_swap.txt：diag / morph / copy / respawn / go <path>；日志 %TEMP%\bk_swap.log。
- 编译：C:\bk\build_bkswap.bat（VS18 vcvars64 + cl /LD /utf-8）。DLL 被进程占用时改输出文件名。
- 控制台：lua local f,e=package.loadlib("C:/bk/bkswap2.dll","luaopen_bkswap"); if f then f() print("OK") else print(e) end
- 已加载载具清单可用 rtmem.py 扫 resarr（本次关卡 190 个 arch14/11/13）。

## 2026-11-23 设计需求：mod 热切换接口 + 玩家私有 dummy（隔离敌人）

目标：把换类能力做成可复用接口，供后续 mod 热切换；核心是「玩家上车瞬间」自动生成 dummy，玩家实际用 dummy，原型资源不动，敌人数据不受影响。

### 接口（C ABI，bkswap.dll 导出）
- int  bks_swap(const char* asset_path)   立即换到指定载具：目标运行时资源 → 玩家私有槽 → copy+respawn
- int  bks_swap_loaded(int resarr_idx)     同上，按索引
- void* bks_player_unit()                  玩家当前 MECH 资源指针（应恒等于 dummy 槽）
- void* bks_player_mech()                  玩家 mech 对象
- int  bks_auto(int on)                    自动接管开关
- const char* bks_last_error()
- Lua 侧仍用 luaopen_bkswap + %TEMP%\bk_swap.txt（命令：diag/morph/copy/respawn/go）

### 自动接管流程（bks_auto on）
1. 捕获「玩家换载具」事件：新原型资源 X（关卡内已加载）
2. 拷贝 X 的 MECH(18448) + LEG(4528) 到玩家私有槽（dummy，默认 idx 9990）
3. 调 Copy + Respawn，让实体重建于 dummy
4. 之后 mod 只改 dummy；敌人引用原型 X 不变

### 隔离边界（必须告知）
- 目前是浅拷贝：dummy 的子资源指针（upper/lower/武器/配方等）仍与原型共享；改顶层字段安全，改子资源会波及敌人。
- 需要完全隔离则要做深拷贝：为每个被引用子资源也预留私有槽。

### 待定：事件捕获方式（按优先级）
A. 内联 hook 写入 mech+0x258 的指令或「玩家上车/重生」函数（精确、零轮询）
B. hook Respawn 0x1401892C0，过滤 rcx==[base+0xB64838] 玩家 ctrl；触发后重跑 dummy 流程
C. 每帧 tick hook（需先定位主循环更新函数），每帧只读 mech+0x258 做变化检测
- 轮询线程不可行：引擎调用必须主线程，线程无法安全触达主线程执行点。

## 2026-11-23 自动接管已实测通过（bkswap3.dll）

### 事件捕获方式（最终采用 C 的变体）
- **hook 点：SDL2 延迟导入槽 `exe+0x49D710`**（thunk `0x140316F26: jmp qword ptr [rip+0x1867E4]`，槽内运行时为 SDL2.dll 内真实地址）。
  每帧开头（`App::frame` 的 `SDL_PumpEvents`）在主线程回调一次；只做一次 `mech+0x258` 指针比较，不遍历世界、无轮询线程。
- 主线程校验：`g_main_tid = GetCurrentThreadId()`（DllMain 时记录），非主线程直接跳过 tick。

### ★ 关键发现：重生后玩家会挂到「原型」上（隔离问题的实证）
- `go volta` 之后 `mech+0x258 = 0x20C12B0F680`，正是 Volta 原型资源地址（不是 dummy 槽）。
- 即 Respawn 重建时引擎按载具数据里的资产引用解析回原型 → 玩家与敌人共享同一份数据。
- 因此自动接管必须在**引擎重生完成后的下一帧**把 `mech+0x258` 指回 dummy；首帧拦截做不到。

### 实测日志（同一次会话）
```
18:20:48 auto: ON
18:20:48 auto: unit change 0 -> 0x20C26A0B560 (Cinderblock 原型)
18:20:48 auto: dummy <- src ... ; mech+0x258 -> dummy 0x20C21CB70A0 (swap #1)
18:21:27 auto: unit change dummy -> 0x20C12B0F680 (Volta 原型)
18:21:27 auto: dummy <- src ... ; mech+0x258 -> dummy 0x20C21CB70A0 (swap #2)
```
玩家在游戏内**实际换乘红甲（Volta）**被自动捕获，无需任何控制台操作。

### 隔离性验证（内存级）
- `dummy` 与 Volta 原型逐字节比对 18448B：**只有 +0xC0（LEG 指针）不同**（指向 dummy 自己的 LEG），其余完全一致 → dummy 是原型的独立副本。
- 把 dummy LEG `+0x101C max_forward_speed` 从 2.5 改为 10.0：dummy=10.0，**原型仍 2.5** → 修改不会泄漏到原型/敌人。

### 产物 / 用法
- `mods/native/bkswap/bkswap.c`、`bkswap.h`；编译输出 `C:\bk\bkswap3.dll`。
- 导出：`bks_auto_enable/disable/state`、`bks_swap`、`bks_player_mech/unit`、`bks_dummy_unit`、`bks_asset_addr`、`bks_last_error`、`bks_version`、`luaopen_bkswap`。
- 控制台：`lua local f,e=package.loadlib("C:/bk/bkswap3.dll","luaopen_bkswap"); if f then f() print("OK") else print(e) end`
- 命令文件增加：`auto on` / `auto off` / `auto`（状态）。
- 已知约束：每次检测到换载具，dummy 会被新原型整块覆盖 → **mod 必须在 swap 后重新施加自己的修改**（当前需自行轮询 `bks_player_unit()`，后续可加 swap 回调）。

## 2026-11-23 玩家背包（Inventory）结构与物品定位

### 静态：Lua 方法表（.rdata @ 0x1403D28A0）
| 方法 | 函数 | 说明 |
|---|---|---|
| AddInventory | 0x1401A96F0 | 往 `[mech+0x238]+0x250` 容器插入 {item, 1, count} |
| TakeInventory | 0x1401A97E0 | 同类 |
| IsInInventory | 0x1401A98D0 | 先查 `[mech+0x238]+0x250`，再查 `mech+0xB78` / `mech+0xB60..0xB68`（0x58 stride） |
| GetInventory | 0x14003B850 | ★ **空实现（xor eax,eax; ret）** → Lua 读不到背包 |
| SetEntryPredicate | 0x1401A9B50 | — |

### 运行时布局（实测，本局）
- 玩家 mech 重新解析（复刻 0x140024C80 的 vector-of-vector 查表）：
  ctrl=`[exe+0xB64838]` → game=`[ctrl+0x40]` → state=game+0x1C468 → container=`[state]`、key=`[state+0x30]`；
  container 是「外层 12 组 × 0x18B，内层 0x10B {u32 id, u32 pad, Mech*}]」，key=[0,30,0] → **mech=0x20B80F7BDB8**。
- 背包容器：`sub=[mech+0x238]`，`sub+0x250` = vector，begin=0x20CDC620910，17 个 slot（元素 0x18）。
- **本次物品（pkp_comp_actuator_small，pack idx 3415）在 slot[9]**：
  slot[9] = {begin=0x20CDB74E650, end=0x20CDB74E668}，元素 = {item资源 0x20C1D8D3A00, 0x20C1D8D3A01, qty=1}。
- 物品资源本身 arch=61 / 768B，内含 `pkp_comp_actuator_small.name` / `.description` 两个本地化键。

### 工具
- `C:\bk\resolve_player.py`（纯读取复刻查表，输出 mech 与背包 slots）
- `C:\bk\probe_inv.py` / `read_inv.py` / `dump_region.py` / `scan_ptr.py` / `analyze_hits.py`

## 2026-11-23 背包条件速度加成（已完成并实测）

- 成品：`mods/native/bkswap/bin/bkswap7.dll`（源码同目录），构建脚本 `C:\bk\build_bkswap.bat`。
- 行为：每 tick 检查背包（`mech+0x238` → `+0x250` 容器，元素 `{begin,end,cap}`，在 `[begin,end)` 内按 0x18 找 item），
  命中则把 dummy LEG 的 3 向最大速度 + 3 向加速度改为「浮动基准 × mult」，移除物品立即还原。
- 实测（19:00:18 / 19:00:22）：
  ```
  speed: APPLY x2.00 (leg=0x20C21CBB8E0 base fwd=2.500)
  speed: restore x2.00 (leg=... base fwd=2.500)
  ```
- 性能：`tick: avg_us≈200`，tick 频率约 120/s（SDL_PumpEvents 会被 SDL_PollEvent 重复触发）。

### 踩坑（重要）
1. 背包是**两层**：容器元素 `{begin,end,cap}`，`begin` 直接指向条目数组，**不要**再对 begin 解引用取 vector 头。
2. `mem_ok(p, 0)` 必须返回失败：空 slot 的值是 `0xFFFFFFFFFFFFFFFF`，长度 0 会让循环不执行而误判可读，
   随后 `[0xFFFF...]` 读取 → 每 tick 访问违例 + 日志刷屏 → 严重卡顿。
3. 需要 `e2 > b2` 而不是 `>=`。
4. `0x140024C80` 的查表可纯读取复刻：container 外层 12 组×0x18（`{begin,end}`），内层 0x10（`{u32 id, pad, Mech*}`），
   key=[0,30,0] → 玩家 mech。
