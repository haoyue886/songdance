# ADR 0001 — Supabase Auth 与服务端会话边界

日期：2026-09-30。决策状态：采用；Phase 38.1 已有本地实现与隔离验证，尚未接入真实 Supabase 项目、Google 或 SMTP。配置步骤见 `../auth-setup.md`。

## 决策与范围

选择托管 Supabase Auth 提供 Google OAuth 和邮箱一次性验证码。不自建密码系统，不将业务 PostgreSQL、Redis 或对象存储迁到 Supabase；业务用户、任务所有权和权益继续由 FastAPI/SQLAlchemy 管理。Supabase 用户以 `(issuer, subject)` 映射内部用户，email 仅为已验证资料，不按同邮箱字符串合并业务用户。

Supabase 是此前讨论的候选，已核对官方的 Google、邮箱 OTP、JWT/JWKS、会话与 SMTP 合同，满足这两种登录方式。此选择不证明价格、地区连通性、实际邮件送达或生产开户已经通过。生产项目应与 API 优先选相近区域，实际区域和费用由真实账户配置记录；不据免费套餐推算正式月成本。

## 浏览器、BFF 与 API

1. Next.js 的 `/api/auth/*` 处理发码、验证、OAuth 开始/回调、刷新、登出；这些路径排除 locale rewrite，使用站内 allowlist 返回路径。API 别名不接受浏览器指定任意上游 URL。
2. 在 Next.js 服务端使用官方 Supabase JS/SSR 客户端。refresh token 与会话 Cookie 设为 HttpOnly、Secure（HTTPS）、SameSite=Lax、Path=/；不交给浏览器 Supabase Auth 客户端，也不写 localStorage。公开页面保持原缓存策略，认证/账号/回跳响应使用 `Cache-Control: private, no-store`，不得缓存 Set-Cookie。
3. HttpOnly Cookie 的读取/更新由 BFF 承担。SDK 的 refresh-token 请求委托 FastAPI `/auth/bridge/refresh`，由现有 API 私网 Redis 做跨实例锁及 10 秒加密结果缓存；Next.js 不直连私网 Redis。桥接仅接受独立服务端 secret，不作为浏览器接口。BFF 保留完整 Cookie 分片，失败提示重新登录，不悄悄使用游客身份。
4. `POST /api/auth/access-token` 在校验本站 Origin/CSRF 及服务端用户后，向同源浏览器返回短期 access JWT 与过期时间；refresh token 永不出现在该 JSON。浏览器只在内存保存 access JWT，过期通过 BFF 刷新。此端点不因 `getSession()` 返回了 user 就授权，必须先验证身份。
5. 浏览器继续直传音频到 FastAPI，并携带 `Authorization: Bearer`；音频上传不经过 Next.js BFF。如此保持现有大文件传输路径；BFF 仅承担小体积认证请求。FastAPI CORS 须定向允许 Authorization，不能用 `*` 或把第三方 Cookie 当认证前提。
6. 所有登录态任务请求统一进入 FastAPI 鉴权依赖；以有效 JWT、供应商会话状态、本地用户状态及 owner 决定访问。有效游客凭证是另一条明确分支，伪造/过期登录凭证不能回退游客。

这是本项目的服务端刷新 + 浏览器短期访问凭证方案，不代表 Supabase 默认 SSR Cookie 已满足 HttpOnly。本批核验并锁定 `@supabase/ssr 0.12.7`、`@supabase/supabase-js 2.117.2`、`PyJWT 2.15.1` 和 `cryptography 50.0.1`；Python 3.11 本地验证通过，容器/真实供应商联调尚未执行。

## JWT 与撤销

- 新项目选非对称签名；FastAPI 使用成熟 JWT 库及项目固定 JWKS URL，验证算法白名单、签名、issuer、audience=`authenticated`、exp、sub 和 session_id。JWKS 缓存须有界、支持轮换，不能按未验证 JWT 的 jku/issuer 请求任意 URL，不手写密码算法。
- 官方明确说明：签名/有效期正确不代表用户尚未退出。登出后旧 JWT 可能继续存在；需要核查 `session_id` 对应的 `auth.sessions` 行。不能将本地验签或 `getUser()` 成功直接视为已经完成会话撤销检查。
- 使用只给 API 的独立、最小权限 Supabase PostgreSQL 凭据检查会话行，按已经验签的 session_id 与 user_id 参数化查询；只读所需会话字段，不给浏览器或 Worker，也不让它访问业务账本。账号暂停/删除仍检查本地业务状态。
- 最小权限角色模板位于 `../../infra/supabase-session-reader.sql`；本地隔离 PostgreSQL 已验证会话查询、撤销、过期及密码列/写权限拒绝。会话查询失败返回 503，不能放行或降级游客。供应商时长/空闲限制须与 API 配置匹配，并在真实项目验证后开启；不能仅凭延迟清理的行存在视为有效。
- 登出调用供应商撤销并清 Cookie；先响应登出成功后再“稍后撤销”不满足合同。删除账号沿用先核验停止续费的业务流程。
- JWT 在接收请求时验证；RQ 的长转录按已接收任务、归属和预占记录运行，不把用户 token 存进队列或要求它整个推理期间有效。再次查询/下载须重新鉴权。

## Google 与邮箱配置

- Google 仅请求身份所需的 openid/email/profile。Google 控制台的授权回调指向 Supabase 项目 callback，Supabase 的回跳 allowlist 再指向本站 `/api/auth/callback`；两层 URL 不能混填。PKCE、OAuth state/nonce 使用供应商/SDK 受支持流程并由 BA-02 验证，不手写简化流程。
- 邮箱 OTP 通过供应商发送和验证。官方 `signInWithOtp` 默认模板可能发链接，需要把邮件模板改为 `{{ .Token }}` 才是界面的数字验证码；设置有效期 600 秒。供应商后台配置与应用的 60 秒重发、每邮箱每小时 5 次、每挑战最多 5 次尝试分别验证，不能认为 SDK 自动提供了全部产品限额。
- 2026-10-07 邮件交付增量：用户选定 Resend 免费层与 API 集成。采用 Supabase Send Email Hook 调用 Resend API，保留 Supabase 的 OTP 生成/验证；此主路径替代原自有 SMTP 方案，启用 Hook 时不再并行使用 SMTP。Hook/API 代码和实际域名尚未配置验证，准备见 `../resend-setup.md`。发送密钥和 Hook secret 仅放在受控服务端，不进入浏览器、聊天或普通日志；Google Client Secret 仍只用于供应商后台。
- 默认 SMTP 仅适合项目团队测试地址，不作为公众发码方案。原 `{{ .Token }}` SMTP 模板要求只适用于未启用 Hook 的路径；API 路径由签名 Hook 中的 OTP 渲染邮件，不能把 SMTP 模板编辑和 API Hook 双重列为前置条件。
- 应用侧按邮箱摘要、可信客户端 IP 和全局配额限流，统一错误响应避免邮箱枚举；还需启用供应商侧保护，不能假设经过 BFF 就无法绕过。服务器聚合 IP 的供应商限额须实测，调整只按官方支持的配置执行，不转发未经验证的 X-Forwarded-For。

## 接口合同（已本地实现，真实供应商待验）

| 路径 | 行为与权限 |
|---|---|
| POST /api/auth/email/start | 邮箱与站内 return path；Origin/CSRF、限流；只返回统一发码状态/重试时间 |
| POST /api/auth/email/verify | 验证挑战和 OTP；成功设置 HttpOnly Cookie，返回最小用户资料，不返回 refresh token |
| POST /api/auth/google/start | Origin/CSRF；产生 PKCE 跳转，绑定回跳状态 |
| GET /api/auth/callback | 校验 OAuth/PKCE 回调；兑换会话并仅回到 allowlist 站内路径 |
| POST /api/auth/access-token | 已有会话、Origin/CSRF、no-store；仅短期 access JWT/到期时间，用于直连 FastAPI |
| POST /api/auth/logout | Origin/CSRF；撤销会话、清 Cookie 和客户端内存凭证 |
| GET /me（FastAPI） | 完整鉴权；返回内部用户，不接受浏览器指定 user_id |
| 既有 jobs/downloads/events | 统一鉴权和 owner/capability 校验，不能只补登录页 |

新游客任务的随机访问凭证只在创建响应发出，API 仅存摘要；浏览器放在当前页内存/sessionStorage，通过 `X-Job-Access` 访问和认领。旧无独立凭证的匿名任务兼容读取，但不能仅凭 job_id 认领。认领以原子条件更新写入 owner，过期时间不变；私有/新游客任务不再展示旧的裸 URL 分享按钮。签名文件 URL 保留既有短期有效合同，签发入口检查所有权，删除后立即失效。

OTP 预算和挑战同样走 server-only bridge，在 Redis 中按邮箱摘要、IP 与全局限制协调；验证码有效期由供应商配置为 600 秒，应用挑战 600 秒且最多尝试 5 次。账户相关的供应商 4xx 不向浏览器暴露区别，提示只承诺“如果该邮箱可接收”；基础设施失败和限流分别展示错误。只有 Vercel 环境采用平台提供的客户端 IP，缺少可信地址时保守共用限流桶，不接受浏览器 JSON 指定 IP。

关键失败路径：供应商拒绝/超时、验证码重用与暴力尝试、并发刷新、开放重定向、不同 issuer、伪造 JWT、已撤销 session、跨用户访问、登录态丢失不能匿名降级、大文件直传与 token 过期后恢复。

## 配置交付与完成边界

变量模板：`../../infra/env.auth.example`。认证运行/构建开关默认关闭；配置真实测试环境后才显式打开，不因代码合入就改变生产行为。离线格式检查：在 api/ 执行 `python -m scripts.check_auth_config --env-file ../infra/env.auth.example`；未填模板预期退出 2，只输出字段名/错误代码，不打印凭据。

38.0 的选型与模板保留；38.1 已实现 SDK/BFF、JWT/会话门禁、迁移 006、用户归属、游客认领与登录/账户 UI。真实项目 URL/key、Google/SMTP、生产 TLS Cookie 和供应商会话策略仍需实际联调。38.2 的月度用量/收费未实现；仅开启 AUTH 时仍沿用原免费运行限流，不宣称已执行商业化的 Free 月额度。删除账号与停止续费依赖后续收费闭环，BA-13 尚未完成。

## 官方核验

核验于 2026-09-30；从 Supabase 官方仓库内容 API 读取原文。以下为本次使用的路径，不把历史会话摘要当当前资料。

- `https://github.com/supabase/supabase/blob/master/apps/docs/content/guides/auth/auth-email-passwordless.mdx`：OTP 模板、发码与验证。
- `https://github.com/supabase/supabase/blob/master/apps/docs/content/guides/auth/social-login/auth-google.mdx`：Google provider 与两层 callback 配置。
- `https://github.com/supabase/supabase/blob/master/apps/docs/content/guides/auth/jwts.mdx`：JWKS、非对称签名验证与缓存。
- `https://github.com/supabase/supabase/blob/master/apps/docs/content/guides/auth/sessions.mdx`：session_id、刷新、退出后的会话检查及 HttpOnly 限制。
- `https://github.com/supabase/supabase/blob/master/apps/docs/content/guides/auth/auth-smtp.mdx`：默认邮件服务限制与自有 SMTP。
- `https://github.com/supabase/supabase/blob/master/apps/docs/content/guides/auth/rate-limits.mdx`：供应商限流与代理 IP 配置边界。
