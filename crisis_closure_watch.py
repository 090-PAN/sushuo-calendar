# -*- coding: utf-8 -*-
"""宿说 · 危机闭环回执守护

作用：轮询飞书「危机记录」表，发现「处理状态」由 待处理 → 已跟进/已结案 时，
向心理中心老师群（飞书群机器人 webhook）推送一张绿色回执卡片，完成闭环。

关键设计：
- 幂等：回执成功后写「闭环回执」字段（记录时间戳），已回执过的记录不再重复推送。
  即使脚本重启、或多实例并发，也不会重复刷屏。
- 容错：单条记录推送失败不中断整轮；网络异常下一轮自动重试。
- 零依赖：只用标准库 + 项目内 feishu_api.py。

用法：
    python crisis_closure_watch.py            # 守护模式，每 60 秒扫一次
    python crisis_closure_watch.py --once     # 只扫一次（便于验证/定时任务）
    python crisis_closure_watch.py --once --dry-run   # 只看会推什么，不真发

webhook 来源（按优先级）：
    1) 环境变量 FEISHU_BOT_WEBHOOK
    2) local_config.py 里的 FEISHU_BOT_WEBHOOK
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from feishu_api import BASE_ID, get_token, list_records, _req, text_of  # noqa: E402

CRISIS_TABLE = "tbl6rGT2qL3aTEYL"
FIELD_STATUS = "处理状态"
FIELD_RECEIPT = "闭环回执"
CLOSED_STATES = ("已跟进", "已结案")
PENDING_STATES = ("待处理",)

TABLE_URL = (
    f"https://wcnq49wi2oso.feishu.cn/base/{BASE_ID}"
    f"?table={CRISIS_TABLE}"
)


def get_webhook():
    hook = os.environ.get("FEISHU_BOT_WEBHOOK", "").strip()
    if hook:
        return hook
    try:
        from local_config import FEISHU_BOT_WEBHOOK  # type: ignore
        return str(FEISHU_BOT_WEBHOOK).strip()
    except (ImportError, AttributeError):
        return ""


def post_card(webhook, payload, timeout=10):
    """向飞书群机器人发消息。返回 (ok, detail)。"""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(webhook, data=data, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.loads(r.read().decode("utf-8") or "{}")
        # 飞书机器人成功返回 {"code":0,"msg":"success"} 或旧版 {"StatusCode":0}
        code = body.get("code", body.get("StatusCode", 0))
        return (code == 0, body)
    except urllib.error.HTTPError as e:
        return (False, f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:200]}")
    except Exception as e:  # noqa: BLE001
        return (False, f"{type(e).__name__}: {e}")


def build_receipt_card(rec_id, fields, status):
    """绿色闭环回执卡片。"""
    keyword = text_of(fields.get("危机关键词")) or "—"
    when = text_of(fields.get("发生时间")) or "—"
    note = text_of(fields.get("备注"))
    is_closed = status == "已结案"
    title = "✅ 危机已结案" if is_closed else "✅ 危机已跟进"
    subtitle = "心理中心已处置完成，本事件闭环" if is_closed else "已接手跟进，事件进入处置中"
    elements = [
        {"tag": "div", "text": {"tag": "lark_md",
                               "content": f"**风险点**：{keyword}\n**发生时间**：{when}"}},
        {"tag": "hr"},
        {"tag": "div", "text": {"tag": "lark_md",
                               "content": f"**当前状态**：**{status}**\n**回执时间**：{_now()}"}},
        {"tag": "note", "elements": [{"tag": "plain_text",
                                      "content": f"记录 ID：{rec_id}"}]},
        {"tag": "action", "actions": [{
            "tag": "button",
            "text": {"tag": "plain_text", "content": "查看记录"},
            "type": "primary",
            "url": TABLE_URL,
        }]},
    ]
    if note:
        elements.insert(2, {"tag": "div", "text": {"tag": "lark_md",
                                                   "content": f"**处置备注**：{note[:200]}"}})
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "subtitle": {"tag": "plain_text", "content": subtitle},
                "template": "green",
            },
            "elements": elements,
        },
    }


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def update_receipt(token, rec_id, text):
    """把回执标记写回记录（幂等锚点）。"""
    d = _req(
        "PUT",
        f"/bitable/v1/apps/{BASE_ID}/tables/{CRISIS_TABLE}/records/{rec_id}",
        token=token,
        payload={"fields": {FIELD_RECEIPT: text}},
    )
    return d.get("code") == 0


def scan_once(token, webhook, dry_run=False, verbose=True):
    """扫一轮，返回 (推送数, 跳过数, 失败数)。"""
    records = list_records(token, CRISIS_TABLE)
    pushed = skipped = failed = 0

    for r in records:
        rec_id = r.get("record_id", "")
        f = r.get("fields") or {}
        status = text_of(f.get(FIELD_STATUS)).strip()
        receipt = text_of(f.get(FIELD_RECEIPT)).strip()

        if status not in CLOSED_STATES:
            continue
        if receipt:  # 已回执过，幂等跳过
            skipped += 1
            continue

        card = build_receipt_card(rec_id, f, status)
        if dry_run:
            if verbose:
                print(f"[DRY] 将回执 {rec_id} status={status} keyword={text_of(f.get('危机关键词'))}")
            pushed += 1
            continue

        if not webhook:
            if verbose:
                print("[SKIP] 未配置 webhook，无法回执")
            failed += 1
            continue

        ok, detail = post_card(webhook, card)
        if ok:
            stamp = f"已回执 {_now()}"
            if update_receipt(token, rec_id, stamp):
                pushed += 1
                if verbose:
                    print(f"[OK] 回执成功 {rec_id} ({status})")
            else:
                # 卡片已发出但标记失败 → 下一轮会重复发，取舍：宁重复不丢
                pushed += 1
                if verbose:
                    print(f"[WARN] 卡片已发但标记写入失败 {rec_id}，下轮可能重复")
        else:
            failed += 1
            if verbose:
                print(f"[FAIL] 回执失败 {rec_id}: {detail}")

    return pushed, skipped, failed


def main():
    ap = argparse.ArgumentParser(description="宿说危机闭环回执守护")
    ap.add_argument("--once", action="store_true", help="只扫一次")
    ap.add_argument("--dry-run", action="store_true", help="只打印不发送")
    ap.add_argument("--interval", type=int, default=60, help="轮询间隔秒数（默认 60）")
    args = ap.parse_args()

    webhook = get_webhook()
    if not webhook and not args.dry_run:
        print("错误：未找到 webhook。请设置环境变量 FEISHU_BOT_WEBHOOK，"
              "或在 local_config.py 里加 FEISHU_BOT_WEBHOOK = 'https://open.feishu.cn/open-apis/bot/v2/hook/xxx'")
        return 2
    if args.dry_run and not webhook:
        print("提示：dry-run 模式，未配置 webhook 也可运行")

    token = get_token()
    print(f"[{_now()}] 闭环回执守护启动｜interval={args.interval}s｜dry_run={args.dry_run}")

    if args.once:
        p, s, f = scan_once(token, webhook, dry_run=args.dry_run)
        print(f"[{_now()}] 本轮：回执 {p}｜已回执跳过 {s}｜失败 {f}")
        return 0 if f == 0 else 1

    while True:
        try:
            token = get_token()
            p, s, f = scan_once(token, webhook, dry_run=args.dry_run)
            if p or f:
                print(f"[{_now()}] 回执 {p}｜跳过 {s}｜失败 {f}")
        except KeyboardInterrupt:
            print("\n已停止")
            return 0
        except Exception as e:  # noqa: BLE001
            print(f"[{_now()}] 本轮异常：{type(e).__name__}: {e}")
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
