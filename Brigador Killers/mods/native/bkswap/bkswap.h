/*
 * bkswap.h - Brigador Killers 运行时载具热切换 C ABI
 *
 * 用法（mod / 其它 DLL）：
 *   HMODULE h = LoadLibraryA("C:/bk/bkswap3.dll");
 *   // 或游戏内 Lua 控制台：
 *   //   local f,e=package.loadlib("C:/bk/bkswap3.dll","luaopen_bkswap")
 *   //   if f then f() end
 *
 * 线程约束：除 bks_auto_state / bks_last_error 外，全部必须在游戏主线程调用。
 * 自动接管：bks_auto_enable() 后在每帧开头检测玩家 unit 指针变化；
 *           变化瞬间把「将要上的原型载具」的 MECH+LEG 拷进 dummy 槽，
 *           并把玩家 mech+0x258 指回 dummy —— 原型数据不再被玩家侧修改污染。
 */
#ifndef BKSWAP_H
#define BKSWAP_H

#ifdef __cplusplus
extern "C" {
#endif

/* 开启自动接管（在玩家换载具的瞬间自动生成 dummy）。成功返回 1。 */
int bks_auto_enable(void);

/* 关闭自动接管并还原 SDL_PumpEvents 钩子。 */
int bks_auto_disable(void);

/* 当前是否开启自动接管。 */
int bks_auto_state(void);

/* 玩家 Mech 对象地址（0 = 当前无法解析）。 */
unsigned long long bks_player_mech(void);

/* 玩家当前载具 unit 资源地址（即 mech+0x258）。 */
unsigned long long bks_player_unit(void);

/* dummy 槽（默认 assets/data/vics/corpse_civ_tuktuk_01.json）的 MECH 地址。 */
unsigned long long bks_dummy_unit(void);

/* 按 pack 内路径取「已加载」资源的运行时地址（0 = 未加载/不存在）。 */
unsigned long long bks_asset_addr(const char *pack_path);

/*
 * 手动热切换：把 pack_path 对应载具数据灌入 dummy 并让玩家重生为它
 * （等价于原 go 命令：morph + copy + respawn）。成功返回 1。
 */
int bks_swap(const char *pack_path);

/* 最近一次失败原因（静态缓冲，不要释放）。 */
const char *bks_last_error(void);

/* 接口版本字符串。 */
const char *bks_version(void);

/*
 * 背包条件速度加成：
 * 当玩家背包（mech+0x238 → +0x250 容器）里存在 item_path 对应物品时，
 * 把玩家 dummy 的三向最大速度/加速度改为「换载具时的原始值 × multiplier」。
 * 只改 dummy LEG，不影响原型与敌人。成功返回 1。
 * 例：bks_item_speed_mod("assets/data/pickups/kit/pkp_comp_actuator_small.json", 2.0f);
 */
int bks_item_speed_mod(const char *item_path, float multiplier);

/* 关闭速度加成并还原 dummy 的原始速度。 */
int bks_item_speed_mod_off(void);

/* 0=关闭, 1=已开启（当前背包无该物品）, 2=已开启且加成生效中。 */
int bks_item_speed_mod_state(void);

#ifdef __cplusplus
}
#endif

#endif /* BKSWAP_H */
