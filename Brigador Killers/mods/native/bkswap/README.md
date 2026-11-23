# bkswap — Brigador Killers 运行时换载具 / 背包条件速度加成

纯 native DLL，通过游戏内控制台的 Lua `package.loadlib` 加载。不修改 exe、不改 assets.pack，关闭游戏即完全还原。

---

## 一、组件清单

**运行时只需要 1 个文件**：`bkswap7.dll`。

| 组件 | 是否必需 | 说明 |
|---|---|---|
| `bin/bkswap7.dll` | ✅ 必需 | 唯一运行时组件（约 177 KB） |
| `bkswap.c` / `bkswap.h` | 可选 | 源码，改功能时用 |
| `C:\bk\build_bkswap.bat` | 可选 | 一键重建，输出直接覆盖 `bin/bkswap7.dll` |
| `%TEMP%\bk_swap.txt` | 运行期 | 命令文件，加载 DLL 时读取 |
| `%TEMP%\bk_swap.log` | 运行期 | 日志，追加写入 |
| 游戏内控制台（`lua` / `luaload`） | ✅ 前置 | 本机已具备（vehicle_spawner 等 mod 同款入口） |

依赖：Windows x64、游戏版本与 `bkswap7.dll` 编译时一致（当前 build 已验证）。不需要装 Python、VC 运行库（DLL 为 /MT 之外的 CRT 已随游戏加载；重建才需要 VS）。

---

## 二、安装（3 步）

### 1. 放 DLL

任选固定目录，建议用项目内备份路径（也可用 `C:\bk\`）：

```
c:\Users\Scrooge\Documents\GitHub\TheArtifact\Brigador Killers\mods\native\bkswap\bin\bkswap7.dll
```

> DLL 可以放在磁盘任意位置，路径**不要有中文/空格风险**，Lua 里用正斜杠 `/`。

### 2. 写命令文件

新建（或覆盖）`%TEMP%\bk_swap.txt`，一行一条命令，例如：

```
diag
auto on
item assets/data/pickups/kit/pkp_comp_actuator_small.json 2
```

含义：打印诊断 + 开启自动接管 + 背包里有该物品时玩家载具速度 ×2。
不写这个文件也能加载，默认只跑一次 `diag`。

### 3. 进关卡后执行

在游戏控制台粘贴（路径换成你的实际路径）：

```
lua local f,e=package.loadlib("C:/Users/Scrooge/Documents/GitHub/TheArtifact/Brigador Killers/mods/native/bkswap/bin/bkswap7.dll","luaopen_bkswap"); if f then f() print("OK") else print(e) end
```

看到控制台打印 `OK` 即加载成功。真正的执行结果看 `%TEMP%\bk_swap.log`（控制台只会显示 Lua 的返回值，不显示 DLL 日志）。

---

## 三、验证

日志里应出现：

```
== luaopen_bkswap ==
auto: unit change ... -> dummy ... (swap #1)
speed: APPLY x2.00 (leg=... base fwd=2.500)
tick: n=600 avg_us=200 speed_on=1 applied=1 has=1
```

- `swap #N`：第 N 次自动接管（每次换载具 +1）
- `speed: APPLY` / `speed: restore`：加成生效 / 物品移除后还原
- `tick: avg_us`：每帧开销（正常 < 300 微秒）

---

## 四、命令参考（写进 `bk_swap.txt` 后重新加载 DLL 生效）

| 命令 | 作用 |
|---|---|
| `diag` | 打印玩家 mech / unit / dummy / 当前状态 |
| `morph <资源路径>` | 只把目标载具数据拷进 dummy 槽（不重生） |
| `copy` | 调引擎 Copy（把 mech 当前数据序列化到 blob） |
| `respawn` | 调引擎 Respawn（按 blob 重建载具） |
| `go <资源路径>` | morph + copy + respawn，一步换车（手动模式） |
| `auto on` / `auto off` | 自动接管开关：玩家上车瞬间自动拷贝到 dummy 并改指 |
| `auto` | 打印自动接管状态 |
| `item <资源路径> [倍率]` | 背包条件速度加成（默认 ×2） |
| `item off` | 关闭加成并还原 |
| `item` | 打印加成状态（0 关 / 1 开但未生效 / 2 生效中） |

> 重新加载同一 DLL 会再次执行 `luaopen_bkswap` → 重新读命令文件，可在不重启游戏的情况下改配置（例如写 `item off` 再执行一次加载命令）。

---

## 五、C 接口（给别的 DLL / mod 用）

全部导出函数必须**在主线程**调用（游戏主线程；hooks 内部已保证）。

```c
int          bks_auto_enable(void);
int          bks_auto_disable(void);
int          bks_auto_state(void);        /* 0/1 */
void        *bks_player_unit(void);       /* 玩家当前 unit（恒为 dummy） */
void        *bks_player_mech(void);
void        *bks_dummy_unit(void);        /* dummy 槽地址：mod 改这里，不碰原型 */
int          bks_swap(const char *asset); /* 手动热切换，成功 1 */
void        *bks_asset_addr(const char *asset);
int          bks_item_speed_mod(const char *item_asset, float mult);
int          bks_item_speed_mod_off(void);
int          bks_item_speed_mod_state(void);  /* 0 关 / 1 开未生效 / 2 生效中 */
const char  *bks_last_error(void);
const char  *bks_version(void);
```

头文件：`mods/native/bkswap/bkswap.h`。

---

## 六、卸载 / 还原

| 目的 | 做法 |
|---|---|
| 关闭速度加成 | `bk_swap.txt` 写 `item off`，重新执行加载命令 |
| 关闭自动接管 | 写 `auto off`，重新加载（同时摘掉 hook） |
| 完全还原 | 关游戏（DLL 不落盘任何修改，内存改动随进程消失） |
| 卸掉 hook 但保留 DLL | `auto off` + `item off` 后重新加载；两者都关时 hook 自动摘除 |

---

## 七、已知限制

1. **dummy 每次换车被整块覆盖**：mod 对 dummy 的修改要在 swap 之后重新施加（速度加成已内置自动重施）。
2. **浅拷贝**：MECH/LEG 是整块内存拷贝，内部子资源指针仍指向原型共享对象；改子资源会污染原型。隔离的是"载具数据本体"。
3. **只对已加载资源有效**：关卡外资源 `resarr=0`，`morph/go` 会失败（日志 `NOT LOADED`）。
4. 自动接管检测的是 `mech+0x258`（玩家 unit 指针）变化；同一载具内不会触发。
5. 关闭自动接管后，speed 加成仍工作（各自独立开关），但速度加成需要在 `auto on` 前提下才会随换车重施。

---

## 八、排障

| 日志关键字 | 原因 / 处理 |
|---|---|
| `no bk_swap.txt, running diag` | 命令文件不存在，按第二节第 2 步创建 |
| `target not in pack` / `NOT LOADED` | 资源路径不在包内 / 该资源当前关卡未加载 |
| `item not loaded / not found` | 物品路径不对，或该物品资源未被加载 |
| `pack: ... bad` | 游戏进程与 DLL 版本不匹配（重新编译） |
| `tick: avg_us` 持续 > 2000 | 异常，记录后关掉 hook（`auto off` + `item off`） |
| 大量 `EXC code=c0000005` | 旧版本 bug（`mem_ok(p,0)`），升级到 bkswap7 |

日志：`%TEMP%\bk_swap.log`（可用 `notepad $env:TEMP\bk_swap.log` 查看）。
