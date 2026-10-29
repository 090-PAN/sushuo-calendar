# -*- coding: utf-8 -*-
# 本地配置模板：复制本文件为 local_config.py 并填入真实值。
# local_config.py 已在 .gitignore 中忽略，不会提交到仓库。
# 云端/CI（GitHub Actions）不需要本文件，改用仓库 Secrets 注入同名环境变量。
APP_ID = "在此填入飞书 App ID"
APP_SECRET = "在此填入飞书 App Secret"
BASE_ID = "在此填入飞书多维表格 Base ID"

# 危机通知群机器人（可选；仅本地跑 crisis_closure_watch.py 时需要）
# 形如 https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx
FEISHU_BOT_WEBHOOK = ""
