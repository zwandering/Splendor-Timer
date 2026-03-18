#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宝石商人计时器 — 围棋日本规则 (主时间 + 读秒制)

用法:
    python timer.py [玩家人数] [选项]

示例:
    python timer.py                          # 2位玩家，默认设置
    python timer.py 4                        # 4位玩家
    python timer.py 4 --main-time 300        # 主时间5分钟
    python timer.py 3 --byoyomi 60 --periods 5

按键:
    空格   — 结束当前玩家回合，切换到下一位
    Q      — 退出程序
"""

import sys
import time
import argparse

# ── 跨平台键盘支持 ────────────────────────────────────────────────────────────
try:
    import msvcrt
    IS_WINDOWS = True
    # 启用 Windows 终端 VT/ANSI 支持
    import ctypes
    _k32 = ctypes.windll.kernel32
    _k32.SetConsoleMode(_k32.GetStdHandle(-11), 0x0007)
except (ImportError, AttributeError):
    IS_WINDOWS = False
    import tty
    import termios
    import select


def read_key():
    """非阻塞读取按键，无输入返回 None。"""
    if IS_WINDOWS:
        if msvcrt.kbhit():
            return msvcrt.getch()
    else:
        r, _, _ = select.select([sys.stdin], [], [], 0)
        if r:
            return sys.stdin.read(1).encode("utf-8", errors="ignore")
    return None


# ── ANSI 颜色工具 ─────────────────────────────────────────────────────────────
def _c(code, text):
    return f"\033[{code}m{text}\033[0m"

def bold(t):    return _c("1", t)
def red(t):     return _c("31", t)
def green(t):   return _c("32", t)
def yellow(t):  return _c("33", t)
def cyan(t):    return _c("36", t)
def white(t):   return _c("37", t)

CURSOR_HOME   = "\033[H"
CLEAR_TO_END  = "\033[J"


# ── 玩家计时器 ─────────────────────────────────────────────────────────────────
class PlayerTimer:
    """
    围棋日本规则：
      · 主时间用完后进入读秒阶段
      · 读秒阶段：每回合有固定时间（byoyomi_time），在时间内落子则读秒重置；
        否则消耗一个读秒次数，读完所有次数即判负
    """

    def __init__(self, pid: int, main_time: float, byoyomi_time: float, byoyomi_periods: int):
        self.pid             = pid
        self.main_time       = float(main_time)
        self.byoyomi_time    = float(byoyomi_time)
        self.periods_left    = byoyomi_periods
        self.period_remain   = float(byoyomi_time)   # 当前读秒剩余
        self.in_byoyomi      = False
        self.timed_out       = False
        self.turns           = 0                     # 已完成回合数

    def tick(self, dt: float) -> bool:
        """推进 dt 秒；返回 True 表示刚刚超时。"""
        if self.timed_out:
            return False

        if not self.in_byoyomi:
            self.main_time -= dt
            if self.main_time <= 0.0:
                self.main_time  = 0.0
                self.in_byoyomi = True
                self.period_remain = self.byoyomi_time
        else:
            self.period_remain -= dt
            if self.period_remain <= 0.0:
                self.periods_left -= 1
                if self.periods_left <= 0:
                    self.periods_left  = 0
                    self.timed_out     = True
                    return True
                self.period_remain = self.byoyomi_time

        return False

    def end_turn(self):
        """玩家按空格结束回合：读秒阶段重置当前读秒时间。"""
        self.turns += 1
        if self.in_byoyomi and not self.timed_out:
            self.period_remain = self.byoyomi_time

    def time_str(self) -> str:
        """格式化当前时间，固定宽度。"""
        PAD = " " * 4
        if self.timed_out:
            return red(bold("  超  时  ")) + PAD
        if not self.in_byoyomi:
            m   = int(self.main_time) // 60
            s   = int(self.main_time) % 60
            col = yellow if self.main_time < 30 else white
            return col(bold(f"{m:02d}:{s:02d}")) + PAD
        else:
            t   = max(int(self.period_remain) + 1, 0)
            col = red if t <= 10 else yellow
            return col(bold(f"读秒 {t:2d}s")) + f"  ({self.periods_left}次剩余){PAD}"


# ── 渲染 ──────────────────────────────────────────────────────────────────────
_WIDE = 56   # 显示宽度（字符）

def render(players: list, cur: int):
    buf = [CURSOR_HOME + CLEAR_TO_END]
    buf.append(cyan(bold("═" * _WIDE)))
    buf.append(cyan(bold("      宝石商人计时器  ⟨ 围棋读秒规则 ⟩      ")))
    buf.append(cyan(bold("═" * _WIDE)))
    buf.append("")

    for i, p in enumerate(players):
        if p.timed_out:
            arrow  = "  "
            marker = red("[超时]")
        elif i == cur:
            arrow  = green("▶ ")
            marker = green(bold("[行动中]"))
        else:
            arrow  = "  "
            marker = ""

        buf.append(f"  {arrow}{bold(f'玩家 {p.pid}')}  {p.time_str()} {marker}")

    buf.append("")
    buf.append(bold("─" * _WIDE))
    buf.append(f"  按 {bold('空格')} 结束当前回合    按 {bold('P')} 暂停/恢复    按 {bold('Q')} 退出")
    buf.append(cyan(bold("═" * _WIDE)))
    buf.append("")

    sys.stdout.write("\n".join(buf))
    sys.stdout.flush()


# ── 主逻辑 ────────────────────────────────────────────────────────────────────
def next_active(players: list, from_idx: int) -> int:
    """从 from_idx 出发顺序查找下一个未超时的玩家下标。"""
    n = len(players)
    for offset in range(1, n + 1):
        idx = (from_idx + offset) % n
        if not players[idx].timed_out:
            return idx
    return -1  # 全部超时


def render_paused(players: list, cur: int):
    """在暂停状态下渲染，顶部显示醒目的暂停提示。"""
    buf = [CURSOR_HOME + CLEAR_TO_END]
    buf.append(yellow(bold("═" * _WIDE)))
    buf.append(yellow(bold("          ⏸  已暂停 — 按 P 继续          ")))
    buf.append(yellow(bold("═" * _WIDE)))
    buf.append("")

    for i, p in enumerate(players):
        if p.timed_out:
            arrow  = "  "
            marker = red("[超时]")
        elif i == cur:
            arrow  = yellow("▶ ")
            marker = yellow(bold("[等待中]"))
        else:
            arrow  = "  "
            marker = ""

        buf.append(f"  {arrow}{bold(f'玩家 {p.pid}')}  {p.time_str()} {marker}")

    buf.append("")
    buf.append(bold("─" * _WIDE))
    buf.append(f"  按 {bold('P')} 继续计时    按 {bold('Q')} 退出")
    buf.append(yellow(bold("═" * _WIDE)))
    buf.append("")

    sys.stdout.write("\n".join(buf))
    sys.stdout.flush()


def run(players: list):
    cur        = 0
    paused     = False
    last_tick  = time.perf_counter()

    # Unix：切换终端为 cbreak 模式（不等 Enter）
    if not IS_WINDOWS:
        fd           = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        tty.setcbreak(fd)

    # 清屏
    sys.stdout.write("\033[2J" + CURSOR_HOME)
    sys.stdout.flush()

    try:
        while True:
            now = time.perf_counter()
            dt  = now - last_tick
            last_tick = now

            p = players[cur]

            if paused:
                render_paused(players, cur)
                key = read_key()
                if key in (b"p", b"P"):
                    paused    = False
                    last_tick = time.perf_counter()   # 跳过暂停期间的时间
                elif key in (b"q", b"Q", b"\x1b"):
                    break
                time.sleep(0.05)
                continue

            if not p.timed_out:
                just_out = p.tick(dt)
                if just_out:
                    render(players, cur)
                    time.sleep(1.2)
                    nxt = next_active(players, cur)
                    if nxt == -1:
                        break   # 全员超时
                    cur       = nxt
                    last_tick = time.perf_counter()
                    continue

            render(players, cur)

            key = read_key()
            if key == b" ":
                players[cur].end_turn()
                nxt = next_active(players, cur)
                if nxt == -1:
                    break
                cur       = nxt
                last_tick = time.perf_counter()
            elif key in (b"p", b"P"):
                paused = True
            elif key in (b"q", b"Q", b"\x1b"):
                break

            time.sleep(0.05)   # ~20 FPS

    finally:
        if not IS_WINDOWS:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    # 结束画面
    render(players, cur)
    print(f"\n  {cyan(bold('游戏结束，感谢使用宝石商人计时器！'))}\n")


# ── 入口 ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="宝石商人计时器 — 围棋读秒规则",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "players", nargs="?", type=int, default=2,
        metavar="玩家人数",
        help="参与游戏的玩家数量 (默认: 2，范围: 1~10)",
    )
    parser.add_argument(
        "--main-time", type=int, default=180,
        metavar="秒",
        help="每位玩家主时间，单位秒 (默认: 180 = 3分钟)",
    )
    parser.add_argument(
        "--byoyomi", type=int, default=30,
        metavar="秒",
        help="每次读秒时间，单位秒 (默认: 30)",
    )
    parser.add_argument(
        "--periods", type=int, default=3,
        metavar="次",
        help="读秒次数 (默认: 3)",
    )

    args = parser.parse_args()

    if not (1 <= args.players <= 10):
        parser.error("玩家人数必须在 1~10 之间")
    if args.main_time < 0:
        parser.error("主时间不能为负数")
    if args.byoyomi < 1:
        parser.error("读秒时间至少 1 秒")
    if args.periods < 1:
        parser.error("读秒次数至少 1 次")

    print(f"\n  {cyan(bold('宝石商人计时器'))}")
    print(f"  玩家人数：{args.players}")
    print(f"  主时间：  {args.main_time // 60}分{args.main_time % 60:02d}秒")
    print(f"  读秒：    {args.byoyomi}秒 × {args.periods}次")
    print(f"\n  按 Enter 开始…")
    input()

    players = [
        PlayerTimer(i + 1, args.main_time, args.byoyomi, args.periods)
        for i in range(args.players)
    ]
    run(players)


if __name__ == "__main__":
    main()
