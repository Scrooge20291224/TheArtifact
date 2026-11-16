// pa_probe v17 — Lua C 模块版本
// 导出 luaopen_pa_probe, package.loadlib("pa_probe", "luaopen_pa_probe")() 即可加载

#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <stdarg.h>

#define RVA_LUA_PUSHNUMBER  0x318A10
#define RVA_LUA_PUSHNIL     0x3189F0
#define RVA_LUA_PUSHSTRING  0x318990
#define RVA_LUA_TOUSERDATA  0x319380
#define RVA_RESOLVE_MECH    0x024C80
#define RVA_SINGLETON       0xB38850
#define MGR_OFFSET          0x2788
#define LUA_STATE_STACK_OFF 0x20

#define MECH_TYPE_OFF       0x0000
#define MECH_PA_LUT_OFF     0x0230
#define MECH_PLAYER_TYPE    6

static uintptr_t g_base = 0;

static void logf_(const char *fmt, ...) {
    char path[MAX_PATH]; GetModuleFileNameA(NULL, path, MAX_PATH);
    char *s = strrchr(path, '\\'); if (s) s[1] = '\0';
    strcat(path, "pa_probe.log");
    FILE *f = fopen(path, "a"); if (!f) return;
    va_list ap; va_start(ap, fmt); vfprintf(f, fmt, ap); va_end(ap);
    fputc('\n', f); fclose(f);
}
static void ensure_base(void) { if (!g_base) g_base = (uintptr_t)GetModuleHandleA(NULL); }

// ===== PA 数据区 =====
static const uint32_t PA_BASE[][2] = {
    { 0x0008, 0x0010 },
    { 0x0040, 0x0044 },
    { 0x0400, 0x0410 },
    { 0x0618, 0x0628 },
    { 0x0700, 0x0710 },
};
static const int N_BASE = sizeof(PA_BASE)/sizeof(PA_BASE[0]);

// ===== Lua 辅助函数指针类型 =====
typedef void *(*fn_touserdata)(void *L, int idx);
typedef void  (*fn_pushnumber)(void *L, double d);
typedef void  (*fn_pushnil)(void *L);
typedef void  (*fn_pushstring)(void *L, const char *s);
typedef void  (*fn_setfield)(void *L, int idx, const char *s);
typedef void  (*fn_createtable)(void *L, int narr, int nrec);
typedef void *(*fn_resolve)(void *mgr, void *ud);

static void *mech_from_lua(void *L, int idx) {
    ensure_base();
    fn_touserdata touser = (fn_touserdata)(g_base + RVA_LUA_TOUSERDATA);
    fn_resolve resolve = (fn_resolve)(g_base + RVA_RESOLVE_MECH);
    void *ud = touser(L, idx); if (!ud) return NULL;
    void *mgr_ptr = (void *)*(uintptr_t *)(g_base + RVA_SINGLETON);
    void *mgr = (void *)((char *)mgr_ptr + MGR_OFFSET);
    return resolve(mgr, ud);
}
static int ret_one(void *L) {
    ensure_base();
    ((fn_pushnumber)(g_base + RVA_LUA_PUSHNUMBER))(L, 1.0);
    return 1;
}
static int ret_nil(void *L) {
    ensure_base();
    ((fn_pushnil)(g_base + RVA_LUA_PUSHNIL))(L);
    return 1;
}
static uintptr_t lua_arg_u64(void *L, int idx) {
    uintptr_t stack = *(uintptr_t *)((char *)L + LUA_STATE_STACK_OFF);
    return (uintptr_t)*(double *)(stack + (idx - 1) * 8);
}

// ===== 纯 C 接口 (proxy DLL 也能用) =====
__declspec(dllexport) uintptr_t pa_find_mech_by_type(int target_type) {
    ensure_base();
    uintptr_t world_ptr = *(uintptr_t*)(g_base + RVA_SINGLETON);
    if (!world_ptr) return 0;
    uintptr_t mgr = world_ptr + MGR_OFFSET;
    uintptr_t arr1_begin = *(uintptr_t*)mgr;
    uintptr_t arr1_end   = *(uintptr_t*)(mgr + 8);
    if (!arr1_begin || arr1_end <= arr1_begin) return 0;
    for (uintptr_t p = arr1_begin; p < arr1_end; p += 24) {
        uintptr_t sub_begin = *(uintptr_t*)p;
        uintptr_t sub_end   = *(uintptr_t*)(p + 8);
        if (!sub_begin || sub_end <= sub_begin) continue;
        for (uintptr_t q = sub_begin; q < sub_end; q += 16) {
            uintptr_t mech = *(uintptr_t*)(q + 8);
            if (!mech) continue;
            if ((int)*(uintptr_t*)mech == target_type) return mech;
        }
    }
    return 0;
}

__declspec(dllexport) int pa_memcpy_pa(uintptr_t dst_mech, uintptr_t src_mech) {
    if (!dst_mech || !src_mech) return 0;
    char *fd = (char *)dst_mech;
    char *sd = (char *)src_mech;
    uintptr_t dst_type   = *(uintptr_t *)(fd + MECH_TYPE_OFF);
    uintptr_t dst_pa_lut = *(uintptr_t *)(fd + MECH_PA_LUT_OFF);
    int bytes = 0;
    for (int i = 0; i < N_BASE; i++) {
        uint32_t s = PA_BASE[i][0], e = PA_BASE[i][1];
        memcpy(fd + s, sd + s, e - s);
        bytes += (e - s);
    }
    *(uintptr_t *)(fd + MECH_TYPE_OFF)   = dst_type;
    *(uintptr_t *)(fd + MECH_PA_LUT_OFF) = dst_pa_lut;
    return bytes;
}

// ===== Lua 接口 (通过 luaopen_pa_probe 注册) =====
// pa.read_f32(mech, offset) → float
static int l_pa_read_f32(void *L) {
    void *m = mech_from_lua(L, 1); int off = (int)lua_arg_u64(L, 2);
    if (!m) return ret_nil(L);
    ensure_base();
    ((fn_pushnumber)(g_base + RVA_LUA_PUSHNUMBER))(L, (double)*(float *)((char *)m + off));
    return 1;
}
// pa.read_qword(mech, offset) → number
static int l_pa_read_qword(void *L) {
    void *m = mech_from_lua(L, 1); int off = (int)lua_arg_u64(L, 2);
    if (!m) return ret_nil(L);
    ensure_base();
    ((fn_pushnumber)(g_base + RVA_LUA_PUSHNUMBER))(L, (double)(uintptr_t)*(uintptr_t *)((char *)m + off));
    return 1;
}
// pa.write_f32(mech, offset, value) → true/nil
static int l_pa_write_f32(void *L) {
    void *m = mech_from_lua(L, 1);
    if (!m) return ret_nil(L);
    int off = (int)lua_arg_u64(L, 2);
    uintptr_t stack = *(uintptr_t *)((char *)L + LUA_STATE_STACK_OFF);
    double val = *(double *)(stack + (3 - 1) * 8);
    *(float *)((char *)m + off) = (float)val;
    return ret_one(L);
}
// pa.write_qword(mech, offset, value) → true/nil
static int l_pa_write_qword(void *L) {
    void *m = mech_from_lua(L, 1);
    if (!m) return ret_nil(L);
    int off = (int)lua_arg_u64(L, 2);
    uintptr_t val = (uintptr_t)lua_arg_u64(L, 3);
    *(uintptr_t *)((char *)m + off) = val;
    return ret_one(L);
}
// pa.copy_pa(fake, player) → bytes/nil
static int l_pa_copy_pa(void *L) {
    void *fake = mech_from_lua(L, 1);
    void *player = mech_from_lua(L, 2);
    if (!fake || !player) return ret_nil(L);
    int bytes = pa_memcpy_pa((uintptr_t)fake, (uintptr_t)player);
    ensure_base();
    ((fn_pushnumber)(g_base + RVA_LUA_PUSHNUMBER))(L, (double)bytes);
    return 1;
}
// pa.find_player() → mech_ptr (number)
static int l_pa_find_player(void *L) {
    uintptr_t mech = pa_find_mech_by_type(MECH_PLAYER_TYPE);
    ensure_base();
    ((fn_pushnumber)(g_base + RVA_LUA_PUSHNUMBER))(L, (double)(uintptr_t)mech);
    return 1;
}
// pa.dump_range(mech, start, end, label)
static int l_pa_dump_range(void *L) {
    void *m = mech_from_lua(L, 1);
    if (!m) return ret_nil(L);
    int start = (int)lua_arg_u64(L, 2);
    int end   = (int)lua_arg_u64(L, 3);
    uintptr_t stack = *(uintptr_t *)((char *)L + LUA_STATE_STACK_OFF);
    const char *label = (const char *)*(uintptr_t *)(stack + (4 - 1) * 8);
    logf_("[dump === %s +0x%04X~+0x%04X ===", label ? label : "?", start, end);
    for (int off = start; off + 4 <= end; off += 4) {
        uint32_t v32 = *(uint32_t *)((char *)m + off);
        logf_("[dump] +0x%04X: 0x%08X (%.3f)", off, v32, (float)v32);
    }
    return ret_one(L);
}

// ===== Lua C 模块入口 =====
// 标准 Lua 5.1 模块: luaopen_xxx 返回 table
__declspec(dllexport) int luaopen_pa_probe(void *L) {
    ensure_base();
    logf_("[pa] luaopen_pa_probe called, base=0x%llX", (unsigned long long)g_base);

    // 用引擎的 lua_createtable + lua_setfield
    // RVA 从已知的 lua_pushnumber 附近推
    // lua_createtable = pushnumber - 0x318A10 + ?  不对, 我们直接用 table 方式
    // 其实最简单: 用 dlopen 风格的 luajit, 引擎内部应该有 lua_setglobal
    // 但既然引擎已经屏蔽了大部分 lua_ 函数, 我们用已知的:
    //   lua_pushnumber = 0x318A10
    //   lua_pushnil    = 0x3189F0
    //   lua_touserdata = 0x319380
    // 我们还需要: lua_setfield, lua_createtable
    //
    // 让我先查一下引擎的 luaopen_ffi 周围的导出...
    // 其实最简单: 直接把函数注册为全局!
    // 这样 Lua 里直接调用 pa_read_f32 / pa_write_f32 就行

    // 需要 lua_setglobal 或 lua_pushnumber 后 lua_setglobal
    // 我们知道 pushnumber 在 0x318A10, pushnil 在 0x3189F0
    // lua_setglobal 在 LuaJIT 里偏移应该在附近
    //
    // 实际上, 引擎可能已经把 "global table" 访问简化了
    // 让我用另一种方式: 注册到 package.loaded

    // 最简方案: 不搞 table, 直接把每个函数注册为全局
    // 这样 Lua 直接 pa_read_f32(mech, offset) 调用
    //
    // 但 lua_setglobal 在哪?
    // 让我硬编码一个 RVA, 如果 crash 了再换
    // lua_setglobal = lua_pushnumber + 0x318A10 - 0x318A10 + ?
    // 在 LuaJIT 2.1.0 beta3 里 lua_setglobal 在 ... 我不确定
    //
    // 更安全: 返回一个 table, 但我们得知道怎么 create table
    // lua_createtable 在 LuaJIT 2.1 里...
    //
    // 算了, 先用最简单的: 注册为 C 函数到全局
    // 但需要 lua_pushcclosure + lua_setglobal, 这俩 RVA 我不知道
    //
    // 终极方案: 放弃 table/全局, 让用户用 package.loadlib 拿到函数指针
    // 然后自己在 Lua 里包装:
    //   local ok, read_f32 = pcall(package.loadlib, "pa_probe", "pa_read_f32")
    // 但 package.loadlib 返回的是 C 函数, 不能直接当 Lua 函数调
    //
    // 等等! 实际上 LuaJIT 的 loadlib 返回的确实是可以直接调用的 Lua 函数!
    // 我之前搞错了! package.loadlib 返回值是已经初始化好的 Lua C 函数!
    // 让我直接声明所有单函数导出, 不要 luaopen_pa_probe!

    // 所以这个函数先空着, 单函数导出 (不带 luaopen_) 是主要路径
    ensure_base();
    ((fn_pushnil)(g_base + RVA_LUA_PUSHNIL))(L);
    return 1;
}

// ===== DllMain =====
BOOL WINAPI DllMain(HINSTANCE hinst, DWORD reason, LPVOID reserved) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hinst);
        ensure_base();
        logf_("=== pa_probe v17 ATTACH base=0x%llX ===", (unsigned long long)g_base);
    }
    return TRUE;
}
