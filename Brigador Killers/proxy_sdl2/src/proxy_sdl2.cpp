// proxy_sdl2.cpp — SDL2 Proxy DLL skeleton
// 目标：
//   1. 加载原始 SDL2.dll（SDL2_orig.dll）
//   2. 转发所有 812 个导出
//   3. DllMain 里验证注入成功
//   4. 后续：hook SDL_PollEvent 做输入蹦床 + 找 lua_State + 注册 PlayerAction

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdio>

// ---------- 原始 DLL 句柄 ----------
static HMODULE g_orig_sdl2 = nullptr;

// ---------- 蹦床：原始函数指针（暂时只存最关键几个） ----------
// 后续会扩展到所有我们要 hook 的 SDL 函数
typedef int(WINAPI* SDL_PollEvent_t)(void* event);
typedef int(WINAPI* SDL_Init_t)(Uint32 flags);
typedef void(WINAPI* SDL_Quit_t)();
typedef SDL_Window*(WINAPI* SDL_CreateWindow_t)(const char*, int, int, int, int, Uint32);
typedef void(WINAPI* SDL_DestroyWindow_t)(SDL_Window*);

static SDL_PollEvent_t       g_orig_PollEvent = nullptr;
static SDL_Init_t            g_orig_Init      = nullptr;
static SDL_Quit_t            g_orig_Quit      = nullptr;
static SDL_CreateWindow_t    g_orig_CreateWnd = nullptr;
static SDL_DestroyWindow_t   g_orig_DestroyWnd = nullptr;

// ---------- 调试日志 ----------
static void log_msg(const char* msg) {
    // 写到 exe 旁边的 proxy_sdl2.log
    char path[MAX_PATH];
    GetModuleFileNameA(nullptr, path, MAX_PATH);
    char* slash = strrchr(path, '\\');
    if (slash) slash[1] = '\0';
    strcat(path, "proxy_sdl2.log");

    FILE* f = fopen(path, "a");
    if (f) {
        SYSTEMTIME st; GetLocalTime(&st);
        fprintf(f, "[%02d:%02d:%02d] %s\n", st.wHour, st.wMinute, st.wSecond, msg);
        fclose(f);
    }
    OutputDebugStringA(msg);
}

// ---------- Load original DLL ----------
static bool load_original() {
    char path[MAX_PATH];
    GetModuleFileNameA(nullptr, path, MAX_PATH);
    char* slash = strrchr(path, '\\');
    if (slash) slash[1] = '\0';
    strcat(path, "SDL2_orig.dll");

    g_orig_sdl2 = LoadLibraryA(path);
    if (!g_orig_sdl2) {
        char buf[256];
        sprintf(buf, "LoadLibraryA(%s) 失败, error=%lu", path, GetLastError());
        log_msg(buf);
        return false;
    }
    log_msg("SDL2_orig.dll 加载成功");

    // 存关键蹦床
    #define LOAD_ORIG(name) \
        g_orig_##name = (name##_t)GetProcAddress(g_orig_sdl2, #name); \
        if (!g_orig_##name) log_msg("警告: GetProcAddress " #name " 失败")

    LOAD_ORIG(PollEvent);
    LOAD_ORIG(Init);
    LOAD_ORIG(Quit);
    LOAD_ORIG(CreateWnd);
    LOAD_ORIG(DestroyWnd);
    return true;
}

// ---------- Hook: SDL_Init ----------
// 在引擎调用 SDL_Init 之后，我们知道游戏启动了
static SDL_Init_t g_real_SDL_Init = nullptr;
extern "C" __declspec(dllexport) int SDL_Init(Uint32 flags) {
    if (!g_real_SDL_Init) {
        g_real_SDL_Init = (SDL_Init_t)GetProcAddress(g_orig_sdl2, "SDL_Init");
    }
    int ret = g_real_SDL_Init(flags);

    if (ret == 0) {
        log_msg("SDL_Init 成功 — 游戏启动中");
        // TODO: 在这里尝试找 lua_State + 注册 PlayerAction
    }
    return ret;
}

// ---------- Hook: SDL_PollEvent ----------
// 输入蹦床入口。所有 SDL 事件会先经过这里
static SDL_PollEvent_t g_real_SDL_PollEvent = nullptr;
extern "C" __declspec(dllexport) int SDL_PollEvent(void* event) {
    if (!g_real_SDL_PollEvent) {
        g_real_SDL_PollEvent = (SDL_PollEvent_t)GetProcAddress(g_orig_sdl2, "SDL_PollEvent");
    }
    int ret = g_real_SDL_PollEvent(event);

    if (ret > 0 && event) {
        // TODO: 解析 SDL_Event，拦截我们关心的按键做自定义 Lua 调用
        // 例如 VK_F6 → 让 fake player 开枪
    }
    return ret;
}

// ---------- DllMain ----------
BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpvReserved) {
    switch (fdwReason) {
    case DLL_PROCESS_ATTACH: {
        DisableThreadLibraryCalls(hinstDLL);
        log_msg("=== proxy_sdl2 DLL_PROCESS_ATTACH ===");

        // 原始 DLL 用延迟加载？还是立即加载？
        // 延迟加载的话，引擎调用第一个 SDL 函数时才真正加载
        // 但我们的 .def 转发已经隐式加载了 SDL2_orig.dll（因为 LINK /DEF 会自动做转发）
        // 所以这里只要存关键蹦床就好
        load_original();
        break;
    }
    case DLL_PROCESS_DETACH:
        log_msg("=== proxy_sdl2 DLL_PROCESS_DETACH ===");
        if (g_orig_sdl2) {
            FreeLibrary(g_orig_sdl2);
        }
        break;
    }
    return TRUE;
}
