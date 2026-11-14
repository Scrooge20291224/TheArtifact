#include <windows.h>
#include <stdio.h>
#include <string.h>

static void logline(const char *msg) {
    char path[MAX_PATH];
    GetModuleFileNameA(NULL, path, MAX_PATH);
    char *slash = strrchr(path, '\\');
    if (slash) slash[1] = '\0';
    strcat(path, "proxy_sdl2.log");
    FILE *f = fopen(path, "a");
    if (f) {
        SYSTEMTIME st;
        GetLocalTime(&st);
        fprintf(f, "[%02d:%02d:%02d] %s\n", st.wHour, st.wMinute, st.wSecond, msg);
        fclose(f);
    }
    OutputDebugStringA(msg);
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID p) {
    (void)h; (void)p;
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(h);
        logline("=== proxy_sdl2 PROCESS_ATTACH ===");
    } else if (reason == DLL_PROCESS_DETACH) {
        logline("=== proxy_sdl2 PROCESS_DETACH ===");
    }
    return TRUE;
}

__declspec(dllexport) int proxy_ping(void) {
    return 42;
}
