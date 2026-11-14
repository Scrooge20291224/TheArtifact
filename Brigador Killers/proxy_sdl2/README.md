# proxy_sdl2 — SDL2 Proxy DLL for Brigador Killers

## 这是什么

一个 Windows Proxy DLL，替换游戏目录下的 `SDL2.dll`，自动转发所有 812 个 SDL2 导出到 `SDL2_orig.dll`，同时在加载时 hook 关键路径做 mod 扩展。

参考 Half-Life 时代的 MetaMod.dll 架构。

## 目标路线图

```
阶段 1: 编译 skeleton，验证注入成功 ✅（骨架已写）
  ↓ 等待用户装 C++ 工具集编译
阶段 2: Hook SDL_Init / SDL_PollEvent 做蹦床 ✅（代码已写）
  ↓ 
阶段 3: Hook 引擎内部 lua_State 注册点
  ↓ （需要 IDA 反编译定位特征码）
阶段 4: 注册 PlayerAction.SetGun / SetSpeed 到 Lua 层
  ↓
阶段 5: Lua mod 直接调 PlayerAction.SetGun(true) 让 fake player 开枪
```

## 当前问题

**Visual Studio 18 Community 只装了 IDE + MSBuild，没装 C++ 编译器（cl.exe）。**

需要装 Visual Studio Installer → Modify → 勾选 **"Desktop development with C++"** 工作负载，至少勾：
- MSVC v143 - VS 2022 C++ x64/x86 生成工具
- Windows 10 SDK（或 11）
- C++ CMake tools for Windows

## 编译步骤（装好后）

### 方式 A：直接用 cl.exe + 链接器（最简单）

打开 **x64 Native Tools Command Prompt for VS 2025**，跑：

```cmd
cd proxy_sdl2\src
cl /LD /Fe:SDL2.dll proxy_sdl2.cpp /link /DEF:proxy.def delayimp.lib
```

### 方式 B：用 CMake

```cmd
cd proxy_sdl2
cmake -B build -G "Visual Studio 18 2025" -A x64
cmake --build build --config Release
```

## 部署

```cmd
cd "C:\Program Files (x86)\Steam\steamapps\common\Brigador Killers"
ren SDL2.dll SDL2_orig.dll
copy proxy_sdl2\build\Release\SDL2.dll .
```

启动游戏，检查旁边生成的 `proxy_sdl2.log`：
```
[09:35:12] === proxy_sdl2 DLL_PROCESS_ATTACH ===
[09:35:12] SDL2_orig.dll 加载成功
[09:35:15] SDL_Init 成功 — 游戏启动中
```

看到这些 = Proxy DLL 跑通了。

## 下一阶段：碰 Lua VM

游戏 LuaJIT **完全静态链接**进 exe，无任何导出。要在 Lua 层注册 PlayerAction 函数：

### 方法 1：扫描 lua_State 特征码

LuaJIT 的 `global_State` 结构体前 6 字节是 `"luaJIT"` — 搜索进程内存里的这串就能定位 Lua 状态。拿到指针后就能用 `luaL_register` 往里面塞新函数。

### 方法 2：hook 引擎注册 Mech 方法的地方

引擎有一个点把 `MoveTo`/`GetPlayer`/`DisableAI` 这些注册到 Lua state — 在那里装一个 trampoline，顺便注册我们自己的函数。

两种方法都需要 IDA 反编译定位——不是纯字符串扫描能搞定的。

## 文件结构

```
proxy_sdl2/
├── CMakeLists.txt          # CMake 构建脚本
├── src/
│   ├── proxy_sdl2.cpp      # Proxy 主入口 + Hook 骨架
│   └── proxy.def           # 810 个 SDL2 导出转发（自动生成）
└── tools/
    └── gen_def.py          # 从原始 SDL2.dll 生成 .def
```

## 参考

- MetaMod 架构：Proxy DLL + 蹦床跳板
- LuaJIT 静态链接特征：`global_State` 开头 `"luaJIT"` 字节串
- Brigador Killers Lua 已开启模块：`jit`, `jit.opt`, `jit.util`, `debug`, `coroutine`, `table`, `string`, `math`, `string.buffer`
- **没开启**：`ffi`, `io`, `os`, `bit`, `bit32`, `luajit`
