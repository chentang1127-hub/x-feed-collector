# X Feed Collector

自动采集 X (Twitter) 博主的推文 → Google 翻译英译中 → 推送到飞书群。

**零成本、全自动、一次配置。**

---

## 工作原理

```
每 30 分钟
  └→ GitHub Actions 自动运行
       ├→ 用你的 X Cookie 采集 @Serenity 最新推文
       ├→ 和本地记录对比，筛选出新推文
       ├→ Google Translate 翻译（英→中、免费无需注册）
       ├→ 下载图片 → 上传飞书图床
       ├→ 推送到飞书群（原文+翻译+图片）
       └→ 更新去重记录，避免重复推送
```

---

## 准备工作：你需要 4 个密钥

整个流程完全免费，你需要注册 1 个服务 + 从浏览器拿 2 个 Cookie：

| # | 密钥 | 获取方式 | 耗时 |
|---|------|----------|------|
| 1 | `X_AUTH_TOKEN` | X 账号 Cookie | 2 分钟 |
| 2 | `X_CT0` | X 账号 Cookie | （同上） |
| 3 | `FEISHU_APP_ID` | open.feishu.cn 创建应用 | 10 分钟 |
| 4 | `FEISHU_APP_SECRET` | （同上） | |
| + | `FEISHU_WEBHOOK_URL` | 飞书群 → 添加机器人 → 获取 Webhook | 2 分钟 |

> 翻译用的是 **Google Translate**（通过 `deep-translator` 库），完全免费，无需注册，无需 API Key。

---

### ① 获取 X Cookie

1. 在电脑浏览器打开 x.com，登录你的账号
2. 按 `F12` 打开开发者工具
3. 进入 **Application**（应用程序）标签
4. 左侧找到 **Cookies** → `https://x.com`
5. 在列表中找两个值：
   - `auth_token` → 复制它的 **Value**，这就是 `X_AUTH_TOKEN`
   - `ct0` → 复制它的 **Value**，这就是 `X_CT0`

> Cookie 可能几个月后过期。如果脚本突然采集失败，第一步就是更新 Cookie。

---

### ② 创建飞书应用 + 机器人

**创建应用：**
1. 打开 open.feishu.cn，用飞书账号登录
2. 点击 **「开发者后台」** → **「创建企业自建应用」**
3. 应用名称填 `X Feed Bot`，图标随便选
4. 创建完成后进入应用详情页

**获取 App ID 和 Secret：**
5. 左侧 **「凭证与基础信息」** → 复制 `App ID` 和 `App Secret`
   - 这就是 `FEISHU_APP_ID` 和 `FEISHU_APP_SECRET`

**开通机器人能力：**
6. 左侧 **「应用功能」** → 找到 **「机器人」** → 点击 **「添加」**
7. 添加后无需额外配置

**添加权限：**
8. 左侧 **「权限管理」** → 搜索并开通以下权限：
   - `im:image`（上传图片）
   - `im:message`（发送消息）
   - `im:resource`（获取消息资源）
9. 点击右上角 **「创建新版本」** → 填写版本号 `1.0.0` → **「发布」**
   - 可能会提示需要管理员审核，你自己就是管理员，直接通过

**获取 Webhook：**
10. 打开飞书客户端 → 创建一个群（或选已有群）
11. 群设置 → **「群机器人」** → **「添加机器人」** → 搜索 `X Feed Bot`
12. 添加后会显示 **Webhook 地址**，格式：
    ```
    https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxxx
    ```
13. 这就是 `FEISHU_WEBHOOK_URL`

---

## 部署到 GitHub

### 第 1 步：创建 GitHub 仓库

1. 打开 github.com/new
2. Repository name: `x-feed-collector`
3. 选择 **Public**（免费无限跑）或 **Private**（每月 2000 分钟也够）
4. 不要勾选任何初始化选项，点 **Create repository**

### 第 2 步：上传代码

在电脑终端执行（把 `你的用户名` 替换掉）：

```bash
cd x-feed-collector

git init
git add .
git commit -m "init: X Feed Collector"

git remote add origin https://github.com/你的用户名/x-feed-collector.git
git branch -M main
git push -u origin main
```

### 第 3 步：添加密钥到 GitHub

1. 打开你的 GitHub 仓库页面
2. 进入 **Settings** → **Secrets and variables** → **Actions**
3. 点击 **New repository secret**，依次添加：

| Name | Value |
|------|-------|
| `X_AUTH_TOKEN` | 你在第①步获取的 auth_token |
| `X_CT0` | 你在第①步获取的 ct0 |
| `FEISHU_APP_ID` | 你在第②步获取的 App ID |
| `FEISHU_APP_SECRET` | 你在第②步获取的 App Secret |
| `FEISHU_WEBHOOK_URL` | 你在第②步获取的 Webhook 地址 |

### 第 4 步：测试运行

1. 进入 **Actions** 标签页
2. 点击左侧 **Collect X Tweets**
3. 点击 **Run workflow** → **Run workflow**（手动触发）
4. 等 1-2 分钟，看到绿勾就是成功了
5. 去飞书群里看消息

---

## 本地测试（可选）

如果你想先在电脑上跑一次试试：

```bash
# 1. 安装 Python 3.11+ （去 python.org 下载）

# 2. 配置环境变量
cp .env.example .env
# 用记事本打开 .env，填入你的几个值

# 3. 安装依赖
pip install -r requirements.txt

# 4. 运行
python main.py
```

---

## 修改目标博主

默认采集 `@Serenity`。要改成其他人：

1. GitHub: **Settings** → **Secrets** → 添加 `TARGET_USERNAME` = 新用户名
2. 本地: 修改 `.env` 中的 `TARGET_USERNAME`
3. 改完后记得重新运行测试

---

## 调整采集频率

在 `.github/workflows/collect.yml` 第 6 行修改 cron：

```yaml
# 每 15 分钟
- cron: '*/15 * * * *'

# 每 30 分钟（默认）
- cron: '*/30 * * * *'

# 每小时
- cron: '0 * * * *'
```

> GitHub Actions 最短间隔建议 15 分钟。太频繁会增加被 X 风控的风险。

---

## 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| X 采集失败 | Cookie 过期 | 重新获取 auth_token 和 ct0，更新 GitHub Secrets |
| 翻译失败 | Google 偶尔限流 | 脚本会自动分段重试，一般都能成功 |
| 飞书发送失败 | App 未发布 / Token 过期 | 去飞书开发者后台检查版本是否发布；权限是否开通 |
| 重复推送 | 去重记录未保存 | 检查 `data/seen_tweets.json` 是否被正常 commit |
| 图片显示不了 | 飞书图床上传失败 | 查看 Actions 日志；检查 `im:image` 权限是否开通 |

---

## 文件结构

```
x-feed-collector/
├── main.py                  ← 主程序入口
├── lib/
│   ├── x_collector.py       ← X 推文采集
│   ├── translator.py        ← Google 翻译（免费无需注册）
│   ├── feishu.py            ← 飞书推送 & 图片上传
│   └── storage.py           ← 去重存储
├── data/
│   └── seen_tweets.json     ← 已处理推文 ID（自动维护）
├── .github/workflows/
│   └── collect.yml          ← GitHub Actions 定时任务
├── requirements.txt
├── .env.example
└── README.md                ← 本文件
```

---

## 成本一览

| 项目 | 服务 | 费用 |
|------|------|------|
| 服务器 | GitHub Actions | 0 |
| 翻译 | Google Translate（deep-translator 库） | 0 |
| 推送 | 飞书机器人 | 0 |
| 图床 | 飞书 IM 图片上传 | 0 |
| **总计** | | **0** |
