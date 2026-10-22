# 广外南活动日历（GitHub Pages 源）

本目录的内容 = GitHub 仓库 **根目录** 应放置的全部文件。
直接把这里的所有文件上传到仓库根即可（不要套子文件夹）。

## 文件说明
- `index.html` —— 订阅落地页（链接自动适配本仓库域名）
- `广外南活动日程.ics` —— 订阅型日历（REFRESH-INTERVAL:PT6H，新活动自动同步）
- `活动日程总览.md` —— 活动文字总览
- `publish_calendar.py` / `act_schedule.py` / `feishu_api.py` —— 飞书→日历生成脚本（自动同步用）
- `local_config.example.py` —— 本地配置模板（真实值放 `local_config.py`，不提交）
- `.gitignore` —— 忽略本地私有配置与临时产物
- `.github/workflows/publish.yml` —— 每天北京时间 09:00 自动从飞书同步日历

## 启用 Pages（一次性）
仓库 **Settings → Pages → Build and deployment**：
- Source：`Deploy from a branch`
- Branch：`main`　Folder：`/(root)`
- Save。约 1–2 分钟后访问 `https://090-PAN.github.io/sushuo-calendar/`

## 启用每日自动同步（可选，推荐）
仓库 **Settings → Secrets and variables → Actions → New repository secret** 添加 4 个：
- `FEISHU_APP_ID` = `cli_aa5dd58092b85d00`
- `FEISHU_APP_SECRET` = 飞书应用 Secret（即 local_config.py 里那串）
- `FEISHU_BASE_ID` = `XQWPbNC23aF9OhsmfbecACMFnTe`
- `ACTIVITY_ICS_BASE_URL` = `https://090-PAN.github.io/sushuo-calendar`

> 不配 Secrets 也能用：日历就是本次上传的静态版本，之后想更新就重传 `.ics` / `.md`。
> 配了 Secrets 后，每天自动把飞书表里新活动同步进订阅日历，学生无需任何操作。

## 别忘了 bot 里的链接
Dify「宿说」应用的环境变量 `activity_ics_base_url` 也填成
`https://090-PAN.github.io/sushuo-calendar`，学生从 bot 回复点订阅才打得开。
