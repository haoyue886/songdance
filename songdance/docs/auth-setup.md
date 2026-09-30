# 认证测试环境接入

状态：本地代码已实现，真实供应商尚未配置或联调。先在隔离 staging 验证，不直接开启正式网站的登录或收费。

## 1. 应用与数据库

- Web 安装锁文件：在 `web/` 执行 `pnpm install --frozen-lockfile`。API 使用更新后的 `pyproject.toml` / `requirements.lock`；部署镜像仍使用锁定依赖。
- 在业务数据库执行 `alembic upgrade head`，迁移 006 新增 users/auth_identities 与 nullable job owner/guest secret 摘要。旧任务不凭空归属新账号。
- 一旦已有受保护任务，不可回滚到不校验所有权的旧应用；迁移降级也会拒绝仍有受保护任务的库，避免回滚后公开私有任务。事故优先关闭新登录/提交并使用兼容版本修复；关闭 AUTH 不会让现有 owner/guest 门禁失效。

## 2. Supabase 项目

- 为本环境创建/选择独立项目，采用非对称 JWT 签名。使用 project URL 与现代 publishable key；不复制 JWT shared secret、service_role 或管理员 key 到浏览器。
- 启用 Google，配置 Google 的 Supabase callback 与 Supabase 的本站回跳 allowlist。本站回跳固定 `/api/auth/callback`；测试/生产域名分别配置，return path 由应用白名单控制。
- 配置自有 SMTP 与 OTP 邮件模板 `{{ .Token }}`，有效期 600 秒；真实验证发码、错误/过期/复用、送达和重发预算。默认 SMTP 不能被当成正式公众邮件服务。
- 按 `../infra/supabase-session-reader.sql` 给专用 LOGIN 角色授予只读会话字段权限；角色名称本身不证明最小权限，实际测试禁止读取密码列或修改数据。其 TLS 连接只配置到 FastAPI。
- 如开启 provider time-box/inactivity，必须同步 `SONGDANCE_AUTH_SESSION_MAX_AGE_SECONDS` / `SONGDANCE_AUTH_SESSION_IDLE_SECONDS` 并实测到期；默认 0 表示未开启该额外策略。

## 3. 环境变量和打开顺序

使用 `../infra/env.auth.example` 作为键名清单，将实际值放在部署平台或本地未提交环境文件；不要把填好的文件提交或发送到聊天。

| 配置 | 所属服务 |
|---|---|
| NEXT_PUBLIC_SITE_URL / NEXT_PUBLIC_AUTH_ENABLED | Web；AUTH 是构建期变量，变更需重建 |
| SONGDANCE_AUTH_ENABLED | Next.js 服务端与 API；默认 false |
| SONGDANCE_AUTH_API_URL | Next.js 服务端，指向固定 API origin |
| SONGDANCE_SUPABASE_URL / SONGDANCE_SUPABASE_PUBLISHABLE_KEY | Next.js 服务端与 API |
| SONGDANCE_AUTH_BRIDGE_SECRET | Next.js 服务端与 API；独立随机 32–128 字符 base64url/hex，不能加 NEXT_PUBLIC 前缀 |
| SONGDANCE_AUTH_SESSION_DATABASE_URL | 仅 API；最小权限 Supabase 会话连接，不是业务数据库连接 |
| SESSION_MAX_AGE / SESSION_IDLE（完整键名见模板） | 仅 API；与 provider 策略一致 |
| SONGDANCE_REDIS_URL / SONGDANCE_QUOTA_NAMESPACE | API 沿用现有 Redis，隔离环境命名空间 |

不要将身份/bridge/会话连接凭据复制给 Worker/Cleanup。Next.js 不需要暴露私网 Redis；刷新请求由 API 在 Redis 中协调。生产禁止内存协调后端。

先保持开关关闭并运行离线检查，填齐后在 staging 同步启用 API/服务端 AUTH 与 Web 构建期 AUTH。更新 API 的精确 CORS origin，确认只允许需要的 Authorization/X-Job-Access 头。Next.js 的 BFF 写请求只接受配置的本站 Origin，错误的 Preview Site URL 会被拒绝。

当前 AUTH-only 测试版提供身份与私有任务，不提供 Creem 付款、月额度账本或账户删除/停止续费闭环。UI 明示尚未启用收费和月用量；这些按 Phase 38.2–38.4 完成后再进入商业化验收。

## 4. 可运行验证

```sh
# api/
.venv/bin/pytest tests/test_auth_ownership.py tests/test_auth_coordination.py tests/test_migrations.py -q
SONGDANCE_TEST_REAL_AUTH_SERVICES=1 .venv/bin/pytest tests/test_auth_real_services.py -q
# web/
pnpm exec vitest run src/lib/auth/server.test.ts src/lib/auth/client.test.ts src/lib/api/jobs.test.ts
pnpm test:auth:ui
```

真实服务测试自己建立临时 PostgreSQL/Redis，不连接已有数据库；需本机 initdb/pg_ctl/redis-server。浏览器 smoke 使用真实 SDK、隔离 Next.js 和本地协议替身，自动关闭自己的进程；不访问 Google、Supabase 或邮件服务，也不证明真实账户已联通。

真实 staging 另需验证 Google/邮箱登录、Cookie Secure/HttpOnly、过期/后台撤销、跨设备、跨用户请求、匿名认领竞争、退出后旧 JWT 拒绝、旧签名下载 TTL 边界，以及私有页面/响应不缓存。补齐证据前不勾选 BA-02/11/13 或宣布生产就绪。
