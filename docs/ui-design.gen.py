#!/usr/bin/env python3
"""生成 docs/ui-design.excalidraw —— 吾日三省 App 界面设计稿。"""
import json, os

ELS, _n, _grp = [], [0], [None]

CREAM, PAPER, WHITE = "#F2EDE1", "#FBF8F0", "#ffffff"
INK, INK2, INK3 = "#14120F", "#1C1A17", "#26241F"
GOLD, GOLD_L, GOLD_D = "#C8992F", "#E8D4A6", "#8C6A16"
GREEN, GREEN_L, GREY = "#3E7A5E", "#CFE0D5", "#8A8477"
RED, AMBER, LINE = "#B5432F", "#B98A2E", "#E4DDCC"
T1, T2, T3 = "#14120F", "#6E685C", "#A9A296"
TR = "transparent"


def nid():
    _n[0] += 1
    return "e%04d" % _n[0]


def base():
    return dict(angle=0, fillStyle="solid", strokeWidth=1, strokeStyle="solid",
                roughness=0, opacity=100, groupIds=([_grp[0]] if _grp[0] else []),
                frameId=None, seed=_n[0] * 7 + 13, version=1, versionNonce=_n[0] * 31 + 7,
                isDeleted=False, boundElements=None, updated=1, link=None, locked=False)


def rect(x, y, w, h, bg=TR, stroke=TR, r=10, sw=1, dashed=False):
    e = base()
    e.update(id=nid(), type="rectangle", x=x, y=y, width=w, height=h,
             strokeColor=stroke, backgroundColor=bg, strokeWidth=sw,
             strokeStyle="dashed" if dashed else "solid",
             roundness=({"type": 3} if r else None))
    if bg == TR:
        e["fillStyle"] = "solid"
    ELS.append(e)
    return e


def ellipse(x, y, w, h, bg=TR, stroke=TR, sw=1):
    e = base()
    e.update(id=nid(), type="ellipse", x=x, y=y, width=w, height=h,
             strokeColor=stroke, backgroundColor=bg, strokeWidth=sw, roundness=None)
    ELS.append(e)
    return e


def line(x1, y1, x2, y2, color=LINE, sw=1):
    e = base()
    e.update(id=nid(), type="line", x=x1, y=y1, width=x2 - x1, height=y2 - y1,
             strokeColor=color, backgroundColor=TR, strokeWidth=sw, roundness=None,
             points=[[0, 0], [x2 - x1, y2 - y1]], lastCommittedPoint=None,
             startBinding=None, endBinding=None, startArrowhead=None, endArrowhead=None)
    ELS.append(e)
    return e


def arrow(x1, y1, x2, y2, color=GREY, sw=2):
    e = base()
    e.update(id=nid(), type="arrow", x=x1, y=y1, width=x2 - x1, height=y2 - y1,
             strokeColor=color, backgroundColor=TR, strokeWidth=sw,
             roundness={"type": 2}, points=[[0, 0], [x2 - x1, y2 - y1]],
             lastCommittedPoint=None, startBinding=None, endBinding=None,
             startArrowhead=None, endArrowhead="arrow")
    ELS.append(e)
    return e


def tw(s, size):
    """粗略估算文本宽度：中日韩全宽，ASCII 约 0.58 倍。"""
    w = 0.0
    for ch in s:
        w += size * (1.0 if ord(ch) > 0x2E80 else 0.58)
    return w


def text(x, y, s, size=14, color=T1, align="left", font=2, bold_gap=0):
    w = tw(s, size) + bold_gap
    h = size * 1.25
    tx = x if align == "left" else (x - w / 2 if align == "center" else x - w)
    e = base()
    e.update(id=nid(), type="text", x=tx, y=y, width=w, height=h,
             strokeColor=color, backgroundColor=TR, roundness=None,
             text=s, originalText=s, fontSize=size, fontFamily=font,
             textAlign="left", verticalAlign="top", containerId=None,
             lineHeight=1.25, baseline=size)
    ELS.append(e)
    return e


def group(name):
    _grp[0] = name


W, H = 360, 780          # 手机画框尺寸
COL, ROW = 470, 900      # 画框间距


# ---------------------------------------------------------------- 通用组件
def frame(ox, oy, bg=CREAM):
    rect(ox - 8, oy - 8, W + 16, H + 16, TR, LINE, 26)
    rect(ox, oy, W, H, bg, TR, 22)


def wrap(s, size, maxw):
    """按估算宽度把说明文字折行，避免撞到相邻画框的图注。"""
    lines, cur = [], ""
    for ch in s:
        if tw(cur + ch, size) > maxw and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def caption(ox, oy, idx, title, desc):
    text(ox, oy + H + 26, "%02d  %s" % (idx, title), 17, T1)
    for i, ln in enumerate(wrap(desc, 12, W)):
        text(ox, oy + H + 52 + i * 20, ln, 12, T2)


def tabbar(ox, oy, active=0, tabs=("今日", "资料", "知识点", "统计")):
    ty = oy + H - 64
    rect(ox, ty, W, 64, INK, TR, 0)
    rect(ox, ty, W, 22, INK, TR, 0)
    for i, t in enumerate(tabs):
        cx = ox + W / 8 + i * W / 4
        c = GOLD if i == active else "#7C766A"
        rect(cx - 9, ty + 14, 18, 16, TR, c, 3)
        text(cx, ty + 36, t, 11, c, "center")
    rect(ox + W / 2 - 55, oy + H - 12, 110, 4, "#C9C4B8", TR, 2)


def ring(cx, cy, r, val, color):
    ellipse(cx - r, cy - r, r * 2, r * 2, TR, LINE, 2)
    ellipse(cx - r + 2, cy - r + 2, r * 2 - 4, r * 2 - 4, TR, color, 2)
    text(cx, cy - 7, str(val), 12, T1, "center")


def chip(x, y, s, fg, bg, size=11, pad=8, h=20):
    w = tw(s, size) + pad * 2
    rect(x, y, w, h, bg, TR, 6)
    text(x + w / 2, y + (h - size * 1.25) / 2 + 1, s, size, fg, "center")
    return w


def sect(ox, y, s):
    text(ox + 24, y, s, 13, T2)


# ---------------------------------------------------------------- 01 今日
def screen_today(ox, oy):
    group("s-today")
    frame(ox, oy)
    text(ox + 24, oy + 26, "2026年7月28日 · 星期二", 11, T3)
    text(ox + 24, oy + 46, "吾日三省", 30, T1)
    ellipse(ox + W - 66, oy + 40, 42, 42, "#7E8C52", TR)
    text(ox + W - 45, oy + 52, "李", 15, WHITE, "center")

    # 数据条
    rect(ox + 24, oy + 108, 312, 84, INK, TR, 18)
    for i, (v, k, c) in enumerate([("12", "连续天数", GOLD), ("78%", "正确率", WHITE),
                                   ("147", "知识点", WHITE)]):
        cx = ox + 24 + 52 + i * 104
        text(cx, oy + 126, v, 24, c, "center")
        text(cx, oy + 162, k, 11, "#8B857A", "center")
        if i:
            line(ox + 24 + i * 104, oy + 128, ox + 24 + i * 104, oy + 172, "#3A3630")

    # 一周打卡
    rect(ox + 24, oy + 204, 312, 76, WHITE, TR, 16)
    for i, d in enumerate("一二三四五六日"):
        x = ox + 38 + i * 42
        done = i < 5
        rect(x, oy + 216, 32, 32, GOLD if done else "#E8E2D4", TR, 8)
        text(x + 16, oy + 224, "✓" if done else d, 14 if done else 12,
             WHITE if done else T3, "center")
        text(x + 16, oy + 254, d if done else "·", 10, T3, "center")

    # 主 CTA
    rect(ox + 24, oy + 292, 312, 88, INK, TR, 18)
    rect(ox + 44, oy + 312, 48, 48, GOLD, TR, 12)
    text(ox + 68, oy + 326, "▶", 15, WHITE, "center")
    text(ox + 106, oy + 316, "开始今日复习", 17, WHITE)
    text(ox + 106, oy + 344, "3 个知识点待复习 · 约 4 分钟", 11, "#8B857A")
    text(ox + 316, oy + 328, "›", 18, "#6E685C")

    sect(ox, oy + 396, "复习队列")
    rows = [(31, RED, "用户增长", "今日到期", RED, "AARRR 模型各阶段指标定义"),
            (42, AMBER, "产品管理", "今日到期", RED, "OKR 与 KPI 的核心区别"),
            (68, GOLD, "数据分析", "今日到期", RED, "SQL 窗口函数应用场景"),
            (55, AMBER, "财务知识", "明日到期", AMBER, "现金流量表三大活动分类"),
            (77, GREEN, "机器学习", "3天后", GREEN, "过拟合的识别与正则化方法")]
    for i, (v, rc, cat, bd, bc, ttl) in enumerate(rows):
        y = oy + 420 + i * 60
        rect(ox + 24, y, 312, 54, WHITE, TR, 14)
        ring(ox + 52, y + 27, 15, v, rc)
        text(ox + 78, y + 9, cat, 10, T3)
        chip(ox + 78 + tw(cat, 10) + 6, y + 6, bd, bc, "#F6EFE4", 9, 5, 15)
        text(ox + 78, y + 26, ttl, 13, T1)
        text(ox + 318, y + 18, "›", 14, T3)

    tabbar(ox, oy, 0)
    caption(ox, oy, 1, "今日 · 首页",
            "打卡数据 + 单一主行动（开始复习）+ 按到期日排序的复习队列；左侧环形数字为掌握度。")


# ---------------------------------------------------------------- 02 资料库
def screen_materials(ox, oy):
    group("s-materials")
    frame(ox, oy)
    text(ox + 24, oy + 26, "M A T E R I A L S", 10, T3)
    text(ox + 24, oy + 48, "资料库", 30, T1)
    text(ox + W - 24, oy + 60, "6 份资料", 12, T2, "right")

    rect(ox + 24, oy + 104, 312, 158, PAPER, T3, 16, dashed=True)
    rect(ox + W / 2 - 24, oy + 124, 48, 48, INK, TR, 12)
    text(ox + W / 2, oy + 138, "⬆", 16, WHITE, "center")
    text(ox + W / 2, oy + 184, "点击上传资料", 16, T1, "center")
    text(ox + W / 2, oy + 208, "PDF · Markdown · TXT · 图片", 11, T2, "center")
    rect(ox + W / 2 - 46, oy + 228, 92, 30, INK, TR, 15)
    text(ox + W / 2, oy + 236, "选择文件", 12, WHITE, "center")

    files = [("产品经理必备方法论.pdf", "产品管理", "#F6EADB", "2.4 MB", "34 知识点", GREEN),
             ("SQL高级查询技巧.md", "数据分析", "#E2EFE7", "68 KB", "22 知识点", GREEN),
             ("用户增长黑客指南.pdf", "用户增长", "#EDE7F5", "5.1 MB", "41 知识点", GREEN),
             ("机器学习基础概念梳理.txt", "机器学习", "#E3EAF4", "124 KB", "28 知识点", GREEN),
             ("财务报表分析实战.pdf", "财务知识", "#F7E3E3", "3.7 MB", "解析中…", GOLD),
             ("项目管理PMP知识体系.png", "项目管理", "#EFEAD8", "1.2 MB", "19 知识点", GREEN)]
    for i, (fn, cat, cbg, size, kp, kc) in enumerate(files):
        y = oy + 276 + i * 66
        if y + 58 > oy + H - 70:
            break
        rect(ox + 24, y, 312, 58, WHITE, TR, 14)
        rect(ox + 36, y + 13, 32, 32, cbg, TR, 8)
        text(ox + 78, y + 12, fn, 13, T1)
        cw = chip(ox + 78, y + 32, cat, T2, cbg, 9, 5, 16)
        text(ox + 78 + cw + 8, y + 34, size, 10, T3)
        text(ox + 78 + cw + 8 + tw(size, 10) + 10, y + 34, kp, 10, kc)
        text(ox + 318, y + 20, "›", 14, T3)

    tabbar(ox, oy, 1)
    caption(ox, oy, 2, "资料库",
            "上传区常驻顶部；每份资料显示分类、体积、已提取知识点数与解析状态（解析中可重试）。")


# ---------------------------------------------------------------- 03 知识点
def screen_knowledge(ox, oy):
    group("s-knowledge")
    frame(ox, oy)
    text(ox + 24, oy + 26, "K N O W L E D G E", 10, T3)
    text(ox + 24, oy + 48, "知识点", 30, T1)
    text(ox + W - 24, oy + 60, "147 条", 12, T2, "right")

    rect(ox + 24, oy + 104, 312, 38, WHITE, TR, 12)
    text(ox + 40, oy + 114, "🔍  搜索知识点 / 资料", 12, T3)

    for i, (s, act) in enumerate([("全部", True), ("薄弱", False),
                                  ("待复习", False), ("已掌握", False)]):
        chip(ox + 24 + i * 68, oy + 154, s, WHITE if act else T2,
             INK if act else "#E8E2D4", 11, 12, 26)

    # 掌握度分布
    rect(ox + 24, oy + 194, 312, 88, WHITE, TR, 16)
    text(ox + 40, oy + 208, "掌握度分布", 13, T1)
    segs = [("薄弱", 32, RED), ("巩固中", 71, GOLD), ("已掌握", 44, GREEN)]
    tot = sum(s[1] for s in segs)
    x = ox + 40
    for nm, v, c in segs:
        w = 280 * v / tot
        rect(x, oy + 232, w - 2, 10, c, TR, 5)
        x += w
    x = ox + 40
    for nm, v, c in segs:
        rect(x, oy + 254, 8, 8, c, TR, 4)
        text(x + 13, oy + 252, "%s %d" % (nm, v), 10, T2)
        x += 94

    items = [("AARRR 模型各阶段指标定义", "用户增长", 31, RED, "用户增长黑客指南.pdf"),
             ("OKR 与 KPI 的核心区别", "产品管理", 42, AMBER, "产品经理必备方法论.pdf"),
             ("SQL 窗口函数应用场景", "数据分析", 68, GOLD, "SQL高级查询技巧.md"),
             ("过拟合的识别与正则化方法", "机器学习", 77, GREEN, "机器学习基础概念梳理.txt"),
             ("现金流量表三大活动分类", "财务知识", 55, AMBER, "财务报表分析实战.pdf"),
             ("关键路径与浮动时间", "项目管理", 88, GREEN, "项目管理PMP知识体系.png")]
    sect(ox, oy + 296, "全部知识点")
    for i, (ttl, cat, v, c, src) in enumerate(items):
        y = oy + 320 + i * 66
        if y + 58 > oy + H - 70:
            break
        rect(ox + 24, y, 312, 58, WHITE, TR, 14)
        ring(ox + 52, y + 29, 16, v, c)
        text(ox + 80, y + 11, ttl, 13, T1)
        cw = chip(ox + 80, y + 32, cat, T2, "#F1EADC", 9, 5, 16)
        text(ox + 80 + cw + 8, y + 34, "来自 " + src, 9, T3)
        text(ox + 318, y + 20, "›", 14, T3)

    tabbar(ox, oy, 2)
    caption(ox, oy, 3, "知识点",
            "按掌握度筛选与检索；每条知识点可溯源到原始资料，支持编辑、合并、删除。")


# ---------------------------------------------------------------- 04 统计
def screen_stats(ox, oy):
    group("s-stats")
    frame(ox, oy)
    text(ox + 24, oy + 26, "A N A L Y T I C S", 10, T3)
    text(ox + 24, oy + 48, "统计", 30, T1)

    cards = [("累计复习", "347", "题", WHITE), ("平均正确率", "78", "%", GOLD),
             ("连续打卡", "12", "天", GOLD), ("知识点总数", "147", "个", WHITE)]
    for i, (k, v, u, c) in enumerate(cards):
        x = ox + 24 + (i % 2) * 160
        y = oy + 100 + (i // 2) * 100
        rect(x, y, 152, 88, INK, TR, 16)
        text(x + 16, y + 14, k, 10, "#8B857A")
        text(x + 16, y + 38, v, 28, c)
        text(x + 16 + tw(v, 28) + 4, y + 54, u, 11, "#8B857A")

    # 本周答题
    rect(ox + 24, oy + 308, 312, 160, WHITE, TR, 16)
    text(ox + 40, oy + 322, "本周答题", 13, T1)
    data = [(9, 7), (7, 6), (12, 10), (5, 2), (14, 12), (1, 0), (1, 0)]
    mx = 14
    for i, (tot, ok) in enumerate(data):
        x = ox + 44 + i * 40
        ht = 78 * tot / mx
        rect(x, oy + 428 - ht, 30, ht, "#E7E0CF", TR, 4)
        hk = 78 * ok / mx
        rect(x, oy + 428 - hk, 30, hk, GREEN, TR, 4)
        text(x + 15, oy + 434, "一二三四五六日"[i], 10, T3, "center")
    rect(ox + 44, oy + 452, 8, 8, "#E7E0CF", TR, 2)
    text(ox + 57, oy + 450, "总题数", 10, T2)
    rect(ox + 112, oy + 452, 8, 8, GREEN, TR, 2)
    text(ox + 125, oy + 450, "答对数", 10, T2)

    # 本月打卡热力图
    rect(ox + 24, oy + 482, 312, 190, WHITE, TR, 16)
    text(ox + 40, oy + 496, "本月打卡", 13, T1)
    lv = [3, 1, 3, 1, 2, 3, 0, 3, 0, 2, 3, 1, 3, 1, 2, 3, 2, 3, 1, 3, 0, 1, 3, 1, 3, 1, 2, 3]
    col = {0: "#EDE7D8", 1: "#E5D3AC", 2: "#DCBB78", 3: GOLD}
    for i, v in enumerate(lv):
        x = ox + 42 + (i % 7) * 40
        y = oy + 522 + (i // 7) * 36
        rect(x, y, 32, 32, col[v], TR, 6)
    text(ox + 316, oy + 496, "颜色越深 = 当日复习越多", 9, T3, "right")

    tabbar(ox, oy, 3)
    caption(ox, oy, 4, "统计",
            "四张核心指标卡 + 本周答题量/正确数对比 + 当月打卡热力图，反馈坚持度而非排名。")


# ---------------------------------------------------------------- 05 单选题
def quiz_header(ox, oy, cur, total, timer, prog):
    text(ox + 24, oy + 30, "‹", 20, "#B8B2A6")
    rect(ox + 48, oy + 38, 200, 4, "#3A3630", TR, 2)
    rect(ox + 48, oy + 38, 200 * prog, 4, GOLD, TR, 2)
    text(ox + W - 24, oy + 30, "%d/%d   %s" % (cur, total, timer), 12, "#B8B2A6", "right")


def screen_quiz(ox, oy):
    group("s-quiz")
    frame(ox, oy, INK)
    quiz_header(ox, oy, 1, 3, "0:05", 1 / 3)
    chip(ox + 24, oy + 66, "用户增长", GOLD, "#3A2F14", 11, 9, 22)
    text(ox + 24 + tw("用户增长", 11) + 30, oy + 70, "单选题", 11, "#8B857A")

    text(ox + 24, oy + 108, "上级问你「激活率为什么下降了", 19, WHITE)
    text(ox + 24, oy + 138, "8%」，你首先应该做什么？", 19, WHITE)

    opts = [("A", "先看获客渠道质量变化"), ("B", "直接看激活路径漏斗"),
            ("C", "先确认指标定义是否一致"), ("D", "对比竞品的激活率")]
    for i, (k, s) in enumerate(opts):
        y = oy + 194 + i * 74
        rect(ox + 24, y, 312, 62, INK3, TR, 14)
        ellipse(ox + 40, y + 19, 24, 24, TR, "#5A5449", 1)
        text(ox + 52, y + 25, k, 11, "#8B857A", "center")
        text(ox + 76, y + 22, s, 14, "#EDE9E0")

    text(ox + W / 2, oy + 508, "选择后立即判分，自动进入下一题", 11, "#6E685C", "center")
    rect(ox + 24, oy + 548, 312, 1, "#2A2823", TR, 0)
    text(ox + 24, oy + 566, "本轮共 3 题 · 全部为高频真实场景提问", 11, "#6E685C")
    caption(ox, oy, 5, "答题 · 客观题",
            "深色沉浸模式，一屏一题；题干模拟上级/客户/面试官口吻，点选即判分。")


# ---------------------------------------------------------------- 06 客观题反馈
def screen_feedback(ox, oy):
    group("s-feedback")
    frame(ox, oy, INK)
    quiz_header(ox, oy, 1, 3, "0:12", 1 / 3)
    chip(ox + 24, oy + 66, "用户增长", GOLD, "#3A2F14", 11, 9, 22)
    text(ox + 24 + tw("用户增长", 11) + 30, oy + 70, "单选题", 11, "#8B857A")
    text(ox + 24, oy + 108, "上级问你「激活率为什么下降了", 19, WHITE)
    text(ox + 24, oy + 138, "8%」，你首先应该做什么？", 19, WHITE)

    opts = [("A", "先看获客渠道质量变化", None), ("B", "直接看激活路径漏斗", "wrong"),
            ("C", "先确认指标定义是否一致", "right"), ("D", "对比竞品的激活率", None)]
    for i, (k, s, st) in enumerate(opts):
        y = oy + 194 + i * 60
        bg = "#16281F" if st == "right" else ("#2A1917" if st == "wrong" else INK3)
        bd = GREEN if st == "right" else (RED if st == "wrong" else TR)
        rect(ox + 24, y, 312, 50, bg, bd, 14, sw=2 if st else 1)
        ellipse(ox + 40, y + 13, 24, 24, TR, "#5A5449", 1)
        text(ox + 52, y + 19, k, 11, "#8B857A", "center")
        text(ox + 76, y + 17, s, 14, "#EDE9E0")
        if st:
            text(ox + 316, y + 16, "✓" if st == "right" else "✕", 14,
                 GREEN if st == "right" else RED, "right")

    rect(ox + 24, oy + 444, 312, 24, "#2A1917", TR, 8)
    text(ox + 36, oy + 448, "✕  回答错误 · 正确答案 C", 12, RED)

    rect(ox + 24, oy + 484, 312, 150, INK2, TR, 16)
    text(ox + 40, oy + 500, "知识点解析", 13, GOLD)
    for i, ln in enumerate(["指标异常的第一步永远是「定义对齐」：确认口径、",
                            "统计窗口、埋点是否发生变更，避免把口径变化误判",
                            "为业务下滑。排除口径问题后，再按漏斗逐层下钻。"]):
        text(ox + 40, oy + 524 + i * 22, ln, 12, "#C6C0B4")
    text(ox + 40, oy + 596, "来源：用户增长黑客指南.pdf · 第 42 页", 10, "#6E685C")
    rect(ox + 40, oy + 614, 92, 1, "#3A3630", TR, 0)

    rect(ox + 24, oy + 650, 152, 48, TR, "#4A443A", 14)
    text(ox + 100, oy + 665, "加入重点", 13, "#C6C0B4", "center")
    rect(ox + 184, oy + 650, 152, 48, GOLD, TR, 14)
    text(ox + 260, oy + 665, "下一题", 13, WHITE, "center")
    caption(ox, oy, 6, "答题 · 判分与解析",
            "即时对错反馈 + 知识点解析 + 溯源页码；可一键标记为重点，缩短复习间隔。")


# ---------------------------------------------------------------- 07 口述作答
def screen_speak(ox, oy):
    group("s-speak")
    frame(ox, oy, INK)
    quiz_header(ox, oy, 2, 3, "0:24", 2 / 3)
    chip(ox + 24, oy + 66, "产品管理", GOLD, "#3A2F14", 11, 9, 22)
    w = chip(ox + 24 + tw("产品管理", 11) + 26, oy + 66, "口述题", GOLD_L, "#2A2418", 11, 9, 22)
    text(ox + 24, oy + 110, "用你自己的话说清 OKR 与 KPI", 19, WHITE)
    text(ox + 24, oy + 140, "的核心区别，并举一个例子。", 19, WHITE)

    rect(ox + 24, oy + 186, 312, 62, INK2, TR, 14)
    text(ox + 40, oy + 198, "AI 会从三个维度评估你的回答", 11, GOLD)
    for i, s in enumerate(["概念准确", "要点覆盖", "表达逻辑"]):
        chip(ox + 40 + i * 88, oy + 218, s, "#C6C0B4", INK3, 10, 10, 20)

    # 波形
    rect(ox + 24, oy + 268, 312, 110, INK2, TR, 16)
    hs = [8, 16, 30, 22, 44, 58, 36, 66, 48, 72, 40, 60, 30, 50, 24, 38, 18, 28, 12, 20, 8]
    for i, hh in enumerate(hs):
        x = ox + 42 + i * 14
        c = GOLD if i < 13 else "#4A443A"
        rect(x, oy + 328 - hh / 2, 5, hh, c, TR, 3)
    text(ox + 40, oy + 356, "● 录音中  00:12", 11, RED)
    text(ox + 316, oy + 356, "剩余 48 秒", 10, "#6E685C", "right")

    # 实时转写
    rect(ox + 24, oy + 396, 312, 148, INK3, TR, 16)
    text(ox + 40, oy + 410, "实时转写", 11, "#8B857A")
    for i, ln in enumerate(["OKR 更强调方向和挑战性，是要「团队想去哪里」，",
                            "允许没有完全达成；KPI 更偏考核底线，通常和",
                            "绩效强绑定。比如我们这个季度的 OKR 是「让新",
                            "用户第一周就用上核心功能」，而 KPI 会是「次周"]):
        text(ox + 40, oy + 434 + i * 22, ln, 12, "#DCD6CA")
    text(ox + 40, oy + 522, "留存率 ≥ 35%」…", 12, "#8B857A")

    # 录音按钮
    ellipse(ox + W / 2 - 42, oy + 566, 84, 84, "#2A2016", TR)
    ellipse(ox + W / 2 - 34, oy + 574, 68, 68, GOLD, TR)
    text(ox + W / 2, oy + 596, "🎤", 20, WHITE, "center")
    text(ox + W / 2, oy + 660, "松开结束作答", 12, "#C6C0B4", "center")
    text(ox + W / 2, oy + 686, "改用文字作答", 11, GOLD, "center")
    line(ox + W / 2 - tw("改用文字作答", 11) / 2, oy + 702,
         ox + W / 2 + tw("改用文字作答", 11) / 2, oy + 702, GOLD_D)
    caption(ox, oy, 7, "答题 · 口述作答（AI）",
            "按住说话，语音实时转写；不做发音评测，只评估内容——概念准确 / 要点覆盖 / 表达逻辑。")


# ---------------------------------------------------------------- 08 AI 评估
def screen_ai_result(ox, oy):
    group("s-airesult")
    frame(ox, oy)
    text(ox + 24, oy + 30, "‹", 20, T3)
    text(ox + W - 24, oy + 30, "2/3", 12, T2, "right")
    text(ox + 24, oy + 60, "AI 评估结果", 24, T1)
    text(ox + 24, oy + 96, "口述题 · OKR 与 KPI 的核心区别", 11, T2)

    # 总分环
    rect(ox + 24, oy + 124, 312, 128, INK, TR, 18)
    cx, cy = ox + 88, oy + 188
    ellipse(cx - 42, cy - 42, 84, 84, TR, "#3A3630", 3)
    ellipse(cx - 38, cy - 38, 76, 76, TR, GOLD, 3)
    text(cx, cy - 18, "82", 28, WHITE, "center")
    text(cx, cy + 14, "分", 10, "#8B857A", "center")
    text(ox + 152, oy + 146, "基本达标，还差一点", 15, WHITE)
    dims = [("概念准确", 90, GREEN), ("要点覆盖", 70, AMBER), ("表达逻辑", 85, GREEN)]
    for i, (nm, v, c) in enumerate(dims):
        y = oy + 176 + i * 24
        text(ox + 152, y, nm, 10, "#8B857A")
        rect(ox + 212, y + 4, 84, 6, "#3A3630", TR, 3)
        rect(ox + 212, y + 4, 84 * v / 100, 6, c, TR, 3)
        text(ox + 316, y, str(v), 10, "#C6C0B4", "right")

    # 命中要点
    rect(ox + 24, oy + 266, 312, 118, WHITE, TR, 16)
    text(ox + 40, oy + 280, "✓  已讲到的要点", 12, GREEN)
    for i, s in enumerate(["区分了「方向性目标」与「考核指标」", "指出 OKR 允许不完全达成",
                           "给出了贴合自身业务的例子"]):
        text(ox + 40, oy + 304 + i * 24, "· " + s, 11, T1)

    # 遗漏要点
    rect(ox + 24, oy + 396, 312, 96, "#FDF6E7", TR, 16)
    text(ox + 40, oy + 410, "!  遗漏 / 需要补强", 12, AMBER)
    for i, s in enumerate(["未提到 OKR 通常「公开透明」、KPI 多为自上而下",
                           "没有说明两者可以并存的组合方式"]):
        text(ox + 40, oy + 434 + i * 22, "· " + s, 11, T1)

    # AI 点评
    rect(ox + 24, oy + 504, 312, 122, WHITE, TR, 16)
    text(ox + 40, oy + 518, "AI 点评", 12, T2)
    for i, ln in enumerate(["表述自然、例子贴切，作为口头回答已经能站得住。",
                            "如果面对上级，建议先给一句结论式定义，再补",
                            "「OKR 定方向、KPI 保底线，二者可并行」的结构，",
                            "会更有说服力。"]):
        text(ox + 40, oy + 542 + i * 20, ln, 11, T1)

    rect(ox + 24, oy + 642, 152, 48, TR, T3, 14)
    text(ox + 100, oy + 657, "重新口述", 13, T1, "center")
    rect(ox + 184, oy + 642, 152, 48, INK, TR, 14)
    text(ox + 260, oy + 657, "下一题", 13, WHITE, "center")
    text(ox + W / 2, oy + 706, "本题掌握度 42 → 58 · 下次复习 3 天后", 10, T2, "center")
    caption(ox, oy, 8, "答题 · AI 评估反馈",
            "总分 + 三维打分 + 命中/遗漏要点 + 改进建议；评估结果直接回写掌握度与复习间隔。")


# ---------------------------------------------------------------- 标题与规范
def title_block(x, y):
    group("meta-title")
    text(x, y, "吾日三省 · Daily Reflection", 42, T1)
    text(x, y + 58, "iOS / iPadOS / macOS 界面设计稿 · SwiftUI · v1.0", 16, T2)
    text(x, y + 88, "8 个核心界面 · 含 AI 口述作答与评估反馈", 14, GOLD)


def spec_block(x, y):
    group("meta-spec")
    rect(x, y, 420, 720, WHITE, LINE, 18)
    text(x + 28, y + 28, "设计规范", 22, T1)

    text(x + 28, y + 76, "配色", 13, GOLD)
    pal = [("宣纸底 Cream", CREAM), ("卡片 White", WHITE), ("墨黑 Ink", INK),
           ("赤金 Gold", GOLD), ("竹青 Green", GREEN), ("警示 Red", RED),
           ("提醒 Amber", AMBER), ("次要文字 Grey", T2)]
    for i, (nm, c) in enumerate(pal):
        yy = y + 102 + i * 34
        rect(x + 28, yy, 44, 26, c, LINE if c == WHITE else TR, 6)
        text(x + 84, yy + 3, nm, 12, T1)
        text(x + 392, yy + 4, c.upper(), 11, T3, "right")

    text(x + 28, y + 392, "字体与层级", 13, GOLD)
    for i, (nm, d) in enumerate([("页面大标题", "30 / 衬线体（吾日三省、资料库）"),
                                 ("题干", "19-20 / 常规，最多两行"),
                                 ("卡片标题", "13-15 / 中粗"),
                                 ("辅助说明", "10-11 / 次要灰")]):
        yy = y + 418 + i * 28
        text(x + 28, yy, nm, 12, T1)
        text(x + 130, yy + 1, d, 11, T2)

    text(x + 28, y + 542, "度量", 13, GOLD)
    for i, (nm, d) in enumerate([("页面留白", "左右 24pt"),
                                 ("卡片圆角", "列表 14pt · 区块 16-18pt"),
                                 ("卡片间距", "垂直 8-12pt"),
                                 ("点击区域", "最小 44×44pt")]):
        yy = y + 568 + i * 28
        text(x + 28, yy, nm, 12, T1)
        text(x + 130, yy + 1, d, 11, T2)

    text(x + 28, y + 680, "浅色为「输入与回顾」，深色为「专注答题」", 11, GOLD_D)


def flow_block(x, y):
    group("meta-flow")
    text(x, y, "核心链路", 22, T1)
    steps = [("上传资料", "PDF / MD / 图片 OCR", CREAM),
             ("AI 提取知识点", "原子化 + 溯源", CREAM),
             ("生成题目", "客观题 + 口述题", CREAM),
             ("碎片复习", "推送 3-5 题 / 4 分钟", INK),
             ("判分与评估", "自动判分 / AI 评语", INK),
             ("间隔重复调度", "更新掌握度与间隔", CREAM)]
    bw, bh, gap = 196, 78, 54
    for i, (t, d, bg) in enumerate(steps):
        bx = x + i * (bw + gap)
        dark = bg == INK
        rect(bx, y + 44, bw, bh, bg, LINE if not dark else TR, 14)
        text(bx + 18, y + 62, t, 15, WHITE if dark else T1)
        text(bx + 18, y + 88, d, 11, "#8B857A" if dark else T2)
        if i:
            arrow(bx - gap + 12, y + 83, bx - 12, y + 83, T3)
    ax = x + 5 * (bw + gap) + bw / 2
    arrow(ax, y + 122 + 12, ax, y + 168, T3)
    line(ax, y + 168, x + bw / 2, y + 168, T3, 2)
    arrow(x + bw / 2, y + 168, x + bw / 2, y + 130, T3)
    text(x + 2 * (bw + gap), y + 176, "答错 / 评估未达标 → 缩短间隔并优先重排", 12, T2)


# ---------------------------------------------------------------- 组装
title_block(0, -190)
screen_today(0, 0)
screen_materials(COL, 0)
screen_knowledge(COL * 2, 0)
screen_stats(COL * 3, 0)
screen_quiz(0, ROW)
screen_feedback(COL, ROW)
screen_speak(COL * 2, ROW)
screen_ai_result(COL * 3, ROW)
spec_block(COL * 4 + 40, 0)
flow_block(0, ROW * 2 + 30)

doc = {
    "type": "excalidraw",
    "version": 2,
    "source": "https://excalidraw.com",
    "elements": ELS,
    "appState": {"gridSize": None, "viewBackgroundColor": "#F7F5F0"},
    "files": {},
}
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui-design.excalidraw")
with open(out, "w", encoding="utf-8") as f:
    json.dump(doc, f, ensure_ascii=False, indent=2)
print("wrote %s (%d elements)" % (out, len(ELS)))
