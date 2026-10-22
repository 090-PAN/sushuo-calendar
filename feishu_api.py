# -*- coding: utf-8 -*-
"""
飞书多维表格极简客户端 —— 只依赖标准库（urllib），不装任何三方包。

提供：获取 token、按名字找表、读取记录。
"""
import datetime as dt
import json
import os
import urllib.error
import urllib.request

API = "https://open.feishu.cn/open-apis"

# 凭证加载策略（安全优先）：
#   1) 若存在本地私有文件 local_config.py（已在 .gitignore 忽略，不会提交到仓库），优先用它，方便本地直接跑；
#   2) 否则读取环境变量（云端/CI 用 GitHub 仓库 Secrets 注入）；
#   3) 都没有则为 None，调用飞书 API 时 get_token() 会明确报错。
# ⚠ 绝不要把明文写死在会被提交到公开仓库的代码里。
try:
    from local_config import APP_ID, APP_SECRET, BASE_ID  # 本地私有，请勿提交
except ImportError:
    APP_ID = os.environ.get("FEISHU_APP_ID")
    APP_SECRET = os.environ.get("FEISHU_APP_SECRET")
    BASE_ID = os.environ.get("FEISHU_BASE_ID")

# 活动日程表（feishu_act_init.py 创建后得到）
ACT_TABLE_ID = "tblWsLeF4FUKKjXl"

# 宿舍知识库表（feishu_dorm_init.py 创建后得到）
DORM_TABLE_ID = "tblfzBcjXff0JN5x"

TZ = dt.timezone(dt.timedelta(hours=8))


def _req(method, path, token=None, payload=None, timeout=20):
    url = API + path
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json; charset=utf-8")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def get_token(app_id=APP_ID, app_secret=APP_SECRET):
    d = _req("POST", "/auth/v3/tenant_access_token/internal",
             payload={"app_id": app_id, "app_secret": app_secret})
    if d.get("code") != 0:
        raise RuntimeError(f"获取飞书 token 失败: {d.get('msg') or d}")
    return d["tenant_access_token"]


def find_table(token, name, base_id=BASE_ID):
    d = _req("GET", f"/bitable/v1/apps/{base_id}/tables?page_size=50", token=token)
    if d.get("code") != 0:
        raise RuntimeError(f"读取表列表失败: {d.get('msg') or d}")
    for it in (d.get("data", {}).get("items") or []):
        if it.get("name") == name:
            return it["table_id"]
    return None


def list_records(token, table_id, base_id=BASE_ID, page_size=100):
    """返回记录列表 [{'record_id':..., 'fields':{...}}]"""
    out, page_token = [], None
    while True:
        path = f"/bitable/v1/apps/{base_id}/tables/{table_id}/records?page_size={page_size}"
        if page_token:
            path += "&page_token=" + page_token
        d = _req("GET", path, token=token)
        if d.get("code") != 0:
            raise RuntimeError(f"读取记录失败: {d.get('msg') or d}")
        data = d.get("data") or {}
        out.extend(data.get("items") or data.get("records") or [])
        if not data.get("has_more"):
            break
        page_token = data.get("page_token")
    return out


def text_of(v):
    """飞书文本字段可能返回 str，也可能返回富文本数组"""
    if v is None:
        return ""
    if isinstance(v, list):
        return "".join(x.get("text", "") for x in v if isinstance(x, dict))
    return str(v)


def create_table(token, name, fields, base_id=BASE_ID, view_name="全部活动"):
    """fields: [{'field_name':..,'type':..}, ...]"""
    d = _req("POST", f"/bitable/v1/apps/{base_id}/tables", token=token,
             payload={"table": {"name": name, "default_view_name": view_name, "fields": fields}})
    if d.get("code") != 0:
        raise RuntimeError(f"建表失败: {d.get('msg') or d}")
    return d["data"]["table_id"]


def batch_create(token, table_id, records, base_id=BASE_ID):
    """records: [{'fields': {...}}, ...]，单次不超过 500 条"""
    d = _req("POST", f"/bitable/v1/apps/{base_id}/tables/{table_id}/records/batch_create",
             token=token, payload={"records": records})
    if d.get("code") != 0:
        raise RuntimeError(f"写入记录失败: {d.get('msg') or d}")
    return d


def ms_to_cst(ms):
    """毫秒时间戳 -> 北京时间 (y, mo, d, h, mi)"""
    if not ms:
        return None
    t = dt.datetime.fromtimestamp(int(ms) / 1000, TZ)
    return (t.year, t.month, t.day, t.hour, t.minute)
