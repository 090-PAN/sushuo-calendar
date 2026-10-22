# -*- coding: utf-8 -*-
"""
把活动数据转成：
  1) 广外南活动日程.ics   —— 手机点开即可加入日历（推荐用 webcal 订阅，自动更新）
  2) 活动日程总览.md      —— 按时间排序的总览，可传入 Dify 活动知识库

数据源二选一：
    --source feishu   从飞书多维表格「活动日程」读（推荐，唯一数据源）
    --source local    用本文件里的 EVENTS 列表（无网时的兜底）

用法：
    python act_schedule.py --source feishu
    python act_schedule.py --source feishu --url-base https://xxx.github.io/sushuo
    python act_schedule.py --only ics --copy-to D:\\网盘\\public
飞书读不到时会自动回退到 local，不至于中断。
"""
import argparse
import datetime as dt
import os
import shutil
import uuid

TZ = dt.timezone(dt.timedelta(hours=8))  # Asia/Shanghai
OUT_DIR = "out_schedule"

# kind: act=活动本体  ddl=报名/提交截止
# 时间均为北京时间；alarm_days 为提前提醒天数
EVENTS = [
    dict(kind="ddl", name="秋之声歌手大赛·复赛材料报送截止",
         start=(2026, 10, 15, 17, 0), end=(2026, 10, 15, 17, 30),
         place="线上（校团委邮箱）", alarm_days=[3, 1],
         url="https://mp.weixin.qq.com/s/c12y5kF81eARSWDWDL_lOw",
         desc="由学院推报，10月15日17:00前发至 gw18620798812@126.com"),
    dict(kind="ddl", name="羽毛球新生杯·班级报名截止",
         start=(2026, 10, 22, 12, 0), end=(2026, 10, 22, 12, 30),
         place="各学院体育部", alarm_days=[3, 1],
         url="https://mp.weixin.qq.com/s/4FhYG-jGhLKuQM0CkHZ75A",
         desc="各班体委10月22日12:00前交报名表至学院体育部；学院20:00前发 gwymqxh@126.com"),
    dict(kind="act", name="秋之声校园歌手大赛·复赛",
         start=(2026, 10, 22, 0, 0), end=(2026, 10, 22, 23, 59),
         place="具体见学院通知", alarm_days=[1],
         url="https://mp.weixin.qq.com/s/c12y5kF81eARSWDWDL_lOw",
         desc="第29届校园歌手大赛，流行+红歌双赛道"),
    dict(kind="act", name="秋之声校园歌手大赛·决赛",
         start=(2026, 10, 29, 0, 0), end=(2026, 10, 29, 23, 59),
         place="具体见学院通知", alarm_days=[1],
         url="https://mp.weixin.qq.com/s/c12y5kF81eARSWDWDL_lOw",
         desc="第29届校园歌手大赛决赛"),
    dict(kind="act", name="羽毛球新生杯·比赛日",
         start=(2026, 10, 31, 8, 0), end=(2026, 10, 31, 19, 0),
         place="大学城校区体育馆", alarm_days=[1],
         url="https://mp.weixin.qq.com/s/4FhYG-jGhLKuQM0CkHZ75A",
         desc="新生专属羽毛球赛，8:00-19:00"),
    dict(kind="ddl", name="粤港澳大湾区大学生艺术节·报名截止",
         start=(2026, 11, 1, 0, 0), end=(2026, 11, 1, 23, 59),
         place="线上报送校团委邮箱", alarm_days=[7, 3, 1],
         url="https://mp.weixin.qq.com/s/WZ_0jAEAJ9SZQnUk_01dIg",
         desc="甲组11月1日前报至 gw18620798812@126.com；乙组由艺术学院院内选拔"),
    dict(kind="act", name="粤港澳大湾区大学生艺术节·展演展示",
         start=(2026, 12, 1, 0, 0), end=(2026, 12, 31, 23, 59),
         place="另行通知", alarm_days=[7],
         url="https://mp.weixin.qq.com/s/WZ_0jAEAJ9SZQnUk_01dIg",
         desc="第六届艺术节展演阶段（具体安排以主办方通知为准）"),
]


def to_utc(y, mo, d, h, mi):
    return dt.datetime(y, mo, d, h, mi, tzinfo=TZ).astimezone(dt.timezone.utc)


def load_from_feishu():
    """从飞书多维表格「活动日程」读活动，返回与 EVENTS 同结构的数据"""
    import feishu_api as fa

    tok = fa.get_token()
    tid = fa.ACT_TABLE_ID or fa.find_table(tok, "活动日程")
    if not tid:
        raise RuntimeError("找不到「活动日程」表，先跑 feishu_act_init.py")
    recs = fa.list_records(tok, tid)

    events = []
    for r in recs:
        f = r.get("fields", {})
        name = fa.text_of(f.get("活动名称"))
        if not name:
            continue
        status = fa.text_of(f.get("状态"))
        if status == "草稿":          # 草稿不对外
            continue
        start = fa.ms_to_cst(f.get("开始时间"))
        if not start:                 # 时间待定，日历里放不了
            continue
        end = fa.ms_to_cst(f.get("结束时间")) or start

        alarm = fa.text_of(f.get("提醒天数")).replace("，", ",")
        days = [int(x) for x in alarm.split(",") if x.strip().isdigit()]

        link = f.get("原文链接") or {}
        events.append(dict(
            kind="ddl" if fa.text_of(f.get("类型")) == "报名截止" else "act",
            name=name, start=start, end=end,
            place=fa.text_of(f.get("地点")),
            signup=fa.text_of(f.get("报名方式")),
            highlight=fa.text_of(f.get("活动亮点")),
            url=link.get("link", "") if isinstance(link, dict) else "",
            status=status,
            alarm_days=days or [1],
            desc=fa.text_of(f.get("报名方式")),
        ))
    return events


def ics_escape(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace(";", r"\;").replace(",", r"\,").replace("\n", r"\n")


def fold(line: str) -> str:
    """RFC5545 折行：单行不超过 75 字节"""
    raw = line.encode("utf-8")
    if len(raw) <= 73:
        return line
    out, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > 73:
            out.append(cur.decode("utf-8"))
            cur = b" " + b
        else:
            cur += b
    out.append(cur.decode("utf-8"))
    return "\r\n".join(out)


def build_ics(events, ttl_hours=6) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    # 订阅模式关键：告诉客户端多久回来拉一次
    ttl = f"PT{ttl_hours}H"
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0",
             "PRODID:-//宿说//广外南活动日程//CN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             "X-WR-CALNAME:广外南活动日程", "X-WR-TIMEZONE:Asia/Shanghai",
             f"REFRESH-INTERVAL:{ttl}", f"X-PUBLISHED-TTL:{ttl}"]

    for e in events:
        s = to_utc(*e["start"])
        en = to_utc(*e["end"])
        prefix = "⏰ " if e["kind"] == "ddl" else "🎪 "
        # UID 由活动名派生：每次重新生成都保持不变，
        # 订阅客户端据此做"更新"而不是"重复新建"，这是订阅能用的前提
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uuid.uuid5(uuid.NAMESPACE_URL, e['name'])}@sushuo",
            f"DTSTAMP:{stamp}",
            f"LAST-MODIFIED:{stamp}",
            "SEQUENCE:0",
            "STATUS:CONFIRMED",
            "TRANSP:TRANSPARENT",
            f"DTSTART:{s.strftime('%Y%m%dT%H%M%SZ')}",
            f"DTEND:{en.strftime('%Y%m%dT%H%M%SZ')}",
            fold("SUMMARY:" + ics_escape(prefix + e["name"])),
            fold("LOCATION:" + ics_escape(e["place"])),
            fold("DESCRIPTION:" + ics_escape(e["desc"])),
        ]
        for d in e.get("alarm_days", []):
            lines += ["BEGIN:VALARM", f"TRIGGER:-P{d}D", "ACTION:DISPLAY",
                      f"DESCRIPTION:{ics_escape(e['name'])} 还有 {d} 天", "END:VALARM"]
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


def build_md(events, url_base=None) -> str:
    today = dt.datetime.now(TZ).date()
    head = [
        "# 广外南（大学城校区）活动日程总览",
        "",
        f"> 本表由「宿说」整理，最后更新 {today.isoformat()}，按时间从近到远排列。",
        "> 条目均来自官方推文，时间以主办方最新通知为准。",
        "",
        "| 日期 | 事项 | 类型 | 地点 | 报名方式 | 亮点 | 原文 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    rows = []
    for e in events:
        d = dt.date(*e["start"][:3])
        typ = "报名/提交截止" if e["kind"] == "ddl" else "活动"
        signup = (e.get("signup") or e.get("desc") or "—").replace("|", "/")
        hl = (e.get("highlight") or "—").replace("|", "/")
        rows.append(
            f"| {d.year}年{d.month}月{d.day}日 | {e['name']} | {typ} | "
            f"{e['place'] or '—'} | {signup} | {hl} | {e.get('url') or '—'} |"
        )
    if url_base:
        base = url_base.rstrip("/")
        sub = base.replace("https://", "webcal://").replace("http://", "webcal://")
        tail = ["", "## 订阅日历（推荐）", "",
                "一次订阅，后续自动同步，不用重复发文件：", "",
                f"- 订阅地址：`{sub}/广外南活动日程.ics`",
                f"- 打不开就用在浏览器打开：`{base}/广外南活动日程.ics`", "",
                "订阅方法：",
                "- iPhone：设置 → 日历 → 账户 → 添加账户 → 其他 → 添加已订阅日历，粘贴上面的地址",
                "- 安卓：系统日历 → 设置 → 添加日历 → 订阅 URL（不同品牌位置略有差异）",
                "- 电脑：Outlook / Google Calendar → 通过 URL 添加日历",
                "", "## 临时用法", "",
                "不想订阅就直接下载 .ics 导入，但活动更新后需要重新导入一次。",
                ""]
    else:
        tail = ["", "## 使用建议", "",
                "- 直接下载「广外南活动日程.ics」导入手机日历即可（iOS/Android 均支持）。",
                "- 标注「报名/提交截止」的条目已内置提前提醒。",
                "- 若把本文件托管到公网地址，可用 `webcal://` 订阅，实现自动更新。",
                ""]
    return "\n".join(head + rows + tail)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["ics", "md"], default=None)
    ap.add_argument("--out", default=OUT_DIR)
    ap.add_argument("--include-past", action="store_true", help="保留已过期的日程（默认剔除）")
    ap.add_argument("--url-base", default=None,
                    help="ics 的公网根地址，用于生成 webcal:// 订阅链接，如 https://xxx.github.io/sushuo")
    ap.add_argument("--copy-to", default=None,
                    help="生成后把 ics 复制到该目录（可填网盘/静态站点同步目录）")
    ap.add_argument("--ttl", type=int, default=6, help="客户端刷新间隔小时数，默认 6")
    ap.add_argument("--source", choices=["feishu", "local"], default="feishu",
                    help="活动数据来源，默认飞书多维表格")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)

    if a.source == "feishu":
        try:
            events = load_from_feishu()
            print(f"已从飞书「活动日程」表读到 {len(events)} 条活动")
        except Exception as ex:
            print(f"[警告] 读取飞书失败：{ex}")
            print("[警告] 回退到本地 EVENTS 列表（数据可能不是最新）")
            events = list(EVENTS)
    else:
        events = list(EVENTS)
    events = sorted(events, key=lambda e: e["start"])
    if not a.include_past:
        cutoff = dt.datetime.now(TZ)
        events = [e for e in events if dt.datetime(*e["end"], tzinfo=TZ) >= cutoff]
        print(f"已剔除过期日程，剩余 {len(events)} 条（加 --include-past 可保留）")

    ics_path = None
    if a.only in (None, "ics"):
        ics_path = os.path.join(a.out, "广外南活动日程.ics")
        with open(ics_path, "w", encoding="utf-8", newline="") as f:
            f.write(build_ics(events, a.ttl))
        print("ics ->", ics_path)

    if a.only in (None, "md"):
        p = os.path.join(a.out, "活动日程总览.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(build_md(events, a.url_base))
        print("md  ->", p)

    if a.copy_to and ics_path:
        os.makedirs(a.copy_to, exist_ok=True)
        dst = os.path.join(a.copy_to, "广外南活动日程.ics")
        shutil.copyfile(ics_path, dst)
        print("copy->", dst)

    print(f"共 {len(events)} 条日程")


if __name__ == "__main__":
    main()
