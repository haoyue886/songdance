# 认证测试环境接入

状态：指定测试项目已通过真实邮件 OTP 和 Google 登录、Next.js BFF、FastAPI 会话查询、账户页及退出撤销联调。本机测试服务与临时邮件入口已关闭，Google 测试 provider 保留；完整 MAIL/BA、Google 品牌审核和生产验收继续待补。现场证据见 [OTP 联调记录](reviews/2026-10-14-mail-otp-integration.md) 与 [Google 联调记录](reviews/2026-10-14-google-oauth-integration.md)。

## 1. 应用与数据库

- Web 安装锁文件：在 `web/` 执行 `pnpm install --frozen-lockfile`。API 使用更新后的 `pyproject.toml` / `requirements.lock`；部署镜像仍使用锁定依赖。
- 在业务数据库执行 `alembic upgrade head`，迁移 006 新增 users/auth_identities 与 nullable job owner/guest secret 摘要。旧任务不凭空归属新账号。
- 一旦已有受保护任务，不可回滚到不校验所有权的旧应用；迁移降级也会拒绝仍有受保护任务的库，避免回滚后公开私有任务。事故优先关闭新登录/提交并使用兼容版本修复；关闭 AUTH 不会让现有 owner/guest 门禁失效。

## 2. Supabase 项目

- 为本环境创建/选择独立项目，采用非对称 JWT 签名。使用 project URL 与现代 publishable key；不复制 JWT shared secret、service_role 或管理员 key 到浏览器。
- 启用 Google，配置 Google 的 Supabase callback 与 Supabase 的本站回跳 allowlist。本站回跳固定 `/api/auth/callback`；测试/生产域名分别配置，return path 由应用白名单控制。2026-10-14 已创建 Notavue Auth Test / Notavue Web Test，以三项基本身份 scope 和单一测试用户取得真实登录/退出证据；应用保持 Testing，Client Secret 仅配置在 Supabase。选择器仍显示默认 Supabase 认证域名，正式品牌呈现另行验证。
- 同日 Creem Test 联调发现供应商拒绝 `127.0.0.1` success URL，经用户授权将本机商业测试站点与 Supabase Site URL 改为 `http://localhost:3002`，allowlist 增加精确 `http://localhost:3002/api/auth/callback`，原 127.0.0.1 条目保留。localhost Google/BFF 实际登录通过；Google 至 Supabase 的 provider callback 未改，未加通配符。详见 [Creem Test 联调记录](reviews/2026-10-14-creem-test-integration.md)。
- 邮件交付按 [Resend 接入准备](resend-setup.md) 的 Supabase Send Email Hook/API 主路径实施，OTP 有效期 600 秒；真实验证发码、错误/过期/复用、送达和重发预算。Hook 未启用时，供应商仍走其默认邮件配置；2026-10-14 测试项目已取得真实供应商 OTP、BFF/账户页与退出撤销证据，本轮 Hook 已禁用、限额页面恢复 2/h；完整邮件验收仍待补齐，见 [联调记录](reviews/2026-10-14-mail-otp-integration.md)。若改用 SMTP 才需自有 SMTP 与 `{{ .Token }}` 模板，不能同时要求或启用两套发信。
- 本测试项目保留供应商默认的 8 位 OTP；应用仅接受 6 或 8 位 ASCII 数字，保留旧 6 位项目兼容，不截断、去空白或转换成数字。输入框和 BFF 共用格式，最终由供应商验证；应用接受 6 位格式不代表能通过配置为 8 位的供应商验证。2026-10-07 控制台显示默认模板发送登录链接、配置自有 SMTP 后才能编辑模板，不能仅配置位数就宣称已支持真实邮箱验证码登录。
- 会话读取只允许 sessions 的 id/user_id/created_at/refreshed_at/not_after、users 的 id/email_confirmed_at/banned_until/deleted_at，共 9 个字段。可以转授 `auth` schema USAGE 的环境使用 `../infra/supabase-session-reader.sql`。若托管 Supabase 的 `postgres` 没有该 schema 的 GRANT OPTION，单条 GRANT 可能只警告而无实际授权；改用 `../infra/supabase-session-reader-views.sql`，由已有迁移角色创建私有 `songdance_auth` schema 的两张视图，并设置 `SONGDANCE_AUTH_SESSION_SCHEMA=songdance_auth`。视图保留默认由所有者检查底层权限的语义，专用账号仅有这两张视图的 SELECT，无需加入 anon/authenticated/service_role/admin。不要把私有 schema 加入 Data API exposed schemas。原 `auth` 直读仍为兼容默认。
- 把 `songdance_auth_reader` 授予专用 LOGIN 角色；不在 SQL 文件中创建或保存密码。角色名称本身不证明最小权限，实际连接应验证 TLS、9 个字段可读、密码列和写操作被拒绝，以及真实会话撤销立即生效；私有视图方案另需确认 reader 无底层 auth schema USAGE。其 TLS 连接只配置到 FastAPI。
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
| SONGDANCE_AUTH_SESSION_SCHEMA | 仅 API；`auth`（兼容默认）或 `songdance_auth`（私有视图），不接受任意 schema |
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

## 5. 游客体验与周期任务摘要（本地实现）

迁移 011 增加游客身份摘要、UTC IP 日准入、提交墓碑和一次成功账本；需先执行 `alembic upgrade head`。`SONGDANCE_GUEST_USAGE_ENABLED=false` 默认关闭，开启要求认证、用量与可靠派发同时启用，以及 API 独立的 `SONGDANCE_GUEST_SIGNING_SECRET`（至少 32 字符）。所有 API 实例必须使用同一稳定密钥，保存在环境密钥管理中，不进浏览器或日志。Worker/Dispatcher 结算只需共享账本，不需要游客签名密钥。

浏览器使用 localStorage 保存服务端签名访客标识，存储受限时仅当前页内存保留。它不等同自然人或登录会话，清浏览器存储、换 IP 可绕过尽力控制。API 按可信代理配置解析 IP，再保存 HMAC 摘要；上线前必须验证代理跳数/CIDR，不能信任任意 X-Forwarded-For。共享出口会共享日名额。游客成功额度与 IP 日名额独立，已接受任务失败只退成功体验，原任务最多两次重试，不额外占日名额。

关闭游客/可靠派发的新准入开关后，已有任务仍按原预占结算；带原访客签名和 key 的已接受提交仍可找回原任务。保留原签名密钥及 schema，并继续运行 Dispatcher/Worker 排空，不能降级删除历史。当前没有多密钥轮换兼容：更换游客密钥会使旧访客签名及其重放失效，也会改变 IP 日摘要；必须暂停准入、处理在途任务并评估额度重置影响后才安排轮换，不把普通重启当轮换。

账户摘要只计当前权益预占周期中的任务，重试按 job 合并，失败/取消单独标明；24 小时清理不删除摘要与额度记录。已认领游客任务不转入 Free/Pro 周期。游客长期防滥用摘要与账务保留政策须在生产隐私审查中确定，当前不自动清除这些防重复记录。

## 6. Notavue 账户删除（本地实现）

迁移 013 新增删除申请和逐订阅核验记录。`SONGDANCE_ACCOUNT_DELETION_ENABLED=false` 默认关闭，启用要求 auth/usage/reliable queue 一起开启。账户页面按服务端开关展示删除确认；`DELETE /me` 要求本站 Origin、Bearer 和 JSON `{"confirmation":"DELETE"}`，按本人账户幂等保存。近期确认以已验签 `session_id` 对应的 Supabase `auth.sessions.created_at` 为准，最近 10 分钟内的新登录会话可申请；JWT 刷新时间和浏览器时间不能替代。现有只读身份连接已经具备该列权限，无需增加管理员凭据。

运行独立 `python -m app.jobs.account_deletion --loop`，每 15 秒处理持久申请。先核对未决 checkout 和完整顾客订阅列表，所有订阅必须与该用户的合法 Test 绑定一致；逐一取消并 GET 确认停止未来续费。未核实的付款、订阅或环境转重试/审查，邮箱及账户暂保留。核验通过后持久切换 cleanup 并停用业务访问，下一批清理临时任务、源文件/导出及邮箱。清理失败保留终态栅栏与额度释放，可继续恢复；不会复活已清理账户。

申请后暂停新任务、重试、认领与购买；进度可通过已验证原身份的 `GET /me`、`GET /me/deletion` 查询。尚有退款/其他必要账务记录不等于自动退款，账号删除不返还已经消费额度。必要身份映射、交易、用量、删除审计继续保留，避免重新登录或换邮箱重获额度。此流程停用 Notavue 业务账户，不删除 Google 账户，也不物理删除 Supabase 用户。生产保留期限及最终匿名化规则仍待运营确认。

请求结果未知时先 GET 查进度，前端不自动重复删除请求。8 次连续故障后转 review，成功批次不消耗故障预算；排除原因后本人可重新登录并确认，或管理员用 `python -m app.jobs.account_deletion --once --replay-id=LOCAL_ID` 继续原申请，累计 attempts 保留并重置连续故障预算。参数使用等号兼容前导短横线。关闭新申请开关后继续运行兼容 Worker 排空，不降级删除历史。

取消完成到清理之间的平台外部重新激活或迟到绑定，收到并核实状态后会重新进入 billing，不恢复业务访问。供应商取消/订阅枚举没有本地数据库事务能力，真实 Test 仍须核验竞态、列表字段及取消后状态。Google/邮件基础真实登录与退出撤销已验证；跨设备重新登录、后台撤销及完整生产策略继续待验。

2026-10-15 指定范围补验：真实Creem客户列表两份canceled订阅可按当前分页合同读取，遇本地未绑定订阅时先拒绝清理且不取消任何订阅。另在全新无账单验收库中，以真实Google最近登录会话发起用户确认的删除，分批停用/清理合成任务与邮箱；身份与已用1次墓碑保留，真实重新登录仍显示停用，无新额度。原两份付款账本未变，115项定向/14项隔离PG回归和独立审查通过。之后已补生产临时目录本地整链，以及原账本独立副本中已退款/canceled订阅的限定删除，历史投影冲突仍保留；active停费及正常完整账本删除继续待验。详见 [删除验收记录](reviews/2026-10-15-account-deletion-acceptance.md)、[临时目录](reviews/2026-10-15-account-temp-cleanup.md)与[已退款副本](reviews/2026-10-15-paid-account-deletion.md)。

同日真实双身份任务检查已完成：原Google与邮箱登录，30个请求验证自有查询/下载、跨身份控制拒绝、显式游客夹具认领和旧cap失效。fresh审查及18项相关回归通过，唯一剩余授权验证码已使用。收费关闭、账单/Portal及真实并发认领等仍待验，不整体勾选BA-11；临时Hook/入口和本轮服务已关闭，测试页已移除，见 [双身份验收](reviews/2026-10-15-two-account-acceptance.md)。

2026-10-19 已补一个既有退款客户绑定、一个无绑定身份的真实账单/Portal隔离：query不切owner、越权body422、邮箱Portal409、Google只生成原客户一次Portal，初始10请求通过。错误响应缓存头现场缺失已局部修复，6回归及45项相关检查/fresh审查通过，邮箱另5请求重验均private/no-store；原四库与8财务表未变。1封本轮新授权邮件已用，Hook、临时入口和自有服务全部关闭；两个不同付费客户、并发认领等完整BA-11仍待补，见 [账单隔离](reviews/2026-10-19-billing-isolation.md)。

同日并发认领的本地PG三轮、runtime离线预检及独立审查通过；真实尝试受IAB切页未携带会话Cookie、改Chrome无痕时补充邮件直连失败阻断。用户确认未收到，unknown发送不自动重试，真实claim为0。Hook禁用、全部本轮服务停止，3未认领合成夹具和来源库完整；新增的两次邮件授权均视为已尝试，续接先做不发信的网络/会话预检。见 [并发准备与阻塞](reviews/2026-10-19-claim-race-preparation.md)。

最新续接覆盖上述阶段状态：显式本机测试代理发送成功，用户已在Chrome无痕登录、普通Google身份也确认；60秒锁前同步器超时，失败后3任务仍未认领，改180秒后未开始。自动审批服务持续403阻断后续核对与停服；Hook已确认禁用、mail/Tunnel已发SIGTERM，public页移除，但Web/API/Redis/新PG与两个浏览器会话当前状态未知，不能称全部关闭。须先按验收记录中的持久停服脚本收尾或恢复审批。无剩余发送授权，真实并发未通过。

后续用户已手动收尾并确认退出测试会话；shutdown记录Web/Redis/PG停止、邮件/Tunnel已停止、API not_started，PG pid文件与public页已移除。独立端口探测仍受审批403阻断，未冒称通过。最新状态见同一验收记录的收尾补记。

**最终补验通过**：自动审批恢复后五端口关闭检查通过，发现Chrome普通Google与无痕邮箱仍有可用真实会话，经原BFF/Verifier/session reader校验后完成三轮锁前同步竞争。24唯一编号请求、每轮一200一404、唯一持久owner、胜者幂等、败者/旧cap拒绝及源文件/来源摘要检查全部通过，fresh独立复核实跑断言通过。无需新邮件或公网入口。结果仅覆盖单API、两真实已验证身份及3合成夹具，BA-11其余矩阵仍待验；此前未通过记录保留作历史，当前以验收报告“最终真实验收结果”为准。

本批已分别从原UI退出两份测试会话，无痕窗口关闭；停服脚本与五端口独立核验完成、临时页移除，PG/Redis/Web/API全部停止，Hook本批未开启。数据和通过证据保留。

同邮箱未确认身份另补本地签名JWT+一次性PG集成：保留原验签/私有视图会话SQL，仅替换JWKS获取；11路径401且归属快照不变，模拟确认后独立user、不继承任务/客户/Portal。新增1项、31相关回归及fresh独立PG审查通过，无生产修改或供应商调用。真实Supabase注册/关联策略未验，BA-11不整体勾选，见 [同邮箱身份隔离](reviews/2026-10-19-same-email-identity-isolation.md)。

多API本地集成也已通过：两个spawn HTTP进程、独立连接池连接同一一次性PG，三轮任务锁前双到达且OS/backend PID均不同，每轮唯一owner，两实例上重放/败者/旧cap门禁一致；替换实例后归属保持。多API+同邮箱集成2项、18相关回归及fresh独立PG复跑通过，进程/库已清理。使用本机签名JWT，未验云端负载均衡、真实JWKS或BFF跨实例刷新，见 [多API认领](reviews/2026-10-19-multi-api-claim-isolation.md)。

认领/删除竞争另补本地集成：两个app/独立engine下，实际PG阻塞证明同user锁序；先认领的任务纳入删除清理，删除先提交时认领409，原未归属guest保留。Worker两阶段停用/清理、原身份墓碑同ID、另一账户源文件和幂等检查通过。新增2项、删除PG共16项、67普通回归及fresh独立2项通过；仅合成无账单账户，无真实删除/停费，BA-11/13未整体签收。见 [认领与删除竞争](reviews/2026-10-19-claim-account-deletion-race.md)。
