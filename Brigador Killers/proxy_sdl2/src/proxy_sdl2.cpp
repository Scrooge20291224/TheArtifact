// proxy_sdl2.cpp — v4: DllMain 零副作用, 所有加载延迟到 SDL_Init 里
// 修: DllMain 调 LoadLibraryA 持 loader lock 会 crash

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>

// ---------- 原始 SDL2 ----------
static HMODULE g_orig_sdl2 = NULL;
typedef int   (WINAPI* SDL_Init_t)(DWORD flags);
typedef int   (WINAPI* SDL_PollEvent_t)(void* event);
typedef void  (WINAPI* SDL_Quit_t)(void);
typedef void* (WINAPI* SDL_CreateWindow_t)(const char*, int, int, int, int, DWORD);

static SDL_Init_t          g_orig_Init        = NULL;
static SDL_PollEvent_t     g_orig_PollEvent   = NULL;
static SDL_Quit_t          g_orig_Quit        = NULL;
static SDL_CreateWindow_t  g_orig_CreateWnd   = NULL;

// ---------- pa_probe ----------
static HMODULE g_pa_probe = NULL;
typedef uintptr_t(*pa_find_t)(int type);
typedef int      (*pa_memcpy_t)(uintptr_t dst, uintptr_t src);
static pa_find_t    g_pa_find    = NULL;
static pa_memcpy_t  g_pa_memcpy  = NULL;

// ---------- 限频 ----------
#define PA_COPY_INTERVAL_MS 16
static DWORD g_last_copy_tick = 0;
static int   g_copy_count     = 0;

// ---------- 日志 ----------
static void logf_(const char* fmt, ...) {
    char path[MAX_PATH];
    GetModuleFileNameA(NULL, path, MAX_PATH);
    char* slash = strrchr(path, '\\');
    if (slash) slash[1] = '\0';
    strcat(path, "proxy_sdl2.log");
    FILE* f = fopen(path, "a"); if (!f) return;
    SYSTEMTIME st; GetLocalTime(&st);
    fprintf(f, "[%02d:%02d:%02d] ", st.wHour, st.wMinute, st.wSecond);
    va_list ap; va_start(ap, fmt); vfprintf(f, fmt, ap); va_end(ap);
    fputc('\n', f); fclose(f);
}

// ---------- 一次性加载所有依赖 ----------
// 在 DllMain 外调用 (例如从第一个 SDL_Init hook)
static int g_initialized = 0;
static void do_init_once(void) {
    if (g_initialized) return;
    g_initialized = 1;

    char path[MAX_PATH];
    GetModuleFileNameA(NULL, path, MAX_PATH);
    char* slash = strrchr(path, '\\');
    if (slash) slash[1] = '\0';

    // 1. 加载原始 SDL2
    char orig_path[MAX_PATH];
    strcpy(orig_path, path);
    strcat(orig_path, "SDL2_orig.dll");
    g_orig_sdl2 = LoadLibraryA(orig_path);
    if (!g_orig_sdl2) {
        logf_("FAIL: LoadLibrary SDL2_orig.dll err=%lu", GetLastError());
        return;
    }
    logf_("SDL2_orig.dll OK");

    g_orig_Init       = (SDL_Init_t)         GetProcAddress(g_orig_sdl2, "SDL_Init");
    g_orig_PollEvent  = (SDL_PollEvent_t)    GetProcAddress(g_orig_sdl2, "SDL_PollEvent");
    g_orig_Quit       = (SDL_Quit_t)         GetProcAddress(g_orig_sdl2, "SDL_Quit");
    g_orig_CreateWnd  = (SDL_CreateWindow_t) GetProcAddress(g_orig_sdl2, "SDL_CreateWindow");

    // 2. 加载 pa_probe
    char pa_path[MAX_PATH];
    strcpy(pa_path, path);
    strcat(pa_path, "pa_probe.dll");
    g_pa_probe = LoadLibraryA(pa_path);
    if (g_pa_probe) {
        g_pa_find   = (pa_find_t)   GetProcAddress(g_pa_probe, "pa_find_mech_by_type");
        g_pa_memcpy = (pa_memcpy_t) GetProcAddress(g_pa_probe, "pa_memcpy_pa");
        logf_("pa_probe OK find=%p memcpy=%p", g_pa_find, g_pa_memcpy);
    } else {
        logf_("pa_probe.dll not found (err=%lu), PA inject disabled", GetLastError());
    }
}

// ---------- PA 注入 ----------
static void inject_pa_once(void) {
    if (!g_pa_find || !g_pa_memcpy) return;
    DWORD now = GetTickCount();
    if (now - g_last_copy_tick < PA_COPY_INTERVAL_MS) return;
    g_last_copy_tick = now;

    uintptr_t player = g_pa_find(6);
    if (!player) return;
    uintptr_t fake = g_pa_find(0);
    if (!fake) return;

    int bytes = g_pa_memcpy(fake, player);
    g_copy_count++;
    if (g_copy_count % 600 == 0) {
        logf_("PA inject OK player=0x%llX fake=0x%llX bytes=%d total=%d",
              (unsigned long long)player, (unsigned long long)fake, bytes, g_copy_count);
    }
}

// ================================================================
//  Hook 导出 — extern "C" 防止 name mangling
// ================================================================

extern "C" __declspec(dllexport) int SDL_Init(DWORD flags) {
    do_init_once();
    if (!g_orig_Init) return -1;
    int ret = g_orig_Init(flags);
    logf_("SDL_Init flags=0x%08X ret=%d", flags, ret);
    return ret;
}

extern "C" __declspec(dllexport) int SDL_PollEvent(void* event) {
    do_init_once();
    if (!g_orig_PollEvent) return 0;
    int ret = g_orig_PollEvent(event);
    inject_pa_once();
    return ret;
}

extern "C" __declspec(dllexport) void SDL_Quit(void) {
    do_init_once();
    logf_("SDL_Quit (total PA injects=%d)", g_copy_count);
    if (g_orig_Quit) g_orig_Quit();
}

extern "C" __declspec(dllexport) void* SDL_CreateWindow(
    const char* title, int x, int y, int w, int h, DWORD flags) {
    do_init_once();
    if (!g_orig_CreateWnd) return NULL;
    void* r = g_orig_CreateWnd(title, x, y, w, h, flags);
    logf_("SDL_CreateWindow '%s' ret=%p", title, r);
    return r;
}

// ================================================================
//  DllMain — 零副作用!!!
// ================================================================
BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpvReserved) {
    (void)lpvReserved;
    (void)hinstDLL;
    if (fdwReason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hinstDLL);
        // 绝不在这里调 LoadLibrary / GetProcAddress / 任何可能触发 loader lock 的事!
    }
    return TRUE;
}
