// pa_probe v7 — 完整导出, 精确拷 Player_Action 安全区

#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <stdarg.h>

#define RVA_LUA_PUSHNUMBER  0x318A10
#define RVA_LUA_PUSHNIL     0x3189F0
#define RVA_LUA_TOUSERDATA  0x319380
#define RVA_RESOLVE_MECH    0x024C80
#define RVA_SINGLETON       0xB38850
#define MGR_OFFSET          0x2788
#define LUA_STATE_STACK_OFF 0x20
#define RVA_LUAOPEN_FFI     0x3299B0
#define RVA_LUAOPEN_BIT     0x3557E0
#define RVA_LUAOPEN_OS      0x323750
#define RVA_LUAOPEN_IO      0x322C20

static uintptr_t g_base = 0;

static void logf_(const char *fmt, ...) {
    char path[MAX_PATH];
    GetModuleFileNameA(NULL, path, MAX_PATH);
    char *s = strrchr(path, '\\');
    if (s) s[1] = '\0';
    strcat(path, "pa_probe.log");
    FILE *f = fopen(path, "a");
    if (!f) return;
    va_list ap; va_start(ap, fmt); vfprintf(f, fmt, ap); va_end(ap);
    fputc('\n', f); fclose(f);
}

static void ensure_base(void) {
    if (!g_base) g_base = (uintptr_t)GetModuleHandleA(NULL);
}

typedef void *(*fn_touserdata)(void *L, int idx);
typedef void  (*fn_pushnumber)(void *L, double d);
typedef void  (*fn_pushnil)(void *L);
typedef void *(*fn_resolve)(void *mgr, void *ud);

static double lua_arg_double(void *L, int idx) {
    ensure_base();
    uintptr_t stack = *(uintptr_t *)((char *)L + LUA_STATE_STACK_OFF);
    return *(double *)(stack + (idx - 1) * 8);
}
static int lua_arg_int(void *L, int idx) { return (int)lua_arg_double(L, idx); }

static void *mech_from_lua(void *L, int idx) {
    ensure_base();
    fn_touserdata tu = (fn_touserdata)(g_base + RVA_LUA_TOUSERDATA);
    fn_resolve    rs = (fn_resolve)(g_base + RVA_RESOLVE_MECH);
    void *ud = tu(L, idx);
    if (!ud) return NULL;
    uintptr_t world = *(uintptr_t *)(g_base + RVA_SINGLETON);
    if (!world) return NULL;
    void *mgr = (void *)(world + MGR_OFFSET);
    return rs(mgr, ud);
}

// 关键: C 函数返回值是返回值个数
static int ret_number(void *L, double d) {
    ((fn_pushnumber)(g_base + RVA_LUA_PUSHNUMBER))(L, d);
    return 1;
}
static int ret_nil(void *L) {
    ((fn_pushnil)(g_base + RVA_LUA_PUSHNIL))(L);
    return 1;
}
static int ret_one(void *L) { return ret_number(L, 1.0); }

// ====================== 导出函数 ======================

// --- 基础读写 ---

__declspec(dllexport) int pa_ptr(void *L) {
    ensure_base();
    void *mech = mech_from_lua(L, 1);
    if (!mech) return ret_nil(L);
    return ret_number(L, (double)(uintptr_t)mech);
}

__declspec(dllexport) int pa_dump(void *L) {
    ensure_base();
    void *mech = mech_from_lua(L, 1);
    if (!mech) return ret_nil(L);
    unsigned char *p = (unsigned char *)mech;
    logf_("[pa] dumping 0x800 bytes @ %p", mech);
    for (int i = 0; i < 0x800; i += 16) {
        char line[200]; int n = sprintf(line, "  +%04X  ", i);
        for (int j = 0; j < 16; j++) n += sprintf(line + n, "%02X ", p[i + j]);
        line[n++] = ' '; line[n++] = ' ';
        for (int j = 0; j < 16; j++) {
            unsigned char c = p[i + j];
            line[n++] = (c >= 32 && c < 127) ? c : '.';
        }
        line[n] = 0; logf_("%s", line);
    }
    return ret_one(L);
}

// 读 f32
__declspec(dllexport) int pa_read_f32(void *L) {
    ensure_base();
    void *mech = mech_from_lua(L, 1);
    if (!mech) return ret_nil(L);
    int offset = lua_arg_int(L, 2);
    float val = *(float *)((char *)mech + offset);
    logf_("[pa] read_f32 +0x%X = %f", offset, val);
    return ret_number(L, (double)val);
}

// 写 f32
__declspec(dllexport) int pa_write_f32(void *L) {
    ensure_base();
    void *mech = mech_from_lua(L, 1);
    if (!mech) return ret_nil(L);
    int offset = lua_arg_int(L, 2);
    float val = (float)lua_arg_double(L, 3);
    *(float *)((char *)mech + offset) = val;
    logf_("[pa] write_f32 +0x%X <- %f", offset, val);
    return ret_one(L);
}

// 读 u32
__declspec(dllexport) int pa_read_u32(void *L) {
    ensure_base();
    void *mech = mech_from_lua(L, 1);
    if (!mech) return ret_nil(L);
    int offset = lua_arg_int(L, 2);
    uint32_t val = *(uint32_t *)((char *)mech + offset);
    logf_("[pa] read_u32 +0x%X = 0x%X", offset, val);
    return ret_number(L, (double)val);
}

// 写 u32
__declspec(dllexport) int pa_write_u32(void *L) {
    ensure_base();
    void *mech = mech_from_lua(L, 1);
    if (!mech) return ret_nil(L);
    int offset = lua_arg_int(L, 2);
    uint32_t val = (uint32_t)lua_arg_double(L, 3);
    *(uint32_t *)((char *)mech + offset) = val;
    logf_("[pa] write_u32 +0x%X <- 0x%X", offset, val);
    return ret_one(L);
}

// 读 qword
__declspec(dllexport) int pa_read_qword(void *L) {
    ensure_base();
    void *mech = mech_from_lua(L, 1);
    if (!mech) return ret_nil(L);
    int offset = lua_arg_int(L, 2);
    uintptr_t val = *(uintptr_t *)((char *)mech + offset);
    logf_("[pa] read_qword +0x%X = 0x%llX", offset, (unsigned long long)val);
    return ret_number(L, (double)val);
}

// 写 qword
__declspec(dllexport) int pa_write_qword(void *L) {
    ensure_base();
    void *mech = mech_from_lua(L, 1);
    if (!mech) return ret_nil(L);
    int offset = lua_arg_int(L, 2);
    uintptr_t val = (uintptr_t)lua_arg_double(L, 3);
    *(uintptr_t *)((char *)mech + offset) = val;
    logf_("[pa] write_qword +0x%X <- 0x%llX", offset, (unsigned long long)val);
    return ret_one(L);
}

// peek 任意地址
__declspec(dllexport) int pa_peek(void *L) {
    ensure_base();
    uintptr_t ptr = (uintptr_t)lua_arg_double(L, 1);
    int size = lua_arg_int(L, 2);
    if (!ptr || size <= 0 || size > 256) return ret_nil(L);
    logf_("[pa] peek 0x%llX (%d bytes):", (unsigned long long)ptr, size);
    unsigned char *p = (unsigned char *)ptr;
    int show = size < 64 ? size : 64;
    for (int i = 0; i < show; i += 16) {
        char line[120]; int n = sprintf(line, "  +%03X: ", i);
        for (int j = 0; j < 16 && i + j < show; j++)
            n += sprintf(line + n, "%02X ", p[i + j]);
        line[n] = 0; logf_("%s", line);
    }
    uintptr_t vft = *(uintptr_t *)ptr;
    logf_("[pa] +0x000 qword = 0x%llX", (unsigned long long)vft);
    return ret_number(L, (double)vft);
}

// 复制 qword
__declspec(dllexport) int pa_copy_qword(void *L) {
    ensure_base();
    void *dst = mech_from_lua(L, 1);
    void *src = mech_from_lua(L, 2);
    if (!dst || !src) return ret_nil(L);
    int offset = lua_arg_int(L, 3);
    uintptr_t val = *(uintptr_t *)((char *)src + offset);
    *(uintptr_t *)((char *)dst + offset) = val;
    logf_("[pa] copy_qword +0x%X: 0x%llX -> dst", offset, (unsigned long long)val);
    return ret_one(L);
}

// copy 任意 byte 区域 (dst, src, offset, size)
__declspec(dllexport) int pa_copy_region(void *L) {
    ensure_base();
    void *dst = mech_from_lua(L, 1);
    void *src = mech_from_lua(L, 2);
    if (!dst || !src) return ret_nil(L);
    int offset = lua_arg_int(L, 3);
    int size   = lua_arg_int(L, 4);
    if (size <= 0 || size > 0x800) return ret_nil(L);
    memcpy((char *)dst + offset, (char *)src + offset, size);
    logf_("[pa] copy_region +0x%X (%d bytes)", offset, size);
    return ret_one(L);
}

// ============================================================
// pa_copy_player_action — v11: 完整 memcpy + 自指指针修正 + crash 捕获
// 全拷 fake = player, 然后:
//   1. 把所有 qword 里 [ptr >= player_start && ptr < player_end] 改成 fake 对应偏移
//   2. 用 VEH 捕获后续 crash, 写故障地址到 log
// 目标: 让 fake 真正变成第二个玩家对象
// ============================================================

static PVOID g_veh_handle = NULL;
static void *g_fake_ptr = NULL;
static void *g_player_ptr = NULL;
static SIZE_T g_region_size = 0x2000;

static LONG WINAPI veh_cb(EXCEPTION_POINTERS *ep) {
    DWORD code = ep->ExceptionRecord->ExceptionCode;
    uintptr_t ip = 0;
    uintptr_t fault = 0;
    if (ep->ContextRecord) {
#ifdef _WIN64
        ip = ep->ContextRecord->Rip;
#else
        ip = ep->ContextRecord->Eip;
#endif
    }
    if (code == EXCEPTION_ACCESS_VIOLATION && ep->ExceptionRecord->NumberParameters >= 2) {
        fault = (uintptr_t)ep->ExceptionRecord->ExceptionInformation[1];
    }
    logf_("[pa] *** CRASH CODE=0x%08X IP=0x%llX FAULT=0x%llX",
          code, (unsigned long long)ip, (unsigned long long)fault);
    logf_("[pa]   fake=0x%llX player=0x%llX region=0x%llX",
          (unsigned long long)g_fake_ptr,
          (unsigned long long)g_player_ptr,
          (unsigned long long)g_region_size);
    return EXCEPTION_CONTINUE_SEARCH;
}

__declspec(dllexport) int pa_copy_player_action(void *L) {
    ensure_base();
    logf_("[pa] === pa_copy_player_action v11: FULL copy + self-pointer fix ===");

    void *fake = mech_from_lua(L, 1);   // dst
    void *player = mech_from_lua(L, 2); // src
    if (!fake || !player) { logf_("[pa] NULL"); return ret_nil(L); }

    g_fake_ptr = fake;
    g_player_ptr = player;

    // 装 VEH
    if (!g_veh_handle) {
        g_veh_handle = AddVectoredExceptionHandler(1, veh_cb);
        logf_("[pa] VEH installed: %p", g_veh_handle);
    }

    // Step 1: 完整 memcpy 2KB
    memcpy(fake, player, g_region_size);
    logf_("[pa] full 2KB memcpy done");

    // Step 2: 扫描 fake, 把所有指向 player 的指针改成 fake 对应偏移
    // 也把指向 fake 自己 (现在内容已变成 player 的) 的指针重新算一遍
    char *d = (char *)fake;
    char *p = (char *)player;
    int fix_count = 0;

    for (size_t off = 0; off < g_region_size; off += 8) {
        uintptr_t val = *(uintptr_t *)(d + off);
        if (val == 0) continue;

        // 如果 val 指向 [player, player + region_size) → 改成 fake 对应偏移
        if ((char *)val >= p && (char *)val < p + g_region_size) {
            size_t delta = (char *)val - p;
            uintptr_t new_val = (uintptr_t)(d + delta);
            logf_("[pa]   fix +0x%04X: 0x%llX -> 0x%llX (player->fake)",
                  off, (unsigned long long)val, (unsigned long long)new_val);
            *(uintptr_t *)(d + off) = new_val;
            fix_count++;
        }
        // 如果 val 指向 [fake, fake + region_size) → 不用改, 已经是 fake 自己的
        // 但如果是指向 fake 但之前内容被 memcpy 成了 player 的, 那指针值也是 player 的
        // 上面已经处理了
    }
    logf_("[pa] self-pointer fix: %d entries", fix_count);

    // Step 3: 记录关键区域
    logf_("[pa] fake type (+0x00) = 0x%llX", (unsigned long long)*(uintptr_t *)(d + 0));
    logf_("[pa] fake +0x230 (lookup) = 0x%llX", (unsigned long long)*(uintptr_t *)(d + 0x230));
    logf_("[pa] fake +0x720 (AI)    = 0x%llX", (unsigned long long)*(uintptr_t *)(d + 0x720));

    return ret_one(L);
}

// 恢复函数: 把 Mech 恢复到全零安全状态
__declspec(dllexport) int pa_zero_region(void *L) {
    ensure_base();
    void *mech = mech_from_lua(L, 1);
    if (!mech) return ret_nil(L);
    int offset = lua_arg_int(L, 2);
    int size   = lua_arg_int(L, 3);
    if (size <= 0 || size > 0x800) return ret_nil(L);
    memset((char *)mech + offset, 0, size);
    logf_("[pa] zero_region +0x%X (%d bytes)", offset, size);
    return ret_one(L);
}

// ============================================================
// pa_ffi — 直接调用 exe 内部的 luaopen_ffi, 把 ffi 表返回给 Lua
// 用法: local ffi = package.loadlib("pa_probe.dll","pa_ffi")()
// ============================================================
typedef int (*fn_luaopen)(void *L);

static int open_lib(void *L, uintptr_t rva, const char *tag) {
    fn_luaopen fn = (fn_luaopen)(g_base + rva);
    int n = fn(L);
    logf_("[pa] luaopen_%s -> %d", tag, n);
    if (n <= 0) return 0;
    return n;
}

__declspec(dllexport) int pa_ffi(void *L) {
    ensure_base();
    logf_("[pa] === pa_ffi ===");
    int n = open_lib(L, RVA_LUAOPEN_FFI, "ffi");
    if (n == 0) { logf_("[pa] ffi FAILED"); return ret_nil(L); }
    return n;   // 栈顶就是 ffi 模块表
}

__declspec(dllexport) int pa_bit(void *L) {
    ensure_base();
    int n = open_lib(L, RVA_LUAOPEN_BIT, "bit");
    if (n == 0) return ret_nil(L);
    return n;
}

__declspec(dllexport) int pa_os(void *L) {
    ensure_base();
    int n = open_lib(L, RVA_LUAOPEN_OS, "os");
    if (n == 0) return ret_nil(L);
    return n;
}

__declspec(dllexport) int pa_io(void *L) {
    ensure_base();
    int n = open_lib(L, RVA_LUAOPEN_IO, "io");
    if (n == 0) return ret_nil(L);
    return n;
}

// 返回 exe 基址, 方便 Lua 侧算绝对地址
__declspec(dllexport) int pa_base(void *L) {
    ensure_base();
    return ret_number(L, (double)g_base);
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID p) {
    (void)p;
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(h);
        ensure_base();
        logf_("=== pa_probe v7 ATTACH base=0x%llX ===", (unsigned long long)g_base);
    }
    return TRUE;
}
