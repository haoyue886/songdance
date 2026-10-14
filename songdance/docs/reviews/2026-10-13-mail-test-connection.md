# 2026-10-13 验证码邮件真实接入准备与现场状态

最新续接以 [2026-10-14 真实 OTP 记录](2026-10-14-mail-otp-integration.md) 为准；以下保留本批准备与当时待办，不能将历史空字段视为最新配置状态。

## 客服收发证据已补齐

用户指出客服测试已完成后，主 Agent 直接查看已有邮箱记录，没有重复发送：

- 测试线程 `SongDance support test SD-20261013-01`，21:53 的外部 QQ 来信发给 `support@notavue.io`，已在飞书 `hello@notavue.io` 的收件箱可见。
- 22:04 从 `hello@notavue.io` 返回的同线程回复在飞书“已发送”可见；原生 Mail 的外部 QQ 收件箱也显示该回复，测试 ID 与正文一致。
- 这完成客服别名收信和从主邮箱回复的真实两端验证。没有重新验证 Gmail/Outlook/Yahoo 或 Resend 的发信头部，不能据此勾选完整 MAIL-01/05。
- 私密测试配置的 `SONGDANCE_MAIL_SUPPORT_VERIFIED` 据该证据为 true；通用模板仍默认 false。根域 MX 保留飞书，未重复修改。

## 隔离回调服务

新增 `api/app/mail_hook.py` 和模块入口 `api/scripts/run_mail_hook.py`，使用现有邮件 router、签名合同、发送幂等与抑制逻辑，不复制另一套发送代码。

- 仅有两个 POST 路由 `/webhooks/supabase/email`、`/webhooks/resend`；不加载转录、账户或付款 API，禁用文档/OpenAPI/斜杠重定向。
- 要求显式 `environment=test`、手动迁移、独立配置文件与数据库；启动检查三张邮件表及列，退出 dispose 自有 engine。
- 配置文件只允许所有者读写；只采用文件字段，不从默认 `.env`、进程环境或文件 secrets 补齐，诊断不输出敏感值。
- 专用 `songdance/.env.mail-test.local` 为受忽略的 0600 文件，绑定 `songdance-test` / `amnsavenqfmmvnauyqzi`、本站 `http://127.0.0.1:3002`、发件 `auth@mail.notavue.io`、测试收件 `hello@notavue.io`。
- 数据库为独立 `api/.data/mail-hook-test/mail.sqlite3`，目录 0700，已真实迁移到 014。生成独立稳定 HMAC secret，未触碰原商业测试配置；发送开关 false。

## 已执行验证

在 `songdance/api` 执行：

```sh
.venv/bin/pytest tests/test_mail_hook_listener.py tests/test_mail.py tests/test_mail_migrations.py -q --tb=short
.venv/bin/ruff check app/mail_hook.py scripts/run_mail_hook.py tests/test_mail_hook_listener.py
.venv/bin/python -m compileall -q app/mail_hook.py scripts/run_mail_hook.py
.venv/bin/python -m scripts.run_mail_hook --env-file ../.env.mail-test.local --check
.venv/bin/python -m scripts.run_mail_hook --env-file ../.env.mail-test.local --port 8024
```

- 最终 76 passed，Ruff/编译通过。首轮一项测试用 `app.routes` 枚举 `.path` 与当前 FastAPI 延迟路由结构不兼容；已移除该内部结构假设，实际 HTTP 暴露/拒绝、签名、去重和抑制用例继续覆盖，重跑通过。
- 原有 Starlette/httpx 和 resampy 弃用警告保留。未重跑全量 Web/API、音乐质量或 PostgreSQL 并发。
- 本机真实探测 `/health`、`/docs`、`/openapi.json`、`/me`、`/jobs` 均 404；两个回调在默认关闭状态均 503。
- 离线配置检查格式有效，已验证客服收发，缺 Resend API key 和两条供应商 Hook secret 时退出 2；不以此宣称 ready。
- fresh 独立审查也运行同一 76 项用例，无确认问题，见 [独立证据](2026-10-13-mail-listener-review.md)；不能将两次运行加成 152 个不同用例。

## 工具与临时 HTTPS

按 `agent-reach` 网页路径读取 Cloudflare 官方 Quick Tunnels 和 Downloads 原文：Jina 路径 DNS 失败，直接跟随官方重定向并请求 Markdown 成功。官方明确 Quick Tunnel 仅供测试、地址随进程停止失效、无生产可用性保证、最多 200 个同时请求。

- 官方 GitHub 2026.10.0 arm64 包下载两次未完成，部分文件摘要不匹配，未解压运行。
- 最终从 Homebrew 官方公开包仓库的标准匿名只读流程取得 2026.10.0 arm64_sequoia bottle，SHA-256 `132412d184bd26d56536f951e7cd8d301f2ed8e2c75ef78756970f1c69a45e9a` 与官方包信息一致。仅取包内 `bin/cloudflared` 至 `/tmp/songdance-cloudflared-20261013/cloudflared`，未全局安装；`--version` 确认为 2026.10.0。
- 用户明确授权创建域名受限的发送 key、公开临时两条签名回调并向 `hello@` 联调。
- 22:53 创建 Quick Tunnel，连接注册成功；当前测试 URL 为 `https://hill-climb-inkjet-england.trycloudflare.com`，仅指向本机邮件 listener 的 8024 端口。
- 该 HTTPS URL 的 `/docs`、`/me`、`/jobs` 实际请求均 404，两个空 POST 回调均 503。未绕过 TLS 校验或扩大完整应用暴露。

## 当前凭据与供应商状态

- Supabase Auth Hooks 页面无现有 Hook；Resend 页面此前无 API key、无 webhook。
- 已准备并获明确授权创建 Resend `SongDance Auth Test`，权限 Sending access、域名 `mail.notavue.io`；API Key 一次展示页已可见，密钥未打印到聊天/日志/Git。
- 复制按钮首轮被自动审批拒绝，理由为原授权未明确覆盖系统剪贴板。用户随后明确授权本机复制、粘贴进私密文件、保存和清除。复制按钮显示 Copied。
- TextEdit 的文件对话框无法可靠确认打开；工具另禁止操作 `com.apple.Terminal`。未使用其它应用绕过限制；随后用户回复已保存；主 Agent 只核对该字段存在、格式有效、文件 0600、发送 false。已用普通页面地址替换剪贴板密钥并关闭一次展示页。
- Resend 回调 `57eb8c9c-8e56-40de-b3e3-098023013eed` 已保存，订阅 email.bounced/complained/delivered/suppressed 四项，状态 Enabled；Supabase Send Email HTTPS 表单已填精确 URL 并生成独立 secret，未提交。已请求用户将两家签名 secret 保存到同一私密文件，实际落盘待核对。publishable key 与最小权限会话读取连接仍未配置。尚未启用发送、产生真实验证码或完成真实应用登录；BA-02 与完整 MAIL 项保留待验。

## 应用登录配置准备

已另建受忽略、0600 的 `songdance/.env.auth-mail-test.local`，本地站点仍为已确认的 `http://127.0.0.1:3002`，API 仅本机 8002，业务库/存储隔离到 `api/.data/auth-mail-test/`，独立 bridge secret 已生成；AUTH 和所有收费/用量开关保持 false。离线 `scripts.check_auth_config` 实际退出 2，只报告 publishable key 和 auth session database DSN 两项 REQUIRED。尚未创建/授权真实 session reader LOGIN 角色，未启动该本地 BFF/API，不以假的 DSN 绕过会话撤销查询。

## 续接步骤与回退

1. 用户将已复制的 Resend key 保存到私密文件后，只检查字段是否已配置、文件仍 0600，不输出值；清除剪贴板中的凭据。
2. 配置公开 HTTPS `/webhooks/resend`（订阅 delivered/bounced/complained/suppressed）和 Supabase Send Email Hook `/webhooks/supabase/email`，将独立 provider secrets 受控存入本机私密文件；签名拒绝和抑制仍用当前实现。
3. 字段齐全后离线检查再启用专用测试发送开关，首先向 `hello@` 发码，验证送达、Supabase OTP 验证/过期/复用；应用 BFF 登录还要求真实 publishable key 和经权限核验的会话读取连接，不能跳过会话撤销查询。
4. 结束测试前先禁用 Supabase Send Email Hook，再停止本任务 cloudflared/listener，保留隔离数据库、HMAC 与发送墓碑；重启 Quick Tunnel 会更换 URL，必须同步两个 provider callback。已创建的受限 key 可保留用于下一次授权测试，不自动删除凭据。

官方依据：

- https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/
- https://developers.cloudflare.com/tunnel/downloads/
- https://api.github.com/repos/cloudflare/cloudflared/releases/latest
- https://formulae.brew.sh/api/formula/cloudflared.json
