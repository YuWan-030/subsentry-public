# SubSentry

SubSentry 是一个开源的 3x-ui 订阅客户管理面板，用来集中管理客户、节点、订阅链接、续费记录、流量状态、通知推送和操作日志。

它适合正在使用 3x-ui 做订阅服务管理、但又希望有更清晰客户资产视图和到期提醒能力的个人、团队或工作室。

[![License](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![Backend](https://img.shields.io/badge/Backend-FastAPI-009688.svg)](backend)
[![Frontend](https://img.shields.io/badge/Frontend-React%20%2B%20Ant%20Design-1677ff.svg)](frontend)

## 主要能力

- 客户资产管理：创建、编辑、删除、续费、重置流量、批量修改客户资料。
- 3x-ui 节点接入：维护多个 3x-ui 节点，读取入站、测试连接、探测节点状态。
- 订阅链接管理：支持标准订阅、JSON、Clash 链接展示、复制和二维码。
- 流量与到期状态：展示总流量、已用流量、剩余流量、IP 限制、启用状态和到期状态。
- 流量倍率：支持客户级流量倍率，可用于按倍数扣减流量的场景。
- 续费记录：记录客户续费操作、续费天数、旧到期时间、新到期时间和续费价格。
- 收入看板：展示今日、本周、本月收入和趋势图。
- Webhook 通知：支持到期提醒、流量不足提醒、客户停用提醒、节点异常提醒。
- 日志中心：查看客户审计、通知发送结果、活动日志和失败通知重试。
- 多用户权限：管理员和普通用户分权，普通用户只能维护自己名下客户。
- 系统健康页：查看后端、数据库、节点探测、通知检查和自动任务状态。
- 首次安装向导：新数据库自动进入 `/install`，引导创建管理员并配置站点。
- 移动端适配：支持手机浏览器使用，也支持添加到主屏幕作为 Web App 打开。

## 技术栈

- 后端：FastAPI、SQLite/MySQL、Requests、WebAuthn
- 前端：React、Vite、Ant Design、Axios、ECharts
- 部署：Nginx、systemd、Linux 一键安装脚本

## 快速开始

### Linux 一键安装

全新 Linux 服务器可以使用下面的命令自动安装依赖、构建前端、写入 `.env`、配置 systemd 和 Nginx。

```bash
curl -fsSL https://raw.githubusercontent.com/YuWan-030/subsentry-public/main/scripts/install-linux.sh | sudo env SUBSENTRY_REPO_URL=https://github.com/YuWan-030/subsentry-public.git bash
```

安装完成后，根据脚本输出的地址访问面板。第一次打开会进入 `/install` 安装向导，用于创建管理员账号和配置站点信息。

### 本地开发运行

```bash
git clone https://github.com/YuWan-030/subsentry-public.git
cd subsentry-public
cp .env.example .env
```

启动后端：

```bash
cd backend
pip install -r requirements.txt
cd ..
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 4398
```

启动前端：

```bash
cd frontend
npm install
VITE_API_BASE_URL=http://127.0.0.1:4398 npm run dev
```

浏览器打开 Vite 输出的地址。全新数据库会自动跳转到安装向导。

## 环境要求

- Python 3.10+
- Node.js 20+
- SQLite 或 MySQL 5.7+/8.0+
- 可访问的 3x-ui 面板 API

Passkey 需要 HTTPS 或 localhost 等安全上下文。生产环境建议使用 HTTPS。

## 安装向导

首次启动时，如果当前数据库中没有管理员账号，系统会自动进入 `/install`。

安装向导会引导完成：

1. 选择数据库：SQLite 或 MySQL。
2. 配置数据库连接：MySQL 需要填写地址、端口、用户名、密码和数据库名。
3. 测试并保存数据库配置。
4. 创建第一个管理员账号。
5. 配置站点 URL 和默认 Webhook。

切换数据库类型或修改数据库连接后，通常需要重启后端，再刷新安装页继续后续步骤。

## 配置说明

完整配置示例见 [.env.example](.env.example)。

```bash
SUBSENTRY_DB_TYPE=sqlite
SUBSENTRY_SQLITE_FILE=subsentry.db
SUBSENTRY_SECRET_KEY=change-me-to-a-long-random-string
SUBSENTRY_CRON_TOKEN=change-me
SUBSENTRY_CORS_ORIGINS=http://127.0.0.1:5173

SUBSENTRY_MYSQL_HOST=127.0.0.1
SUBSENTRY_MYSQL_PORT=3306
SUBSENTRY_MYSQL_USER=subsentry
SUBSENTRY_MYSQL_PASSWORD=change-me
SUBSENTRY_MYSQL_DATABASE=subsentry

SUBSENTRY_PUBLIC_SUBSCRIPTION_BASE_URL=http://your-domain.example.com:10883
SUBSENTRY_DEFAULT_WEBHOOK_URL=
```

## 生产部署建议

```bash
cd frontend
VITE_API_BASE_URL=https://your-domain.example.com npm run build
```

```bash
uvicorn backend.app.main:app --host 127.0.0.1 --port 4398
```

建议使用 Nginx 或 Caddy 对外提供 HTTPS，并将 `/api/` 反向代理到后端。

## 使用流程

1. 进入 `/install` 创建第一个管理员账号。
2. 在“节点集群”中添加 3x-ui 节点，填写面板地址、端口、API Token 和订阅路径。
3. 测试节点连接，确认可以读取入站和订阅配置。
4. 在“用户管理”中创建普通用户或客户经理账号。
5. 在“客户管理”中添加客户，选择节点、入站、到期时间、流量和续费价格。
6. 在客户详情中查看订阅链接、续费记录、审计记录和通知历史。
7. 在“系统设置”中配置 Webhook、通知模板、推送策略、公告和备案号。
8. 在“系统健康”和“日志中心”中查看自动任务、节点状态和通知结果。

## 开发

```bash
python -m compileall backend
cd frontend
npm run build
```

## 安全提醒

- 不要提交真实 `.env`、数据库文件、管理员密码、Webhook Key、OnAuth Secret 或 3x-ui API Token。
- 生产环境必须修改 `SUBSENTRY_SECRET_KEY` 和 `SUBSENTRY_CRON_TOKEN`。
- 建议通过 HTTPS 暴露面板，不要直接把后端端口裸露到公网。
- 请定期备份数据库。
- 给 3x-ui API Token 授予最小必要权限。

## 贡献

欢迎提交 Issue 和 Pull Request。UI 改动建议附带截图或录屏，方便 review。

## 许可证

SubSentry 基于 [Apache License 2.0](LICENSE) 开源。

版权所有 © 鱼丸工作室。
