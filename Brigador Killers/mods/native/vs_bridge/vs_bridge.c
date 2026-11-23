// vs_bridge.c - probe DLL for Brigador Killers pack write-back RE
// Phase 2: read-only runtime probing via a worker thread (no Lua API needed).
//
// In-game console:
//   lua local f,e=package.loadlib("C:/bk/vb.dll","luaopen_vb");if f then f() print("OK") else print(e) end
//
// Commands: write lines to %TEMP%\bk_cmd.txt
//   probe                 dump pointers / locate PackFile by header magic
//   find <asset path>     path -> index via engine binary search
//   parse <file>          parse a JSON file with the engine parser

#include <windows.h>
#include <stdio.h>
#include <stdarg.h>
#include <stdint.h>
#include <string.h>
#include <share.h>

#define EXE_BASE 0x140000000ull
#define OFF_ASSET_MGR   0x0B385F8ull
#define OFF_GLOBAL_JSON 0x0B385C0ull
#define OFF_RES_ROOT    0x0B38850ull
#define FN_FIND_INDEX   0x0225F10ull   // int f(PackFile*, const char* path)
#define FN_JSON_PARSE   0x01FB4C0ull   // void* f(const char* text)

#define PACK_MAGIC 0x5EA1C012u

static FILE *g_log = NULL;
static CRITICAL_SECTION g_cs;

static void log_open(void)
{
    char path[MAX_PATH];
    DWORD n = GetTempPathA(MAX_PATH, path);
    if (n == 0 || n >= MAX_PATH) return;
    lstrcatA(path, "bk_probe.txt");
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

static int readable(const void *p)
{
    MEMORY_BASIC_INFORMATION mbi;
    if (!p) return 0;
    if (VirtualQuery(p, &mbi, sizeof(mbi)) != sizeof(mbi)) return 0;
    if (mbi.State != MEM_COMMIT) return 0;
    if (mbi.Protect & (PAGE_NOACCESS | PAGE_GUARD)) return 0;
    return 1;
}

#define RD64(p) (*(volatile uint64_t *)(p))
#define RD32(p) (*(volatile uint32_t *)(p))
#define RD8(p)  (*(volatile unsigned char *)(p))

static uint64_t rd64_safe(uint64_t p, int *ok)
{
    if (!readable((const void *)p)) { *ok = 0; return 0; }
    // must be fully readable for 8 bytes: verify region end
    MEMORY_BASIC_INFORMATION mbi;
    VirtualQuery((const void *)p, &mbi, sizeof(mbi));
    uint64_t end = (uint64_t)mbi.BaseAddress + mbi.RegionSize;
    if (p + 8 > end) { *ok = 0; return 0; }
    *ok = 1;
    return *(volatile uint64_t *)p;
}

static int cstr_at(uint64_t p, char *out, int cap)
{
    int i;
    if (!readable((const void *)p)) return 0;
    for (i = 0; i < cap - 1; i++) {
        unsigned char c = RD8(p + i);
        out[i] = (char)c;
        if (c == 0) return i > 0;
        if (c < 0x20 || c > 0x7e) { out[i] = 0; return 0; }
    }
    out[cap - 1] = 0;
    return 1;
}

// returns PackFile* or 0; scans qwords in [obj, obj+span) for a pointer whose
// first dword is the pack header magic.
static uint64_t find_pack_in(uint64_t obj, int span, const char *what)
{
    int i, ok;
    if (!obj) return 0;
    for (i = 0; i < span; i += 8) {
        uint64_t q = rd64_safe(obj + i, &ok);
        if (!ok || !q) continue;
        if (!readable((const void *)q)) continue;
        if (RD32(q) == PACK_MAGIC) {
            logf_("%s: PACK at +0x%x -> %p", what, i, (void *)q);
            return q;
        }
    }
    return 0;
}

static uint64_t safe_ptr(uint64_t p, const void *what)
{
    if (!p || !readable((const void *)p)) {
        logf_("  %s: ptr %p not readable", (const char *)what, (void *)p);
        return 0;
    }
    return p;
}

static void dump_pack(uint64_t reg)
{
    int ok = 0;
    uint64_t hdr = rd64_safe(reg, &ok);
    logf_("pack=%p header=%p", (void *)reg, (void *)hdr);
    if (!hdr || !readable((const void *)hdr)) { logf_("  header unreadable"); return; }
    uint32_t magic = RD32(hdr), ver = RD32(hdr + 4);
    logf_("  magic=%08x ver=%x", magic, ver);
    if (magic != PACK_MAGIC) { logf_("  magic mismatch, stop"); return; }

    uint32_t count = RD32(hdr + 0x10);
    uint64_t paths = rd64_safe(hdr + 0x18, &ok);
    uint64_t offs  = rd64_safe(hdr + 0x28, &ok);
    uint64_t sizes = rd64_safe(hdr + 0x30, &ok);
    uint64_t resarr = rd64_safe(reg + 0x18, &ok);
    logf_("  count=%u paths=%p offs=%p sizes=%p resarr=%p", count,
          (void *)paths, (void *)offs, (void *)sizes, (void *)resarr);
    if (count > 200000) { logf_("  count bogus, stop"); return; }

    if (safe_ptr(paths, "paths")) {
        for (int i = 0; i < 8 && (uint32_t)i < count; i++) {
            char s[256];
            uint64_t p = rd64_safe(paths + i * 8, &ok);
            if (!ok || !p) continue;
            int good = cstr_at(p, s, sizeof(s));
            uint64_t off = safe_ptr(offs, "offs") ? rd64_safe(offs + i * 8, &ok) : 0;
            uint64_t sz  = safe_ptr(sizes, "sizes") ? rd64_safe(sizes + i * 8, &ok) : 0;
            logf_("  [%d] %s off=%llx size=%llx", i, good ? s : "(bad str)",
                  (unsigned long long)off, (unsigned long long)sz);
        }
    }
    if (safe_ptr(resarr, "resarr")) {
        for (int i = 0; i < 8 && (uint32_t)i < count; i++) {
            int ok2 = 0;
            uint64_t res = rd64_safe(resarr + i * 8, &ok2);
            if (!ok2 || !res || !readable((const void *)res)) continue;
            uint32_t arch = RD32(res - 0x18);
            uint64_t np = rd64_safe(res - 0x10, &ok2);
            char s[256];
            int good = ok2 && np && cstr_at(np, s, sizeof(s));
            logf_("  res[%d]=%p arch=%u dirty=%u name=%s", i, (void *)res, arch,
                  RD8(res - 4), good ? s : "?");
        }
    }
}

static void cmd_probe(void)
{
    uint64_t base = (uint64_t)GetModuleHandleA(NULL);
    int ok = 0;
    logf_("== probe == base=%p", (void *)base);
    uint64_t mgr = rd64_safe(base + OFF_ASSET_MGR, &ok);
    uint64_t gj  = rd64_safe(base + OFF_GLOBAL_JSON, &ok);
    uint64_t root = rd64_safe(base + OFF_RES_ROOT, &ok);
    uint64_t reg = ok ? rd64_safe(root + 0x2718, &ok) : 0;
    logf_("asset_mgr=%p global_json=%p res_root=%p pack=%p", (void *)mgr, (void *)gj, (void *)root, (void *)reg);
    if (!reg || !readable((const void *)reg)) { logf_("pack unreadable"); return; }
    dump_pack(reg);
}

static void cmd_find(const char *path)
{
    uint64_t base = (uint64_t)GetModuleHandleA(NULL);
    int ok = 0;
    uint64_t root = rd64_safe(base + OFF_RES_ROOT, &ok);
    uint64_t reg = ok ? rd64_safe(root + 0x2718, &ok) : 0;
    logf_("find '%s' pack=%p", path, (void *)reg);
    if (!reg || !readable((const void *)reg)) { logf_("  pack unreadable"); return; }
    typedef int (*find_fn)(void *, const char *);
    int idx = ((find_fn)(base + FN_FIND_INDEX))(reg, path);
    logf_("  lookup -> %d", idx);
    if (idx >= 0) {
        int ok2 = 0;
        uint64_t hdr = rd64_safe(reg, &ok2);
        uint64_t resarr = rd64_safe(reg + 0x18, &ok2);
        uint64_t res = (ok2 && resarr) ? rd64_safe(resarr + (uint64_t)idx * 8, &ok2) : 0;
        logf_("  hdr=%p res=%p arch=%u", (void *)hdr, (void *)res,
              (res && readable((const void *)res)) ? RD32(res - 0x18) : 0);
    }
}

static void cmd_list(const char *sub)
{
    uint64_t base = (uint64_t)GetModuleHandleA(NULL);
    int ok = 0;
    uint64_t root = rd64_safe(base + OFF_RES_ROOT, &ok);
    uint64_t reg = ok ? rd64_safe(root + 0x2718, &ok) : 0;
    if (!reg || !readable((const void *)reg)) { logf_("list: pack unreadable"); return; }
    uint64_t hdr = rd64_safe(reg, &ok);
    if (!ok || !hdr || !readable((const void *)hdr) || RD32(hdr) != PACK_MAGIC) { logf_("list: bad header"); return; }
    uint32_t count = RD32(hdr + 0x10);
    uint64_t paths = rd64_safe(hdr + 0x18, &ok);
    if (!ok || !paths || !readable((const void *)paths)) { logf_("list: bad paths"); return; }
    logf_("list '%s': count=%u", sub, count);
    int shown = 0;
    for (uint32_t i = 0; i < count && shown < 60; i++) {
        int ok2 = 0;
        uint64_t p = rd64_safe(paths + (uint64_t)i * 8, &ok2);
        char s[300];
        if (!ok2 || !p || !cstr_at(p, s, sizeof(s))) continue;
        if (sub[0] && !strstr(s, sub)) continue;
        logf_("  [%u] %s", i, s);
        shown++;
    }
    logf_("list done, shown=%d", shown);
}

static void cmd_parse(const char *file)
{
    char *buf = NULL;
    FILE *f = NULL;
    if (fopen_s(&f, file, "rb") == 0 && f) {
        fseek(f, 0, SEEK_END);
        long n = ftell(f);
        fseek(f, 0, SEEK_SET);
        if (n > 0 && n < 4 * 1024 * 1024) {
            buf = (char *)malloc((size_t)n + 1);
            if (buf) {
                size_t rd = fread(buf, 1, (size_t)n, f);
                buf[rd] = 0;
            }
        }
        fclose(f);
    }
    if (!buf) { logf_("parse: cannot read %s", file); return; }
    uint64_t base = (uint64_t)GetModuleHandleA(NULL);
    typedef void *(*parse_fn)(const char *);
    void *json = ((parse_fn)(base + FN_JSON_PARSE))(buf);
    logf_("parse %s (%d bytes) -> json=%p", file, (int)strlen(buf), json);
    if (json) {
        // root object: dump first key/value types via raw reads (best effort)
        int ok;
        uint64_t t = rd64_safe((uint64_t)json, &ok);
        logf_("  json tag=%p first=%016llx", (void *)t, (unsigned long long)(ok ? t : 0));
    }
    free(buf);
}

static uint64_t get_pack(void)
{
    uint64_t base = (uint64_t)GetModuleHandleA(NULL);
    int ok = 0;
    uint64_t root = rd64_safe(base + OFF_RES_ROOT, &ok);
    uint64_t pack = ok ? rd64_safe(root + 0x2718, &ok) : 0;
    if (!pack || !readable((const void *)pack)) {
        logf_("pack unavailable");
        return 0;
    }
    return pack;
}

static int pack_find(uint64_t pack, const char *path)
{
    uint64_t base = (uint64_t)GetModuleHandleA(NULL);
    typedef int (*find_fn)(void *, const char *);
    return ((find_fn)(base + FN_FIND_INDEX))(pack, path);
}

static void *json_from_file(const char *file)
{
    char *buf = NULL;
    FILE *f = NULL;
    if (fopen_s(&f, file, "rb") == 0 && f) {
        fseek(f, 0, SEEK_END);
        long n = ftell(f);
        fseek(f, 0, SEEK_SET);
        if (n > 0 && n < 16 * 1024 * 1024) {
            buf = (char *)malloc((size_t)n + 1);
            if (buf) {
                size_t rd = fread(buf, 1, (size_t)n, f);
                buf[rd] = 0;
            }
        }
        fclose(f);
    }
    if (!buf) { logf_("json_from_file: cannot read %s", file); return NULL; }
    uint64_t base = (uint64_t)GetModuleHandleA(NULL);
    typedef void *(*parse_fn)(const char *);
    void *json = ((parse_fn)(base + FN_JSON_PARSE))(buf);
    free(buf);
    return json;
}

// SEH capture: turn engine faults into log lines instead of process death.
static DWORD g_exc_code;
static void *g_exc_addr;
static ULONG_PTR g_exc_info0, g_exc_info1;
static CONTEXT g_exc_ctx;
static int seh_filter(EXCEPTION_POINTERS *ep)
{
    g_exc_code = ep->ExceptionRecord->ExceptionCode;
    g_exc_addr = ep->ExceptionRecord->ExceptionAddress;
    g_exc_info0 = ep->ExceptionRecord->ExceptionInformation[0];
    g_exc_info1 = ep->ExceptionRecord->ExceptionInformation[1];
    if (ep->ContextRecord) {
        g_exc_ctx = *ep->ContextRecord;
        logf_("  EXC code=%08lx at=%p rip=%p rax=%p rcx=%p rdx=%p",
             (unsigned long)g_exc_code, g_exc_addr, (void *)ep->ContextRecord->Rip,
             (void *)ep->ContextRecord->Rax, (void *)ep->ContextRecord->Rcx,
             (void *)ep->ContextRecord->Rdx);
    }
    return EXCEPTION_EXECUTE_HANDLER;
}

static void cmd_dump(const char *args)
{
    const char *sp = strrchr(args, ' ');
    if (!sp) { logf_("dump: need '<path> <outfile>'"); return; }
    char path[512], out[MAX_PATH];
    size_t plen = (size_t)(sp - args);
    if (plen >= sizeof(path)) plen = sizeof(path) - 1;
    memcpy(path, args, plen); path[plen] = 0;
    lstrcpynA(out, sp + 1, MAX_PATH);

    uint64_t pack = get_pack();
    if (!pack) return;
    int idx = pack_find(pack, path);
    logf_("dump '%s' -> idx=%d out=%s", path, idx, out);
    if (idx < 0) return;
    int ok = 0;
    uint64_t hdr = rd64_safe(pack, &ok);
    uint64_t offarr = rd64_safe(hdr + 0x28, &ok);
    uint64_t szarr = rd64_safe(hdr + 0x30, &ok);
    uint64_t off = rd64_safe(offarr + (uint64_t)idx * 8, &ok);
    uint64_t sz = rd64_safe(szarr + (uint64_t)idx * 8, &ok);
    logf_("  pack off=%llx size=%llu", (unsigned long long)off, (unsigned long long)sz);
    if (!sz || sz > 16 * 1024 * 1024) { logf_("  size refused"); return; }

    HANDLE h = CreateFileA("assets.pack", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL,
                           OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) { logf_("  cannot open assets.pack (%lu)", GetLastError()); return; }
    LARGE_INTEGER li; li.QuadPart = (LONGLONG)off;
    SetFilePointerEx(h, li, NULL, FILE_BEGIN);
    char *buf = (char *)malloc((size_t)sz);
    DWORD got = 0;
    BOOL r = buf ? ReadFile(h, buf, (DWORD)sz, &got, NULL) : FALSE;
    CloseHandle(h);
    if (!r || got != sz) { logf_("  read failed got=%lu err=%lu", got, GetLastError()); free(buf); return; }
    FILE *o = NULL;
    if (fopen_s(&o, out, "wb") == 0 && o) { fwrite(buf, 1, (size_t)sz, o); fclose(o); }
    else logf_("  cannot write %s", out);
    logf_("  wrote %lu bytes; head: %.64s", got, buf);
    free(buf);
}

// args: "<asset path> <out file>"  (struct -> JSON text via funcB)
static void cmd_export(const char *args)
{
    const char *sp = strrchr(args, ' ');
    if (!sp) { logf_("export: need '<path> <outfile>'"); return; }
    char path[512], out[MAX_PATH];
    size_t plen = (size_t)(sp - args);
    if (plen >= sizeof(path)) plen = sizeof(path) - 1;
    memcpy(path, args, plen); path[plen] = 0;
    lstrcpynA(out, sp + 1, MAX_PATH);

    uint64_t pack = get_pack();
    if (!pack) return;
    int idx = pack_find(pack, path);
    logf_("export '%s' -> idx=%d out=%s", path, idx, out);
    if (idx < 0) return;
    int ok = 0;
    uint64_t hdr = rd64_safe(pack, &ok);
    if ((uint32_t)idx >= RD32(hdr + 0x10)) { logf_("  idx range"); return; }
    uint64_t resarr = rd64_safe(pack + 0x18, &ok);
    uint64_t res = rd64_safe(resarr + (uint64_t)idx * 8, &ok);
    if (!ok || !res || !readable((const void *)res)) { logf_("  resource not loaded"); return; }
    uint32_t arch = RD32(res - 0x18);
    logf_("  res=%p arch=%u", (void *)res, arch);
    if (arch >= 0x4a) return;

    uint64_t base = (uint64_t)GetModuleHandleA(NULL);
    uint64_t rec = base + 0x3DE220ull + (uint64_t)arch * 0x28;
    uint64_t funcB = *(volatile uint64_t *)(rec + 0x20);
    uint64_t archName = *(volatile uint64_t *)(rec + 8);
    typedef void *(*newjson_fn)(void);
    void *json = ((newjson_fn)(base + 0x1FB230ull))();
    if (!json) { logf_("  new json failed"); return; }
    typedef void (*setstr_fn)(void *, const char *, const char *);
    ((setstr_fn)(base + 0x1FE080ull))(json, "archetype", (const char *)archName);
    typedef void (*fb_fn)(void *, void *, void *);
    ((fb_fn)funcB)((void *)pack, (void *)res, json);
    typedef char *(*tostr_fn)(void *);
    char *text = ((tostr_fn)(base + 0x1FB5A0ull))(json);
    logf_("  serialized -> %p", (void *)text);
    if (!text || !readable(text)) return;
    size_t len = strlen(text);
    if (len > 32 * 1024 * 1024) { logf_("  too big"); return; }
    FILE *o = NULL;
    if (fopen_s(&o, out, "wb") == 0 && o) { fwrite(text, 1, len, o); fclose(o); logf_("  wrote %u bytes", (unsigned)len); }
    else logf_("  cannot write %s", out);
}

static void cmd_apply(const char *args)
{
    const char *sp = strrchr(args, ' ');
    if (!sp) { logf_("apply: need '<asset path> <json file>'"); return; }
    char path[512], file[MAX_PATH];
    size_t plen = (size_t)(sp - args);
    if (plen >= sizeof(path)) plen = sizeof(path) - 1;
    memcpy(path, args, plen); path[plen] = 0;
    lstrcpynA(file, sp + 1, MAX_PATH);

    uint64_t pack = get_pack();
    if (!pack) return;
    int idx = pack_find(pack, path);
    logf_("apply '%s' file='%s' idx=%d", path, file, idx);
    if (idx < 0) return;
    int ok = 0;
    uint64_t hdr = rd64_safe(pack, &ok);
    uint32_t count = RD32(hdr + 0x10);
    if ((uint32_t)idx >= count) { logf_("  idx out of range"); return; }
    uint64_t resarr = rd64_safe(pack + 0x18, &ok);
    uint64_t res = rd64_safe(resarr + (uint64_t)idx * 8, &ok);
    if (!ok || !res || !readable((const void *)res)) { logf_("  resource not loaded (res=%p)", (void *)res); return; }
    uint32_t arch = RD32(res - 0x18);
    logf_("  res=%p arch=%u", (void *)res, arch);
    if (arch >= 0x4a) { logf_("  bad archetype"); return; }

    void *json = json_from_file(file);
    if (!json) { logf_("  parse failed"); return; }
    logf_("  json=%p", json);

    uint64_t base = (uint64_t)GetModuleHandleA(NULL);
    uint64_t rec = base + 0x3DE220ull + (uint64_t)arch * 0x28;
    uint64_t funcA = *(volatile uint64_t *)(rec + 0x18);
    uint64_t structSize = *(volatile uint64_t *)(rec + 0x10);
    uint64_t allocator = *(volatile uint64_t *)(pack + 0x4c8);
    logf_("  funcA=%p size=%llu alloc=%p", (void *)funcA, (unsigned long long)structSize, (void *)allocator);
    if (!funcA) return;

    uint64_t namePtr = *(volatile uint64_t *)(res - 0x10);
    logf_("  name=%s", (const char *)namePtr);

    typedef void (*pre_fn)(void *, int);
    typedef void (*fa_fn)(void *, void *, const char *, void *, void *);
    __try {
        ((pre_fn)(base + 0x1FE10ull))(allocator, 8);
    } __except (seh_filter(GetExceptionInformation())) {
        logf_("  pre-alloc fault");
    }
    int faulted = 0;
    __try {
        ((fa_fn)funcA)((void *)pack, (void *)allocator, (const char *)namePtr, (void *)res, json);
        logf_("  funcA returned");
    } __except (seh_filter(GetExceptionInformation())) {
        faulted = 1;
    }
    if (faulted) { logf_("  funcA faulted -> skip writeback"); return; }

    typedef void (*wb_fn)(void *, int);
    __try {
        ((wb_fn)(base + 0x228660ull))((void *)pack, idx);
        logf_("  writeback returned");
    } __except (seh_filter(GetExceptionInformation())) {
        logf_("  writeback faulted");
    }
}


#define OFF_PLAYER_CTRL 0x0B64838ull   // global -> controller

// 取资源在内存里的结构体地址（用引擎的 resarr：pack+0x18 指针数组）
static uint64_t res_addr(const char *path, uint64_t *out_off, uint64_t *out_size)
{
    uint64_t pack = get_pack();
    if (!pack) return 0;
    int idx = pack_find(pack, path);
    if (idx < 0) { logf_("  res_addr '%s' not found", path); return 0; }
    int ok = 0;
    uint64_t hdr = rd64_safe(pack, &ok);
    uint64_t offarr = rd64_safe(hdr + 0x28, &ok);
    uint64_t szarr = rd64_safe(hdr + 0x30, &ok);
    uint64_t off = rd64_safe(offarr + (uint64_t)idx * 8, &ok);
    uint64_t sz = rd64_safe(szarr + (uint64_t)idx * 8, &ok);
    uint64_t resarr = rd64_safe(pack + 0x18, &ok);
    uint64_t res = rd64_safe(resarr + (uint64_t)idx * 8, &ok);
    if (!ok || !res || !readable((const void *)res)) { logf_("  res_addr '%s' res null", path); return 0; }
    if (out_off) *out_off = off;
    if (out_size) *out_size = sz;
    return res;
}

// 在 [p, p+span) 中查找等于 target 的 qword，记录偏移
static int scan_ptr(uint64_t p, uint64_t span, uint64_t target, const char *tag)
{
    int hits = 0, ok = 0;
    if (!p || !readable((const void *)p)) return 0;
    for (uint64_t i = 0; i + 8 <= span; i += 8) {
        uint64_t v = rd64_safe(p + i, &ok);
        if (ok && v == target) {
            logf_("  HIT %s %p+0x%llx == %p", tag, (void *)p, (unsigned long long)i, (void *)target);
            hits++;
        }
    }
    return hits;
}

static void cmd_player(void)
{
    uint64_t base = (uint64_t)GetModuleHandleA(NULL);
    int ok = 0;
    logf_("== player == base=%p", (void *)base);

    uint64_t unit_off = 0, unit_sz = 0, leg_off = 0, leg_sz = 0;
    uint64_t unit = res_addr("assets/data/vics/units/rig_corv_cinderblock_01.json", &unit_off, &unit_sz);
    uint64_t leg = res_addr("assets/data/vics/lowers/rig_corv_cinderblock_01_lo.json", &leg_off, &leg_sz);
    uint64_t clone = res_addr("assets/data/vics/corpse_civ_tuktuk_01.json", NULL, NULL);
    logf_("unit=%p off=%llx size=%llx", (void *)unit, (unsigned long long)unit_off, (unsigned long long)unit_sz);
    logf_("leg =%p off=%llx size=%llx", (void *)leg, (unsigned long long)leg_off, (unsigned long long)leg_sz);
    logf_("clone=%p", (void *)clone);
    if (unit && readable((const void *)unit)) {
        uint64_t c0 = rd64_safe(unit + 0xC0, &ok);
        logf_("  orig unit +0xC0 -> %p", (void *)c0);
        uint64_t c8 = rd64_safe(unit + 0xC8, &ok);
        uint64_t d0 = rd64_safe(unit + 0xD0, &ok);
        uint64_t d8 = rd64_safe(unit + 0xD8, &ok);
        uint64_t e0 = rd64_safe(unit + 0xE0, &ok);
        uint64_t e8 = rd64_safe(unit + 0xE8, &ok);
        logf_("  orig unit +0xC8=%p +0xD0=%p +0xD8=%p +0xE0=%p +0xE8=%p",
              (void *)c8, (void *)d0, (void *)d8, (void *)e0, (void *)e8);
    }

    uint64_t ctrl = rd64_safe(base + OFF_PLAYER_CTRL, &ok);
    logf_("controller=%p", (void *)ctrl);
    if (!ctrl || !readable((const void *)ctrl)) { logf_("controller unreadable"); return; }
    uint64_t game = rd64_safe(ctrl + 0x40, &ok);
    logf_("game=%p", (void *)game);
    if (!game || !readable((const void *)game)) return;
    for (uint64_t o = 0x1C400; o <= 0x1C500; o += 8) {
        uint64_t v = rd64_safe(game + o, &ok);
        if (!ok) continue;
        logf_("  game+%llx = %p", (unsigned long long)o, (void *)v);
    }
    // 在 game 对象内找指向原 unit/leg 的字段
    scan_ptr(game, 0x40000, unit, "game->unit");
    scan_ptr(game, 0x40000, leg, "game->leg");

    // 对候选实体：扫描其前 0x2000 字节里是否有 leg/unit 指针
    for (uint64_t o = 0x1C400; o <= 0x1C500; o += 8) {
        uint64_t v = rd64_safe(game + o, &ok);
        if (!ok || v < 0x10000 || !readable((const void *)v)) continue;
        int h1 = scan_ptr(v, 0x2000, leg, "cand->leg");
        int h2 = scan_ptr(v, 0x2000, unit, "cand->unit");
        if (h1 || h2) logf_("  ^ candidate from game+%llx", (unsigned long long)o);
    }
}

static void cmd_entity(void)
{
    uint64_t base = (uint64_t)GetModuleHandleA(NULL);
    int ok = 0;
    logf_("== entity ==");
    uint64_t unit_off = 0, unit_sz = 0, leg_off = 0, leg_sz = 0;
    uint64_t unit = res_addr("assets/data/vics/units/rig_corv_cinderblock_01.json", &unit_off, &unit_sz);
    uint64_t leg = res_addr("assets/data/vics/lowers/rig_corv_cinderblock_01_lo.json", &leg_off, &leg_sz);
    uint64_t clone = res_addr("assets/data/vics/corpse_civ_tuktuk_01.json", NULL, NULL);
    uint64_t clone_leg = 0;
    if (clone && readable((const void *)clone)) {
        clone_leg = rd64_safe(clone + 0xC0, &ok);
    }
    logf_("orig unit=%p leg=%p clone=%p clone_leg=%p", (void *)unit, (void *)leg, (void *)clone, (void *)clone_leg);

    uint64_t ctrl = rd64_safe(base + OFF_PLAYER_CTRL, &ok);
    if (!ok || !ctrl || !readable((const void *)ctrl)) { logf_("ctrl bad"); return; }
    typedef uint64_t (*state_fn)(void *);
    uint64_t state = 0;
    __try { state = ((state_fn)(base + 0x178F50ull))((void *)ctrl); }
    __except (seh_filter(GetExceptionInformation())) { logf_("  state() fault"); return; }
    logf_("ctrl=%p state=%p", (void *)ctrl, (void *)state);
    if (!state || !readable((const void *)state)) return;
    uint32_t id = RD32(state + 0x10), handle = RD32(state + 0x14), flag = RD32(state + 0xC);
    logf_("  id=%u handle=%u flag=%u", id, handle, flag);

    uint64_t root = rd64_safe(base + OFF_RES_ROOT, &ok);
    uint64_t vec = root ? rd64_safe(root + 0x2788, &ok) : 0;
    uint64_t begin = vec ? rd64_safe(vec, &ok) : 0;
    uint64_t end = vec ? rd64_safe(vec + 8, &ok) : 0;
    logf_("root=%p vec=%p begin=%p end=%p count=%llu", (void *)root, (void *)vec,
          (void *)begin, (void *)end, (unsigned long long)((end - begin) / 16));
    if (!begin || !end || end <= begin) return;
    uint64_t n = (end - begin) / 16;
    if (id >= n) { logf_("  id out of range"); return; }
    uint32_t key = RD32(begin + (uint64_t)id * 16);
    uint64_t ent = rd64_safe(begin + (uint64_t)id * 16 + 8, &ok);
    logf_("  slot id=%u key=%u ent=%p", id, key, (void *)ent);
    if (!ok || !ent || !readable((const void *)ent)) return;

    for (uint64_t o = 0; o < 0x200; o += 8) {
        uint64_t v = rd64_safe(ent + o, &ok);
        if (!ok) continue;
        logf_("  ent+%03llx = %p", (unsigned long long)o, (void *)v);
    }
    scan_ptr(ent, 0x2000, leg, "ent->origleg");
    scan_ptr(ent, 0x2000, clone_leg, "ent->cloneleg");
    scan_ptr(ent, 0x2000, unit, "ent->origunit");
    scan_ptr(ent, 0x2000, clone, "ent->cloneunit");
}

static void process_cmd_line(const char *line)
{
    while (*line == ' ' || *line == '\t') line++;
    if (!*line) return;
    logf_("cmd: %s", line);
    if (_stricmp(line, "probe") == 0) cmd_probe();
    else if (_stricmp(line, "player") == 0) cmd_player();
    else if (_stricmp(line, "entity") == 0) cmd_entity();
    else if (_strnicmp(line, "find ", 5) == 0) cmd_find(line + 5);
    else if (_strnicmp(line, "dump ", 5) == 0) cmd_dump(line + 5);
    else if (_strnicmp(line, "export ", 7) == 0) cmd_export(line + 7);
    else if (_strnicmp(line, "apply ", 6) == 0) cmd_apply(line + 6);
    else if (_strnicmp(line, "parse ", 6) == 0) cmd_parse(line + 6);
    else logf_("unknown cmd");
}

static DWORD WINAPI worker(LPVOID param)
{
    (void)param;
    char tmp[MAX_PATH], cmd[MAX_PATH], done[MAX_PATH];
    DWORD n = GetTempPathA(MAX_PATH, tmp);
    if (n == 0 || n >= MAX_PATH) return 0;
    lstrcpyA(cmd, tmp); lstrcatA(cmd, "bk_cmd.txt");
    lstrcpyA(done, tmp); lstrcatA(done, "bk_cmd.done.txt");
    logf_("worker started, cmd file %s", cmd);
    for (;;) {
        Sleep(400);
        if (GetFileAttributesA(cmd) == INVALID_FILE_ATTRIBUTES) continue;
        FILE *f = NULL;
        if (fopen_s(&f, cmd, "rb") != 0 || !f) continue;
        static char buf[4096];
        size_t rd = fread(buf, 1, sizeof(buf) - 1, f);
        fclose(f);
        buf[rd] = 0;
        DeleteFileA(cmd);
        // split lines
        char *p = buf;
        while (p && *p) {
            char *e = p;
            while (*e && *e != '\r' && *e != '\n') e++;
            char save = *e;
            *e = 0;
            process_cmd_line(p);
            if (!save) break;
            p = e + 1;
            while (*p == '\r' || *p == '\n') p++;
        }
        MoveFileExA(cmd, done, MOVEFILE_REPLACE_EXISTING);
    }
    return 0;
}

static void write_marker(const char *tag)
{
    char path[MAX_PATH];
    DWORD n = GetTempPathA(MAX_PATH, path);
    if (n == 0 || n >= MAX_PATH) return;
    lstrcatA(path, "bk_bridge_loaded.txt");
    FILE *f = NULL;
    if (fopen_s(&f, path, "a") == 0 && f) {
        SYSTEMTIME st;
        GetLocalTime(&st);
        fprintf(f, "%s pid=%lu time=%04d-%02d-%02d %02d:%02d:%02d\n",
                tag, (unsigned long)GetCurrentProcessId(),
                st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond);
        fclose(f);
    }
}

BOOL WINAPI DllMain(HINSTANCE hinst, DWORD reason, LPVOID reserved)
{
    (void)hinst; (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        write_marker("attach");
        InitializeCriticalSection(&g_cs);
        log_open();
    }
    return TRUE;
}

__declspec(dllexport) int luaopen_vs_bridge(void *L)
{
    (void)L;
    write_marker("luaopen");
    static int started = 0;
    if (!started) { started = 1; CreateThread(NULL, 0, worker, NULL, 0, NULL); }
    return 0;
}

__declspec(dllexport) int luaopen_vb(void *L)
{
    (void)L;
    write_marker("luaopen_vb");
    static int started = 0;
    if (!started) { started = 1; CreateThread(NULL, 0, worker, NULL, 0, NULL); }
    return 0;
}
