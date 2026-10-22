# -*- coding: utf-8 -*-
"""
把飞书「活动日程」表生成公开订阅日历，写入 site/ 目录（GitHub Pages 源）。

用法：
    python publish_calendar.py                 # 仅生成本地 site/
    python publish_calendar.py --push          # 生成并提交+推送到 git（需已配置 remote）
    ACTIVITY_ICS_BASE_URL=https://x.github.io/sushuo python publish_calendar.py

说明：
    - 飞书凭证优先读环境变量 FEISHU_APP_ID/SECRET/BASE_ID，缺省用 feishu_api.py 里的默认。
    - site/ 里的 .ics 带 REFRESH-INTERVAL:PT6H，客户端每 6 小时自动回源拉取，
      因此飞书表新增/修改活动后，只要重新跑本脚本并推送，订阅者日历会自动更新。
"""
import os
import sys
import argparse
import datetime as dt
import subprocess
import act_schedule as ac


def main():
    parser = argparse.ArgumentParser(description="飞书活动表 -> 公开订阅日历")
    parser.add_argument("--out", default="site",
                        help="输出目录；本地预览用默认 site/，部署到 GitHub Pages 仓库根时传 \".\"")
    parser.add_argument("--push", action="store_true", help="生成后 git add/commit/push")
    args = parser.parse_args()
    SITE = args.out

    url_base = os.environ.get("ACTIVITY_ICS_BASE_URL", "").strip()
    try:
        events = ac.load_from_feishu()
        print(f"[ok] 飞书读取 {len(events)} 条")
    except Exception as ex:
        print(f"[warn] 飞书读取失败，回退本地 EVENTS：{ex}")
        events = list(ac.EVENTS)

    events = sorted(events, key=lambda e: e["start"])
    cutoff = dt.datetime.now(ac.TZ)
    events = [e for e in events if dt.datetime(*e["end"], tzinfo=ac.TZ) >= cutoff]
    print(f"[ok] 剔除过期后剩余 {len(events)} 条")

    os.makedirs(SITE, exist_ok=True)
    with open(os.path.join(SITE, "广外南活动日程.ics"), "w", encoding="utf-8", newline="") as f:
        f.write(ac.build_ics(events, 6))
    with open(os.path.join(SITE, "活动日程总览.md"), "w", encoding="utf-8") as f:
        f.write(ac.build_md(events, url_base or None))
    print(f"[ok] 已写入 {SITE}/")

    if args.push:
        try:
            subprocess.run(["git", "add", "."], check=True)
            subprocess.run(["git", "commit", "-m", "chore: update activity calendar"], check=True)
            subprocess.run(["git", "push"], check=True)
            print("[ok] 已 git push")
        except Exception as ex:
            print(f"[warn] git push 失败（可能无改动或无 remote）：{ex}")


if __name__ == "__main__":
    main()
