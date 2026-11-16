// proxy_sdl2.c — v39 safe: 延迟调用 + 全指针防护
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#include <stdint.h>

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
typedef uintptr_t(*pa_find_fake_t)(void);
static pa_find_t       g_pa_find       = NULL;
static pa_find_fake_t  g_pa_find_fake  = NULL;

// ---------- 限频 ----------
#define PA_COPY_INTERVAL_MS 16
static DWORD g_last_copy_tick = 0;
static int   g_copy_count     = 0;
static DWORD g_init_tick      = 0;  // SDL_Init 时间

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

    // 2. 加载 pa_probe (可选, 失败不影响转发)
    char pa_path[MAX_PATH];
    strcpy(pa_path, path);
    strcat(pa_path, "pa_probe.dll");
    g_pa_probe = LoadLibraryA(pa_path);
    if (g_pa_probe) {
        g_pa_find       = (pa_find_t)       GetProcAddress(g_pa_probe, "pa_find_mech_by_type");
        g_pa_find_fake  = (pa_find_fake_t)  GetProcAddress(g_pa_probe, "pa_find_fake");
        logf_("pa_probe OK find=%p fake=%p", g_pa_find, g_pa_find_fake);
    } else {
        logf_("pa_probe.dll not found (err=%lu), PA inject disabled", GetLastError());
    }

    g_init_tick = GetTickCount();
}

// ---------- 探索: 延迟 5 秒后 dump (等地图加载完) ----------
static int g_dumped = 0;

static void safe_dump64(const char* prefix, uintptr_t addr) {
    if (!addr || addr < 0x100000 || IsBadReadPtr((void*)addr, 8)) return;
    logf_("  %s @ 0x%llX (64B):", prefix, (unsigned long long)addr);
    for (int i = 0; i < 64; i += 16) {
        if (IsBadReadPtr((void*)(addr + i), 16)) break;
        uint64_t q0 = *(uint64_t*)(addr + i);
        uint64_t q1 = *(uint64_t*)(addr + i + 8);
        logf_("    +0x%02X: %016llX %016llX", i, q0, q1);
    }
}

static void dump_once_safe(void) {
    DWORD age = GetTickCount() - g_init_tick;
    if (age < 5000) return;   // 等 5 秒让地图加载
    if (g_dumped) return;
    g_dumped = 1;

    if (!g_pa_find) { logf_("dump_once: no pa_find"); return; }

    uintptr_t player = g_pa_find(6);
    if (!player) { logf_("dump_once: no player yet"); return; }

    // fake 由 Lua 创建, 可能还不存在
    uintptr_t fake = g_pa_find_fake ? g_pa_find_fake() : 0;

    logf_("=== DUMP player=0x%llX fake=0x%llX (age=%ums) ===",
          (unsigned long long)player, (unsigned long long)fake, age);

    // Player PA LUT + P1 + 8 子组件
    char *pp = (char*)player;
    uintptr_t pl = *(uintptr_t*)(pp + 0x230);
    logf_("  PLAYER +0x230 PA LUT = 0x%llX", (unsigned long long)pl);
    safe_dump64("  PA_LUT", pl);

    if (pl && !IsBadReadPtr((void*)pl, 8)) {
        uintptr_t pp1 = *(uintptr_t*)(pl + 0x30);
        logf_("  PLAYER LUT+0x30 PA_P1 = 0x%llX", (unsigned long long)pp1);
        safe_dump64("  PA_P1", pp1);

        // P1+0x18~0x50: 8 个子组件
        if (pp1 && !IsBadReadPtr((void*)pp1, 0x50)) {
            logf_("  PLAYER PA_P1 子组件:");
            for (int i = 0; i < 8; i++) {
                int off = 0x18 + i * 8;
                uintptr_t sub = *(uintptr_t*)(pp1 + off);
                logf_("    P1+0x%02X → sub[%d] = 0x%llX", off, i, (unsigned long long)sub);
                safe_dump64("      SUB", sub);
            }
        }
    }

    // Fake (如果有)
    if (fake) {
        char *fp = (char*)fake;
        uintptr_t fl = *(uintptr_t*)(fp + 0x230);
        logf_("  FAKE +0x230 PA LUT = 0x%llX", (unsigned long long)fl);
        safe_dump64("  F_PA_LUT", fl);

        if (fl && !IsBadReadPtr((void*)fl, 8)) {
            uintptr_t fp1 = *(uintptr_t*)(fl + 0x30);
            logf_("  FAKE LUT+0x30 PA_P1 = 0x%llX", (unsigned long long)fp1);
            safe_dump64("  F_PA_P1", fp1);

            if (fp1 && !IsBadReadPtr((void*)fp1, 0x50)) {
                logf_("  FAKE PA_P1 子组件:");
                for (int i = 0; i < 8; i++) {
                    int off = 0x18 + i * 8;
                    uintptr_t sub = *(uintptr_t*)(fp1 + off);
                    logf_("    P1+0x%02X → sub[%d] = 0x%llX", off, i, (unsigned long long)sub);
                    safe_dump64("      F_SUB", sub);
                }
            }
        }
    } else {
        logf_("  (fake not found yet)");
    }
}

static void inject_pa_once(void) {
    dump_once_safe();  // 只 dump, 不注入
}

// ================================================================
//  Hook 导出 (纯 C, 绝无 mangling!)
// ================================================================

__declspec(dllexport) int SDL_Init(DWORD flags) {
    do_init_once();
    if (!g_orig_Init) return -1;
    int ret = g_orig_Init(flags);
    logf_("SDL_Init flags=0x%08X ret=%d", flags, ret);
    return ret;
}

__declspec(dllexport) int SDL_PollEvent(void* event) {
    do_init_once();
    if (!g_orig_PollEvent) return 0;
    int ret = g_orig_PollEvent(event);
    inject_pa_once();
    return ret;
}

__declspec(dllexport) void SDL_Quit(void) {
    do_init_once();
    logf_("SDL_Quit");
    if (g_orig_Quit) g_orig_Quit();
}

__declspec(dllexport) void* SDL_CreateWindow(
    const char* title, int x, int y, int w, int h, DWORD flags) {
    do_init_once();
    if (!g_orig_CreateWnd) return NULL;
    void* r = g_orig_CreateWnd(title, x, y, w, h, flags);
    return r;
}

// ================================================================
//  DllMain — 零副作用
// ================================================================
BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpvReserved) {
    (void)lpvReserved;
    (void)hinstDLL;
    if (fdwReason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hinstDLL);
    }
    return TRUE;
}
