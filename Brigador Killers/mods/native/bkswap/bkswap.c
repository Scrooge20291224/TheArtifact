// bkswap.c - runtime vehicle-class swap for Brigador Killers (route B)
//
// Loaded from the in-game Lua console:
//   lua local f,e=package.loadlib("C:/bk/bkswap.dll","luaopen_bkswap"); if f then f() print("OK") else print(e) end
//
// Commands are read from %TEMP%\bk_swap.txt (one per line):
//   diag
//   morph <asset path>
//   copy
//   respawn
//   go    <asset path>     ; morph + copy + respawn
//
// Everything runs on the calling (Lua console / main) thread. Output: %TEMP%\bk_swap.log
//
// Verified engine facts (Brigador Killers, current build):
//   res_root  = [exe + 0xB38850]
//   pack      = [res_root + 0x2718];  resarr = [pack + 0x18]
//   ctrl      = [exe + 0xB64838];     game = [ctrl + 0x40]
//   state     = game + 0x1C468
//   container = [state]; key = [state + 0x30]; guard: key[0] must be 0
//   mech      = 0x140024C80(container, key)        ; panel "Copy player" chain
//   blob      = res_root + 0x2D28
//   copy      = 0x1401AE1C0(mech, blob)
//   respawn   = 0x1401892C0(ctrl, blob)

#include <windows.h>
#include <stdio.h>
#include <stdarg.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <share.h>

#define OFF_RES_ROOT        0x0B38850ull
#define OFF_PACK_IN_ROOT    0x2718ull
#define OFF_PLAYER_CTRL     0x0B64838ull
#define OFF_SDL_PUMP_SLOT   0x49D710ull   // delay-import IAT slot: SDL_PumpEvents
#define OFF_MECH_UNIT       0x258ull     // mech+0x258 = 当前载具 unit 资源指针
#define OFF_GAME            0x40ull
#define OFF_STATE_FROM_GAME 0x1C468ull
#define OFF_BLOB_FROM_ROOT  0x2D28ull

#define FN_STATE    0x01785F0ull   // u64 f(ctrl)  -> game + 0x1C468
#define FN_LOOKUP   0x0024C80ull   // void* f(container, key)
#define FN_COPY     0x01AE1C0ull   // char f(mech, blob)
#define FN_RESPAWN  0x01892C0ull   // void f(ctrl, blob)

#define ARCH_MECH  14
#define ARCH_LEG   11
#define MECH_SIZE  18448
#define LEG_SIZE   4528

#define PRESERVE_MECH 0x3338
#define PRESERVE_LEG  0x11A0

#define CLONE_PATH "assets/data/vics/corpse_civ_tuktuk_01.json"
#define PACK_MAGIC 0x5EA1C012u

static FILE *g_log = NULL;
static CRITICAL_SECTION g_cs;

// ---- 对外接口 / 自动接管状态 ----
static volatile LONG g_auto_on = 0;
static void *g_sdl_slot = NULL;          // exe + OFF_SDL_PUMP_SLOT
static void *g_sdl_orig = NULL;          // 原始 SDL_PumpEvents
static DWORD g_main_tid = 0;             // 主线程 id（只有主线程才跑 tick）
static uint64_t g_clone = 0;             // dummy MECH 地址
static uint64_t g_clone_leg = 0;         // dummy LEG 地址
static uint64_t g_last_unit = 0;         // 上一帧玩家 unit 指针
static uint64_t g_swap_count = 0;
static int g_speed_applied = 0;  // 速度加成当前是否已乘倍率（前向声明用）
static int g_speed_on = 0;       // 速度加成功能开关
static unsigned long long g_tick_n = 0;
static long long g_tick_us = 0;
static long long g_qpc_freq = 0;
static int g_last_has = -1;
static char g_last_err[256] = "none";

static void log_open(void)
{
    char path[MAX_PATH];
    DWORD n = GetTempPathA(MAX_PATH, path);
    if (n == 0 || n >= MAX_PATH) return;
    lstrcatA(path, "bk_swap.log");
    g_log = _fsopen(path, "a", _SH_DENYNO);
}

static void logf_(const char *fmt, ...)
{
    if (!g_log) return;
    EnterCriticalSection(&g_cs);
    SYSTEMTIME st;
    GetLocalTime(&st);
    fprintf(g_log, "[%02d:%02d:%02d.%03d] ", st.wHour, st.wMinute, st.wSecond, st.wMilliseconds);
    va_list ap;
    va_start(ap, fmt);
    vfprintf(g_log, fmt, ap);
    va_end(ap);
    fputc('\n', g_log);
    fflush(g_log);
    LeaveCriticalSection(&g_cs);
}

static int seh_filter(EXCEPTION_POINTERS *ep)
{
    logf_("  EXC code=%08lx at=%p", (unsigned long)ep->ExceptionRecord->ExceptionCode,
          ep->ExceptionRecord->ExceptionAddress);
    return EXCEPTION_EXECUTE_HANDLER;
}

static int mem_ok(uint64_t p, size_t n)
{
    uint64_t cur, end;
    if (!p || !n) return 0;
    cur = p;
    end = p + n;
    if (end < cur) return 0;
    while (cur < end) {
        MEMORY_BASIC_INFORMATION mbi;
        uint64_t rend;
        if (VirtualQuery((const void *)cur, &mbi, sizeof(mbi)) != sizeof(mbi)) return 0;
        if (mbi.State != MEM_COMMIT) return 0;
        if (mbi.Protect & (PAGE_NOACCESS | PAGE_GUARD)) return 0;
        rend = (uint64_t)mbi.BaseAddress + mbi.RegionSize;
        if (rend <= cur) return 0;
        cur = rend;
    }
    return 1;
}

static uint64_t exe_base(void)
{
    return (uint64_t)GetModuleHandleA(NULL);
}

// ---------- pack file access ----------

typedef struct {
    FILE *f;
    uint64_t base, root, pack, resarr;
    uint32_t count;
    uint64_t names, archs, offs, sizes;
    uint64_t *nametab, *offtab, *sizetab;
    uint32_t *archtab;
    uint64_t *reltab;
    uint64_t reln;
} Ctx;

static int rd_at(FILE *f, uint64_t pos, void *buf, size_t n)
{
    if (_fseeki64(f, (__int64)pos, SEEK_SET) != 0) return 0;
    return fread(buf, 1, n, f) == n;
}

static int pack_path(char *out, size_t cap)
{
    char exe[MAX_PATH];
    DWORD n = GetModuleFileNameA(NULL, exe, MAX_PATH);
    char *p;
    if (n == 0 || n >= MAX_PATH) return 0;
    p = strrchr(exe, '\\');
    if (!p) return 0;
    p[1] = 0;
    if (strlen(exe) + 12 >= cap) return 0;
    lstrcatA(exe, "assets.pack");
    lstrcpynA(out, exe, (int)cap);
    return 1;
}

static int open_pack(Ctx *c)
{
    char path[MAX_PATH];
    unsigned char hdr[0x60];
    uint32_t magic;

    memset(c, 0, sizeof(*c));
    c->base = exe_base();
    c->root = 0;
    c->pack = 0;
    c->resarr = 0;

    if (!pack_path(path, sizeof(path))) { logf_("pack: path fail"); return 0; }
    c->f = fopen(path, "rb");
    if (!c->f) { logf_("pack: cannot open %s", path); return 0; }
    if (!rd_at(c->f, 0, hdr, sizeof(hdr))) { logf_("pack: header read fail"); return 0; }
    magic = *(uint32_t *)hdr;
    if (magic != PACK_MAGIC) { logf_("pack: bad magic %08x", magic); return 0; }

    c->count  = *(uint32_t *)(hdr + 0x10);
    c->names  = *(uint64_t *)(hdr + 0x18);
    c->archs  = *(uint64_t *)(hdr + 0x20);
    c->offs   = *(uint64_t *)(hdr + 0x28);
    c->sizes  = *(uint64_t *)(hdr + 0x30);
    {
        uint64_t rel_off = *(uint64_t *)(hdr + 0x40);
        uint64_t rel_cnt = *(uint64_t *)(hdr + 0x48);
        if (rel_cnt > 4000000ull) rel_cnt = 0;
        c->reln = rel_cnt;
        c->reltab = (uint64_t *)malloc((size_t)(rel_cnt ? rel_cnt : 1) * 8);
        if (!c->reltab) return 0;
        if (rel_cnt && !rd_at(c->f, rel_off, c->reltab, (size_t)rel_cnt * 8)) {
            logf_("pack: reloc table read fail");
            return 0;
        }
    }
    if (c->count == 0 || c->count > 200000u) { logf_("pack: bogus count %u", c->count); return 0; }

    c->nametab = (uint64_t *)malloc((size_t)c->count * 8);
    c->offtab  = (uint64_t *)malloc((size_t)c->count * 8);
    c->sizetab = (uint64_t *)malloc((size_t)c->count * 8);
    c->archtab = (uint32_t *)malloc((size_t)c->count * 4);
    if (!c->nametab || !c->offtab || !c->sizetab || !c->archtab) { logf_("pack: oom"); return 0; }
    if (!rd_at(c->f, c->names, c->nametab, (size_t)c->count * 8) ||
        !rd_at(c->f, c->offs,  c->offtab,  (size_t)c->count * 8) ||
        !rd_at(c->f, c->sizes, c->sizetab, (size_t)c->count * 8) ||
        !rd_at(c->f, c->archs, c->archtab, (size_t)c->count * 4)) {
        logf_("pack: table read fail");
        return 0;
    }

    c->root = *(volatile uint64_t *)(c->base + OFF_RES_ROOT);
    if (!mem_ok(c->root, 0x2800)) { logf_("pack: res_root bad %p", (void *)c->root); return 0; }
    c->pack = *(volatile uint64_t *)(c->root + OFF_PACK_IN_ROOT);
    if (!mem_ok(c->pack, 0x30)) { logf_("pack: pack ptr bad %p", (void *)c->pack); return 0; }
    c->resarr = *(volatile uint64_t *)(c->pack + 0x18);
    if (!mem_ok(c->resarr, (size_t)c->count * 8)) { logf_("pack: resarr bad %p", (void *)c->resarr); return 0; }

    logf_("pack ok: count=%u root=%p pack=%p resarr=%p rel=%llu",
          c->count, (void *)c->root, (void *)c->pack, (void *)c->resarr,
          (unsigned long long)c->reln);
    return 1;
}

static void close_pack(Ctx *c)
{
    if (c->f) fclose(c->f);
    free(c->nametab); free(c->offtab); free(c->sizetab); free(c->archtab); free(c->reltab);
    memset(c, 0, sizeof(*c));
}

static uint64_t res_addr(Ctx *c, uint32_t idx)
{
    return *(volatile uint64_t *)(c->resarr + (uint64_t)idx * 8);
}

static int find_name(Ctx *c, const char *path, uint32_t *out_idx,
                     uint64_t *out_off, uint64_t *out_size, uint32_t *out_arch)
{
    uint32_t i;
    char buf[300];
    for (i = 0; i < c->count; i++) {
        if (!rd_at(c->f, c->nametab[i], buf, sizeof(buf))) continue;
        buf[sizeof(buf) - 1] = 0;
        if (strcmp(buf, path) == 0) {
            if (out_idx)  *out_idx = i;
            if (out_off)  *out_off = c->offtab[i];
            if (out_size) *out_size = c->sizetab[i];
            if (out_arch) *out_arch = c->archtab[i];
            return 1;
        }
    }
    return 0;
}

static int find_off(Ctx *c, uint64_t off, uint32_t *out_idx,
                    uint64_t *out_size, uint32_t *out_arch)
{
    uint32_t i;
    for (i = 0; i < c->count; i++) {
        if (c->offtab[i] == off) {
            if (out_idx)  *out_idx = i;
            if (out_size) *out_size = c->sizetab[i];
            if (out_arch) *out_arch = c->archtab[i];
            return 1;
        }
    }
    return 0;
}

static int rel_slot(Ctx *c, uint64_t off, uint64_t size, uint64_t r)
{
    uint64_t k;
    uint64_t abs_off = off + r;
    for (k = 0; k < c->reln; k++) {
        if (c->reltab[k] == abs_off) return 1;
    }
    return 0;
}

static uint64_t resolve_pack_ptr(Ctx *c, uint64_t packval)
{
    uint32_t i;
    for (i = 0; i < c->count; i++) {
        if (c->offtab[i] == packval) {
            uint64_t a = res_addr(c, i);
            return mem_ok(a, 8) ? a : 0;
        }
    }
    return 0;
}

static int patch_payload(Ctx *c, unsigned char *buf, uint64_t off, uint64_t size, const char *tag)
{
    uint64_t k;
    int n = 0;
    for (k = 0; k < c->reln; k++) {
        uint64_t v = c->reltab[k];
        uint64_t r, pv, addr;
        if (v < off || v >= off + size) continue;
        r = v - off;
        if (r + 8 > size) continue;
        pv = *(uint64_t *)(buf + r);
        if (!pv) continue;
        addr = resolve_pack_ptr(c, pv);
        if (!addr) {
            logf_("  %s reloc +0x%llx -> pack off 0x%llx : NOT LOADED", tag,
                  (unsigned long long)r, (unsigned long long)pv);
            return 0;
        }
        *(uint64_t *)(buf + r) = addr;
        n++;
    }
    logf_("  %s relocs patched = %d", tag, n);
    return 1;
}

// ---------- morph ----------

// 从“已加载”的目标资源直接拷贝（关内存在的载具才有）
static int do_morph(Ctx *c, const char *target)
{
    uint32_t ti = 0, ci = 0;
    uint64_t tsize = 0;
    uint32_t tarch = 0;
    uint64_t trt, leg_rt, clone, clone_leg, pm, pl;
    DWORD op1, op2;

    logf_("morph <- %s", target);
    if (!find_name(c, target, &ti, NULL, &tsize, &tarch)) { logf_("  target not in pack"); return 0; }
    if (tarch != ARCH_MECH) { logf_("  arch=%u not MECH", tarch); return 0; }
    if (tsize != MECH_SIZE) { logf_("  size=%llu != %d", (unsigned long long)tsize, MECH_SIZE); return 0; }

    trt = res_addr(c, ti);
    if (!mem_ok(trt, MECH_SIZE)) {
        logf_("  target NOT LOADED in this level (res=%p). pick a vehicle present in the level.", (void *)trt);
        return 0;
    }
    leg_rt = *(volatile uint64_t *)(trt + 0xC0);
    if (!mem_ok(leg_rt, LEG_SIZE)) { logf_("  target leg not loaded %p", (void *)leg_rt); return 0; }

    if (!find_name(c, CLONE_PATH, &ci, NULL, NULL, NULL)) { logf_("  clone not in pack"); return 0; }
    clone = res_addr(c, ci);
    if (!mem_ok(clone, MECH_SIZE)) { logf_("  clone res bad %p", (void *)clone); return 0; }
    clone_leg = *(volatile uint64_t *)(clone + 0xC0);
    if (!mem_ok(clone_leg, LEG_SIZE)) { logf_("  clone leg bad %p", (void *)clone_leg); return 0; }

    logf_("  target idx=%u res=%p leg=%p", ti, (void *)trt, (void *)leg_rt);
    logf_("  clone  idx=%u res=%p leg=%p", ci, (void *)clone, (void *)clone_leg);

    pm = *(volatile uint64_t *)(clone + PRESERVE_MECH);
    pl = *(volatile uint64_t *)(clone_leg + PRESERVE_LEG);
    logf_("  preserve mech+0x%x=0x%llx leg+0x%x=0x%llx",
          PRESERVE_MECH, (unsigned long long)pm, PRESERVE_LEG, (unsigned long long)pl);

    VirtualProtect((void *)clone, MECH_SIZE, PAGE_READWRITE, &op1);
    VirtualProtect((void *)clone_leg, LEG_SIZE, PAGE_READWRITE, &op2);
    memcpy((void *)clone, (const void *)trt, MECH_SIZE);
    memcpy((void *)clone_leg, (const void *)leg_rt, LEG_SIZE);

    *(volatile uint64_t *)(clone + PRESERVE_MECH) = pm;
    *(volatile uint64_t *)(clone_leg + PRESERVE_LEG) = pl;
    *(volatile uint64_t *)(clone + 0xC0) = clone_leg;    VirtualProtect((void *)clone, MECH_SIZE, op1, &op1);
    VirtualProtect((void *)clone_leg, LEG_SIZE, op2, &op2);

    logf_("  morph written ok (mech+0xC0 -> clone leg %p)", (void *)clone_leg);
    return 1;
}

// ---------- mech lookup / copy / respawn ----------

typedef struct {
    uint64_t ctrl, game, state, container, key, mech;
} PlayerRefs;

static int get_player_g(uint64_t base, PlayerRefs *pr, int verbose)
{
    memset(pr, 0, sizeof(*pr));
    pr->ctrl = *(volatile uint64_t *)(base + OFF_PLAYER_CTRL);
    if (!mem_ok(pr->ctrl, 0x60)) { if (verbose) logf_("  ctrl bad %p", (void *)pr->ctrl); return 0; }
    pr->game = *(volatile uint64_t *)(pr->ctrl + OFF_GAME);
    if (!mem_ok(pr->game, 0x10)) { if (verbose) logf_("  game bad %p", (void *)pr->game); return 0; }
    pr->state = pr->game + OFF_STATE_FROM_GAME;
    if (!mem_ok(pr->state, 0x40)) { if (verbose) logf_("  state bad %p", (void *)pr->state); return 0; }
    pr->container = *(volatile uint64_t *)(pr->state);
    pr->key = *(volatile uint64_t *)(pr->state + 0x30);
    if (!mem_ok(pr->key, 0x10)) { if (verbose) logf_("  key bad %p", (void *)pr->key); return 0; }
    if (*(volatile uint32_t *)pr->key != 0) {
        if (verbose) logf_("  guard: key[0]=%u (panel would skip)", *(volatile uint32_t *)pr->key);
        return 0;
    }
    {
        typedef uint64_t (*lookup_fn)(void *, void *);
        __try {
            pr->mech = ((lookup_fn)(base + FN_LOOKUP))((void *)pr->container, (void *)pr->key);
        } __except (seh_filter(GetExceptionInformation())) {
            if (verbose) logf_("  lookup faulted");
            pr->mech = 0;
        }
    }
    if (!mem_ok(pr->mech, 0x300)) { if (verbose) logf_("  mech bad %p", (void *)pr->mech); return 0; }
    if (verbose)
        logf_("  ctrl=%p game=%p state=%p container=%p key=%p key=[%u,%u,%u] mech=%p",
              (void *)pr->ctrl, (void *)pr->game, (void *)pr->state, (void *)pr->container,
              (void *)pr->key,
              *(volatile uint32_t *)(pr->key), *(volatile uint32_t *)(pr->key + 4),
              *(volatile uint32_t *)(pr->key + 8), (void *)pr->mech);
    return 1;
}

static int get_player(Ctx *c, PlayerRefs *pr, int verbose)
{
    return get_player_g(c->base, pr, verbose);
}

static void do_diag(Ctx *c)
{
    PlayerRefs pr;
    uint32_t ci = 0;
    uint64_t clone = 0, clone_leg = 0;

    if (!get_player(c, &pr, 1)) {
        logf_("diag: player unresolved");
    }
    if (find_name(c, CLONE_PATH, &ci, NULL, NULL, NULL)) {
        clone = res_addr(c, ci);
        if (mem_ok(clone, MECH_SIZE)) clone_leg = *(volatile uint64_t *)(clone + 0xC0);
        logf_("diag: clone idx=%u res=%p leg=%p", ci, (void *)clone, (void *)clone_leg);
    }
    if (pr.mech) {
        uint64_t u = *(volatile uint64_t *)(pr.mech + 0x258);
        logf_("diag: mech+0x258=%p %s clone", (void *)u,
              (u == clone) ? "==" : "!=");
        logf_("diag: mech+0x28=%p mech+0x60=%p mech+0xB60=%p mech+0xB68=%p",
              (void *)*(volatile uint64_t *)(pr.mech + 0x28),
              (void *)*(volatile uint64_t *)(pr.mech + 0x60),
              (void *)*(volatile uint64_t *)(pr.mech + 0xB60),
              (void *)*(volatile uint64_t *)(pr.mech + 0xB68));
    }
}

static int do_copy(Ctx *c)
{
    PlayerRefs pr;
    uint64_t blob;
    char r;
    if (!get_player(c, &pr, 1)) { logf_("copy: player unresolved"); return 0; }
    blob = c->root + OFF_BLOB_FROM_ROOT;
    logf_("copy: mech=%p blob=%p", (void *)pr.mech, (void *)blob);
    {
        typedef char (*copy_fn)(void *, void *);
        __try {
            r = ((copy_fn)(c->base + FN_COPY))((void *)pr.mech, (void *)blob);
            logf_("  copy returned %d", (int)(unsigned char)r);
        } __except (seh_filter(GetExceptionInformation())) {
            logf_("  copy faulted");
            return 0;
        }
    }
    return 1;
}

static int do_respawn(Ctx *c)
{
    PlayerRefs pr;
    uint64_t blob;
    pr.ctrl = *(volatile uint64_t *)(c->base + OFF_PLAYER_CTRL);
    if (!mem_ok(pr.ctrl, 0x60)) { logf_("respawn: ctrl bad %p", (void *)pr.ctrl); return 0; }
    blob = c->root + OFF_BLOB_FROM_ROOT;
    logf_("respawn: ctrl=%p blob=%p", (void *)pr.ctrl, (void *)blob);
    {
        typedef void (*respawn_fn)(void *, void *);
        __try {
            ((respawn_fn)(c->base + FN_RESPAWN))((void *)pr.ctrl, (void *)blob);
            logf_("  respawn returned");
        } __except (seh_filter(GetExceptionInformation())) {
            logf_("  respawn faulted");
            return 0;
        }
    }
    return 1;
}

// ---------- 自动接管：玩家换载具瞬间把原型数据拷进 dummy ----------

static int do_go(Ctx *c, const char *target)
{
    if (!do_morph(c, target)) { logf_("go: morph failed"); return 0; }
    if (!do_copy(c)) { logf_("go: copy failed, respawn skipped"); return 0; }
    do_respawn(c);
    return 1;
}

// 只打开一次 pack，把 dummy 槽（MECH/LEG）地址缓存下来
static int resolve_dummy(void)
{
    Ctx c;
    uint32_t ci = 0;
    uint64_t clone, leg;

    if (g_clone && g_clone_leg) return 1;
    if (!open_pack(&c)) { lstrcpynA(g_last_err, "pack open failed", sizeof(g_last_err)); return 0; }
    if (!find_name(&c, CLONE_PATH, &ci, NULL, NULL, NULL)) {
        close_pack(&c);
        lstrcpynA(g_last_err, "dummy asset not found", sizeof(g_last_err));
        return 0;
    }
    clone = res_addr(&c, ci);
    close_pack(&c);
    if (!mem_ok(clone, MECH_SIZE)) {
        lstrcpynA(g_last_err, "dummy mech invalid", sizeof(g_last_err));
        return 0;
    }
    leg = *(volatile uint64_t *)(clone + 0xC0);
    if (!mem_ok(leg, LEG_SIZE)) {
        lstrcpynA(g_last_err, "dummy leg invalid", sizeof(g_last_err));
        return 0;
    }
    g_clone = clone;
    g_clone_leg = leg;
    logf_("auto: dummy idx=%u mech=%p leg=%p", ci, (void *)clone, (void *)leg);
    return 1;
}

// 把 src（将要上的原型载具）MECH+LEG 复制进 dummy；保留 dummy 自身的运行时槽
static int make_dummy_from(uint64_t src)
{
    uint64_t leg, pm, pl;
    DWORD op1, op2;

    if (!g_clone || !g_clone_leg) return 0;
    if (!mem_ok(src, 0xC8)) { logf_("auto: src %p invalid", (void *)src); return 0; }
    leg = *(volatile uint64_t *)(src + 0xC0);
    if (!mem_ok(leg, LEG_SIZE)) {
        logf_("auto: src leg %p invalid (leave prototype)", (void *)leg);
        return 0;
    }

    pm = *(volatile uint64_t *)(g_clone + PRESERVE_MECH);
    pl = *(volatile uint64_t *)(g_clone_leg + PRESERVE_LEG);

    if (!VirtualProtect((void *)g_clone, MECH_SIZE, PAGE_READWRITE, &op1)) return 0;
    if (!VirtualProtect((void *)g_clone_leg, LEG_SIZE, PAGE_READWRITE, &op2)) {
        VirtualProtect((void *)g_clone, MECH_SIZE, op1, &op1);
        return 0;
    }
    memcpy((void *)g_clone, (const void *)src, MECH_SIZE);
    memcpy((void *)g_clone_leg, (const void *)leg, LEG_SIZE);
    *(volatile uint64_t *)(g_clone + PRESERVE_MECH) = pm;
    *(volatile uint64_t *)(g_clone_leg + PRESERVE_LEG) = pl;
    *(volatile uint64_t *)(g_clone + 0xC0) = g_clone_leg;
    VirtualProtect((void *)g_clone, MECH_SIZE, op1, &op1);
    VirtualProtect((void *)g_clone_leg, LEG_SIZE, op2, &op2);

    logf_("auto: dummy <- src %p (src leg %p)", (void *)src, (void *)leg);
    return 1;
}

// 每帧一次：只做「玩家 unit 指针是否变化」的判断，开销可忽略
static void speed_update(void);

static void auto_tick(void)
{
    PlayerRefs pr;
    uint64_t u;

    if (!g_auto_on) return;
    if (g_main_tid && GetCurrentThreadId() != g_main_tid) return;
    if (!get_player_g(exe_base(), &pr, 0)) return;

    u = *(volatile uint64_t *)(pr.mech + OFF_MECH_UNIT);
    if (u == g_last_unit) return;

    logf_("auto: unit change %p -> %p (mech=%p)", (void *)g_last_unit, (void *)u, (void *)pr.mech);
    if (u && g_clone && u != g_clone && make_dummy_from(u)) {
        *(volatile uint64_t *)(pr.mech + OFF_MECH_UNIT) = g_clone;
        g_swap_count++;
        g_speed_applied = 0;   // dummy 已被新原型覆盖，下一帧按背包状态重新施加
        logf_("auto: mech+0x258 -> dummy %p (swap #%llu)",
              (void *)g_clone, (unsigned long long)g_swap_count);
        u = g_clone;
    }
    g_last_unit = u;
}

static void sdl_pump_hook(void)
{
    typedef void (*pump_fn)(void);
    LARGE_INTEGER t0, t1;
    QueryPerformanceCounter(&t0);
    ((pump_fn)g_sdl_orig)();
    __try {
        auto_tick();
        speed_update();
    } __except (seh_filter(GetExceptionInformation())) {
        logf_("auto: tick fault");
    }
    QueryPerformanceCounter(&t1);
    if (g_qpc_freq) {
        g_tick_us += (t1.QuadPart - t0.QuadPart) * 1000000 / g_qpc_freq;
        g_tick_n++;
        if ((g_tick_n % 600) == 0) {
            logf_("tick: n=%llu avg_us=%lld speed_on=%d applied=%d has=%d",
                  g_tick_n, g_tick_us / 600, g_speed_on, g_speed_applied, g_last_has);
            g_tick_us = 0;
        }
    }
}

static int install_hook(void)
{
    uint64_t slot = exe_base() + OFF_SDL_PUMP_SLOT;
    DWORD old;
    void *cur;

    if (g_sdl_slot) return 1;
    QueryPerformanceFrequency((LARGE_INTEGER *)&g_qpc_freq);
    if (!mem_ok(slot, 8)) {
        lstrcpynA(g_last_err, "SDL slot invalid", sizeof(g_last_err));
        return 0;
    }
    cur = *(void **)slot;
    if (!cur) {
        lstrcpynA(g_last_err, "SDL_PumpEvents unresolved", sizeof(g_last_err));
        return 0;
    }
    // 若槽位已被别的 bkswap 实例挂钩，优先取 SDL2 的真实导出地址，避免链式重复
    {
        HMODULE sdl = GetModuleHandleA("SDL2.dll");
        void *real = sdl ? (void *)GetProcAddress(sdl, "SDL_PumpEvents") : NULL;
        if (real) cur = real;
    }
    if (!VirtualProtect((void *)slot, 8, PAGE_EXECUTE_READWRITE, &old)) {
        lstrcpynA(g_last_err, "VirtualProtect slot failed", sizeof(g_last_err));
        return 0;
    }
    g_sdl_orig = cur;
    *(void **)slot = (void *)sdl_pump_hook;
    VirtualProtect((void *)slot, 8, old, &old);
    g_sdl_slot = (void *)slot;
    logf_("auto: SDL_PumpEvents hooked (slot %p orig %p)", (void *)slot, cur);
    return 1;
}

static void uninstall_hook(void)
{
    DWORD old;
    if (!g_sdl_slot) return;
    if (VirtualProtect(g_sdl_slot, 8, PAGE_EXECUTE_READWRITE, &old)) {
        *(void **)g_sdl_slot = g_sdl_orig;
        VirtualProtect(g_sdl_slot, 8, old, &old);
        logf_("auto: hook removed");
    }
    g_sdl_slot = NULL;
    g_sdl_orig = NULL;
}

// ---------- 背包条件速度加成：背包里有指定 item → 玩家 dummy 速度 ×N ----------
//
// 判定：mech+0x238 → 背包容器 sub+0x250(vector, 0x18 stride)，元素 {item资源, item+1, 数量}。
// 命中则把 dummy LEG 的三向速度/加速度改为「换载具时的原始值 × 倍率」，只改 dummy，不碰原型。

#define LEG_OFF_MAX_FWD_SPEED  0x101C
#define LEG_OFF_MAX_SIDE_SPEED 0x1020
#define LEG_OFF_MAX_REV_SPEED  0x1024
#define LEG_OFF_MAX_FWD_ACCEL  0x1028
#define LEG_OFF_MAX_SIDE_ACCEL 0x102C
#define LEG_OFF_MAX_REV_ACCEL  0x1030

static uint64_t g_item_addr = 0;
static float g_speed_mult = 2.0f;
static float g_speed_base[6];

static const uint32_t g_speed_offs[6] = {
    LEG_OFF_MAX_FWD_SPEED, LEG_OFF_MAX_SIDE_SPEED, LEG_OFF_MAX_REV_SPEED,
    LEG_OFF_MAX_FWD_ACCEL, LEG_OFF_MAX_SIDE_ACCEL, LEG_OFF_MAX_REV_ACCEL
};

static int inv_has_item(uint64_t mech, uint64_t item)
{
    uint64_t sub, b, e, p, v;

    if (!mech || !item) return 0;
    sub = *(volatile uint64_t *)(mech + 0x238);
    if (!mem_ok(sub, 0x270)) return 0;
    b = *(volatile uint64_t *)(sub + 0x250);
    e = *(volatile uint64_t *)(sub + 0x258);
    if (!b || !e || e < b || (e - b) > 0x2000) return 0;
    for (p = b; p + 0x18 <= e; p += 0x18) {
        uint64_t b2 = *(volatile uint64_t *)p;        // slot 的子 vector begin（或直接 item）
        uint64_t e2 = *(volatile uint64_t *)(p + 8);  // 子 vector end
        uint64_t q;
        v = b2;
        if (v == item) return 1;
        // slot 自身的 {begin,end} 就是一个 item 数组：元素 {item, item+1, count}
        if (!b2 || !e2 || e2 <= b2 || (e2 - b2) > 0x800) continue;
        if (((e2 - b2) % 0x18) != 0) continue;
        if (!mem_ok(b2, (size_t)(e2 - b2))) continue;
        for (q = b2; q + 0x18 <= e2; q += 0x18) {
            if (*(volatile uint64_t *)q == item) return 1;
        }
    }
    return 0;
}

static int resolve_item(const char *path)
{
    Ctx c;
    uint32_t i = 0;
    uint64_t a = 0;
    if (!path || !*path) return 0;
    if (!open_pack(&c)) { lstrcpynA(g_last_err, "pack open failed", sizeof(g_last_err)); return 0; }
    if (find_name(&c, path, &i, NULL, NULL, NULL)) a = res_addr(&c, i);
    close_pack(&c);
    if (!a) { lstrcpynA(g_last_err, "item not loaded / not found", sizeof(g_last_err)); return 0; }
    g_item_addr = a;
    logf_("speed: item %s -> %p", path, (void *)a);
    return 1;
}

static void speed_apply(int on)
{
    PlayerRefs pr;
    uint64_t unit, leg;
    float *f;
    int i;
    DWORD old;

    if (!get_player_g(exe_base(), &pr, 0)) return;
    unit = *(volatile uint64_t *)(pr.mech + OFF_MECH_UNIT);
    if (!mem_ok(unit, 0xC8)) return;
    leg = *(volatile uint64_t *)(unit + 0xC0);
    if (!mem_ok(leg, LEG_SIZE)) return;

    f = (float *)leg;
    if (on && !g_speed_applied) {
        for (i = 0; i < 6; i++) g_speed_base[i] = f[g_speed_offs[i] / 4];
    }
    if (!VirtualProtect((void *)leg, LEG_SIZE, PAGE_READWRITE, &old)) return;
    for (i = 0; i < 6; i++) {
        f[g_speed_offs[i] / 4] = on ? (g_speed_base[i] * g_speed_mult) : g_speed_base[i];
    }
    VirtualProtect((void *)leg, LEG_SIZE, old, &old);

    g_speed_applied = on;
    logf_("speed: %s x%.2f (leg=%p base fwd=%.3f)",
          on ? "APPLY" : "restore", g_speed_mult, (void *)leg,
          g_speed_base[0]);
}

static void speed_update(void)
{
    PlayerRefs pr;
    int has;

    if (!g_speed_on || !g_item_addr) return;
    if (g_main_tid && GetCurrentThreadId() != g_main_tid) return;
    if (!get_player_g(exe_base(), &pr, 0)) return;

    has = inv_has_item(pr.mech, g_item_addr);
    g_last_has = has;
    if (has && !g_speed_applied) speed_apply(1);
    else if (!has && g_speed_applied) speed_apply(0);
}

__declspec(dllexport) int bks_item_speed_mod(const char *item_path, float multiplier)
{
    g_main_tid = GetCurrentThreadId();
    if (!resolve_item(item_path)) {
        logf_("speed: enable failed: %s", g_last_err);
        return 0;
    }
    if (multiplier > 0.0f) g_speed_mult = multiplier;
    g_speed_applied = 0;               // 以当前 dummy 数据为基准
    g_speed_on = 1;
    if (!install_hook()) {
        g_speed_on = 0;
        logf_("speed: enable failed: %s", g_last_err);
        return 0;
    }
    logf_("speed: ON item=%p x%.2f", (void *)g_item_addr, g_speed_mult);
    speed_update();                    // 立即按当前背包状态尝试一次
    return 1;
}

__declspec(dllexport) int bks_item_speed_mod_off(void)
{
    g_speed_on = 0;
    if (g_speed_applied) speed_apply(0);
    logf_("speed: OFF");
    if (!g_auto_on) uninstall_hook();
    return 1;
}

__declspec(dllexport) int bks_item_speed_mod_state(void)
{
    return g_speed_on ? (g_speed_applied ? 2 : 1) : 0;
}

// ---------- C ABI（供 mod / 其它 DLL 调用；必须主线程） ----------

__declspec(dllexport) int bks_auto_enable(void)
{
    g_main_tid = GetCurrentThreadId();
    if (!resolve_dummy()) {
        logf_("auto: enable failed: %s", g_last_err);
        return 0;
    }
    if (!install_hook()) {
        logf_("auto: enable failed: %s", g_last_err);
        return 0;
    }
    g_last_unit = 0;              // 首帧立即接管当前载具
    InterlockedExchange(&g_auto_on, 1);
    logf_("auto: ON");
    return 1;
}

__declspec(dllexport) int bks_auto_disable(void)
{
    InterlockedExchange(&g_auto_on, 0);
    if (!g_speed_on) uninstall_hook();
    logf_("auto: OFF");
    return 1;
}

__declspec(dllexport) int bks_auto_state(void)
{
    return (int)g_auto_on;
}

__declspec(dllexport) unsigned long long bks_player_mech(void)
{
    PlayerRefs pr;
    if (!get_player_g(exe_base(), &pr, 0)) return 0;
    return pr.mech;
}

__declspec(dllexport) unsigned long long bks_player_unit(void)
{
    PlayerRefs pr;
    if (!get_player_g(exe_base(), &pr, 0)) return 0;
    return *(volatile uint64_t *)(pr.mech + OFF_MECH_UNIT);
}

__declspec(dllexport) unsigned long long bks_dummy_unit(void)
{
    if (!g_clone && !resolve_dummy()) return 0;
    return g_clone;
}

__declspec(dllexport) unsigned long long bks_asset_addr(const char *path)
{
    Ctx c;
    uint32_t i = 0;
    uint64_t a = 0;
    if (!path || !*path) return 0;
    if (!open_pack(&c)) return 0;
    if (find_name(&c, path, &i, NULL, NULL, NULL)) a = res_addr(&c, i);
    close_pack(&c);
    return a;
}

__declspec(dllexport) int bks_swap(const char *path)
{
    Ctx c;
    int ok = 0;
    if (!path || !*path) return 0;
    if (g_main_tid && GetCurrentThreadId() != g_main_tid) {
        lstrcpynA(g_last_err, "bks_swap must run on main thread", sizeof(g_last_err));
        return 0;
    }
    if (!open_pack(&c)) { lstrcpynA(g_last_err, "pack open failed", sizeof(g_last_err)); return 0; }
    __try {
        ok = do_go(&c, path);
    } __except (seh_filter(GetExceptionInformation())) {
        ok = 0;
    }
    close_pack(&c);
    if (ok) { g_last_unit = 0; g_speed_applied = 0; }   // 让自动接管/速度加成重新同步
    return ok;
}

__declspec(dllexport) const char *bks_last_error(void)
{
    return g_last_err;
}

__declspec(dllexport) const char *bks_version(void)
{
    return "bkswap/3";
}

// ---------- command dispatch ----------

static void run_line(const char *line)
{
    Ctx c;
    char cmd[64];
    const char *arg;

    while (*line == ' ' || *line == '\t') line++;
    if (!*line || *line == '#' || *line == ';') return;

    {
        size_t i = 0;
        while (line[i] && line[i] != ' ' && line[i] != '\t' && i < sizeof(cmd) - 1) {
            cmd[i] = line[i];
            i++;
        }
        cmd[i] = 0;
        arg = line + i;
        while (*arg == ' ' || *arg == '\t') arg++;
    }

    logf_("cmd: %s %s", cmd, arg);

    if (!open_pack(&c)) return;
    __try {
        if (_stricmp(cmd, "diag") == 0) {
            do_diag(&c);
        } else if (_stricmp(cmd, "morph") == 0) {
            do_morph(&c, arg);
        } else if (_stricmp(cmd, "copy") == 0) {
            do_copy(&c);
        } else if (_stricmp(cmd, "respawn") == 0) {
            do_respawn(&c);
        } else if (_stricmp(cmd, "go") == 0) {
            do_go(&c, arg);
        } else if (_stricmp(cmd, "auto") == 0) {
            if (_stricmp(arg, "on") == 0) bks_auto_enable();
            else if (_stricmp(arg, "off") == 0) bks_auto_disable();
            else logf_("auto: state=%d dummy=%p last_unit=%p swaps=%llu",
                       bks_auto_state(), (void *)g_clone, (void *)g_last_unit,
                       (unsigned long long)g_swap_count);
        } else if (_stricmp(cmd, "item") == 0) {
            if (_stricmp(arg, "off") == 0) {
                bks_item_speed_mod_off();
            } else {
                char path[256];
                float mult = 2.0f;
                const char *sp;
                size_t k = 0;
                while (arg[k] && arg[k] != ' ' && arg[k] != '\t' && k < sizeof(path) - 1) {
                    path[k] = arg[k];
                    k++;
                }
                path[k] = 0;
                sp = arg + k;
                while (*sp == ' ' || *sp == '\t') sp++;
                if (*sp) mult = (float)atof(sp);
                if (k) bks_item_speed_mod(path, mult);
                else logf_("item: state=%d item=%p x%.2f",
                           bks_item_speed_mod_state(), (void *)g_item_addr, g_speed_mult);
            }
        } else {
            logf_("unknown cmd");
        }
    } __except (seh_filter(GetExceptionInformation())) {
        logf_("cmd faulted");
    }
    close_pack(&c);
}

static void read_commands(void)
{
    char path[MAX_PATH];
    char buf[8192];
    FILE *f;
    size_t n;
    char *p;

    DWORD tmp = GetTempPathA(MAX_PATH, path);
    if (tmp == 0 || tmp >= MAX_PATH) return;
    lstrcatA(path, "bk_swap.txt");

    f = fopen(path, "rb");
    if (!f) { logf_("no bk_swap.txt, running diag"); run_line("diag"); return; }
    n = fread(buf, 1, sizeof(buf) - 1, f);
    fclose(f);
    buf[n] = 0;

    p = buf;
    while (p && *p) {
        char *e = p;
        while (*e && *e != '\r' && *e != '\n') e++;
        {
            char save = *e;
            *e = 0;
            run_line(p);
            if (!save) break;
            p = e + 1;
            while (*p == '\r' || *p == '\n') p++;
        }
    }
}

BOOL WINAPI DllMain(HINSTANCE hinst, DWORD reason, LPVOID reserved)
{
    (void)hinst;
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        InitializeCriticalSection(&g_cs);
        g_main_tid = GetCurrentThreadId();
        log_open();
        logf_("== dll attach pid=%lu ==", (unsigned long)GetCurrentProcessId());
    }
    return TRUE;
}

__declspec(dllexport) int luaopen_bkswap(void *L)
{
    (void)L;
    logf_("== luaopen_bkswap ==");
    read_commands();
    return 0;
}
