# Resend 邮件接入准备

2026-10-13 更新：Cloudflare DNS/NS 与受测 DNSSEC 恢复已于 14:50 验收，临时跟进已停止。Resend `mail.notavue.io` 控制台于 15:04 显示 DNS verified、15:05 显示 Domain verified，DKIM 与两条发信 CNAME 均 Verified，Sending on / Receiving off。晚间用户确认客服收件目标为已可收发的 `hello@notavue.io`；只读核对根域 MX 已由飞书承接，后台域名已启用、邮箱成员正常。随后经用户明确授权，已添加并保存 `support@notavue.io` 企业邮箱别名，刷新后在成员详情复核可见；现有 `SD-20261013-01` 测试线程的来信与回复已在飞书/外部 QQ 两端核对；保留飞书 MX，不能直接沿用早先 Cloudflare 根域转发设想。邮件本地代码和 014 迁移已补入，默认关闭；独立审查已补齐且未发现可行动问题，Resend 受限发送 key 已创建并存入私密配置，四事件回调已保存；两路隔离 HTTPS、签名 secrets 与 Supabase Hook 已接通并启用受限测试发送，2026-10-14 真实 OTP 发码/收件/供应商验证与复用拒绝通过。真实 600 秒过期拒绝、专用私有视图连接、应用 BFF/账户页及退出撤销已通过；本轮已禁用两家回调、限额页面恢复 2/h 并关闭本机测试服务，三家邮箱仍待验；最新现场见 [OTP 联调](reviews/2026-10-14-mail-otp-integration.md)。见 [维护记录](reviews/2026-10-13-cloudflare-migration.md)、[邮件交付记录](reviews/2026-10-13-mail-delivery.md)、[审查与客服核对续接](reviews/2026-10-13-mail-review-followup.md)；历史事件见 [DNS 准备](reviews/2026-10-12-resend-dns-preparation.md) 与 [故障恢复](reviews/2026-10-13-dnssec-recovery.md)。认证要求见 [AUTH-04](../../Billing-Auth-Spec.md)，开发归属为 [Phase 38.1](../../DEV-PLAN.md)。

## 1. 账户与域名

- 使用 Resend 免费层的独立测试配置，不自动添加付费功能、升级或购买域名。2026-10-07 已登录账户 Usage 页显示 Transactional Free：3,000 封/月、100 封/日；Team Free：3 个域名、10 req/s。事务邮件 Pay-as-you-go 关闭且不可用；尚未产生发送用量。该记录仅是当前账户显示，免费额度和域名数量后续仍以实际账户/官方合同为准。
- 主域名必须由用户确认且有 DNS 控制权，不能从产品名猜测。仅在 Resend 添加 `mail.<主域名>`，取得该账户生成的 DKIM 与 SPF/Return-Path 记录，再在对应 DNS 控制台逐条配置；不手写示例值冒充真实验证。
- 保留现有业务/客服的 MX、SPF 与 DMARC。新增记录前检查同名已有值；同一主机名不新增第二条 `v=spf1`，也不为发信验证覆盖根域收信 MX。
- DMARC 先核查子域继承的现有策略与 SPF/DKIM 对齐。未有既定策略的新测试子域可先监控；已有更严格策略不未经确认降级。报告接收地址必须真实能收信，验证全部合法发信源后再逐步收紧策略。
- Resend 域名 Verified 与三家邮箱认证/收件均通过才启用对真实用户发信；DNS 发布、权限扩展、创建密钥和接受法律条款在具体操作时确认，新认证凭据由用户输入并提交。

## 2. 发件与客服身份

| 用途 | 地址 | 准备条件 |
|---|---|---|
| 登录验证码 | `auth@mail.notavue.io` | 发信子域已 Verified；服务端固定 From，尚未真实发送 |
| 账务通知身份 | `billing@mail.notavue.io` | 同一发信子域名；先准备身份，不重复发送 Creem 收据 |
| 用户回复/客服 | `support@notavue.io` | 收件目标 `hello@notavue.io` 已由飞书托管，成员正常；`support@` 企业邮箱别名已获授权添加并保存，刷新后复核可见，现有 QQ 测试来信/主邮箱回复两端已核对；保留现有 MX |

只验证 `mail.<主域名>` 不授权从根域 `auth@<主域名>` 发信。所有应用邮件可固定 Reply-To 为客服地址。Resend 发信身份不是自动创建可登录的客服邮箱；客服收信不能以“From 能发送”代替。

## 3. API 与 Supabase 边界

Supabase 的 `signInWithOtp` 仍产生 OTP 并负责 `verifyOtp`、过期与单次使用。签名 Send Email Hook 把认证邮件请求交给服务端，再调用 `POST https://api.resend.com/emails`；启用 Email Provider 与 Hook 后该链路不再使用 SMTP。当前测试项目保留 8 位、600 秒，应用已兼容 6/8 位格式，但这不证明发信 Hook 或真实邮箱已经联通。

实施时：

- 按供应商真实签名合同验证原始请求体、时间窗和 ID，固定项目/本站/发件身份，限制请求大小与邮件类型；采用成熟 Standard Webhooks/Svix 实现，不复制不同供应商的签名头或手写简化验签。
- 只发送 Supabase 提供的验证码，不自行生成另一套验证码或把邮件送达当登录成功；不在 subject、链接、日志或诊断响应中放入 OTP/token/hash。
- 使用 Resend 的稳定 `Idempotency-Key`，在其 24 小时窗口内对同一发送请求保留相同 key/正文，避免超时后重复发信。429/暂时故障有界退避，永久错误不盲重试；Hook 超时预算与实际供应商重试行为须在实现前核对。
- 明确区分未发送、结果未知、Resend 接受和实际投递。失败不得伪造成功或延长验证码有效期；重发继续遵循 BFF/Redis 的既有预算，不以发送重试绕过限制。
- 密钥只在受控服务端：Resend 最小发信权限 key、Supabase Hook secret、Resend webhook secret 各自独立。尚未把任何真实密钥放进本地文件或平台。
- 普通发送日志保存消息 ID、类型、状态、错误分类和必要收件地址带密钥摘要；不保存验证码、密钥、完整 hook payload/邮件正文。若可靠恢复需要保存敏感内容，需加密、有界保留并排除普通日志。

本地已实现默认关闭的 Hook/API、持久发送记录和退信回调。专用 listener 和 Cloudflare Quick Tunnel 已获授权准备并实测 HTTPS 路由边界；临时地址见 [现场记录](reviews/2026-10-13-mail-test-connection.md)，本轮受限测试已取得供应商 OTP、真实过期拒绝和应用 BFF/账户页/退出证据；收尾已禁用 Hook 与事件回调并停止 Tunnel/listener，MAIL_ENABLED 恢复 false。不能把 `127.0.0.1` 当 Supabase 云端可访问回调。

### 本地实现与配置边界

配置骨架为 [env.mail.example](../infra/env.mail.example)，运行库采用 `standardwebhooks==1.1.0` 验签，`httpx==0.28.1` 做有总时限的异步发送。安装使用 `api/requirements.lock`；本地 `uv.lock` 不作为交付锁文件。

- 先对隔离数据库执行 `alembic upgrade head`（014），随后按私密配置启用 `SONGDANCE_MAIL_ENABLED`。启动检查要求非 production、匹配 Supabase 项目/本站 origin、1–10 个明确测试收件人、独立三组密钥和已验证客服收信；客服仍待创建时保持关闭，不假填验证标记。
- `POST /webhooks/supabase/email`，原始 body 上限 20 KiB。使用 `webhook-*` 签名头，SDK 校验正负 5 分钟时间窗；独立 Hook secret 是项目来源凭证，payload 没有可信的项目 ID，不靠浏览器声明来源。固定 `email_data.site_url` 为该 Supabase 项目 API origin 或 `/auth/v1`；官方 Auth 实现该字段来自 `API.ExternalURL`，不能与应用首页比较。模板链接独立使用服务端 `mail_site_url`，只接受 6/8 位 ASCII OTP 和 signup/magiclink/reauthentication。
- Hook 替代 Supabase 所有邮件；当前不支持 invite/recovery/email_change/security notification，明确失败而不静默丢信。接入测试项目时必须限制这些流程。Google OAuth 不通过这个邮件 Hook。OTP 到期仍由 Supabase 的 600 秒设置负责。
- Supabase 官方 HTTP Hook 总预算 5 秒。本应用请求等待上限 4 秒、Resend 单次尝试上限 3 秒；底层 HTTPX 超时 2 秒，不重定向、不自行循环发送。暂时失败回 503 + 非空 Retry-After；Supabase 整个调用（含重试）仍只有 5 秒，当前只检查该头非空、不按数值调度；本地 next_attempt_at 继续强制退避，实际重试时序待联调。同请求数据库 CAS/4 秒租约控制并发，每个 ID 最多 3 次发送尝试、首次接收后最多 120 秒；这只是同请求再次到达的处理上界，不表示 Supabase 会重投 120 秒。
- 稳定发送 key 为项目和 Hook ID 的摘要；请求体和完整渲染正文另存 HMAC 摘要，重试修改正文/模板/配置会失败关闭，不换 key 重发。超时状态为 unknown，提交 accepted 后才返回成功；accepted 不表示投递或登录成功。服务重启可从同一签名重投恢复，没有保存明文 OTP 的后台 outbox。超过窗口、永久错误、配额耗尽不自动再试，需用户按原发码预算重新请求新验证码。
- `POST /webhooks/resend`，原始 body 上限 64 KiB；适配 `svix-*` 到 Standard Webhooks 相同签名算法，SDK 验签后再处理。事件和抑制同事务，已签名事件通过发送时附带的 `songdance_delivery` tag、From、收件摘要及已知 message ID 关联本地发送；其它邮件不影响应用。硬退信 Permanent、投诉和 provider suppressed 均抑制后续发送；Temporary 不永久抑制；迟到 delivered 不解除抑制。已在途的发送不能撤回。
- 日志/表只保留必要消息 ID、HMAC 摘要、类型、状态、尝试、固定错误码和时间；不保存收件明文、OTP/token/hash、正文、完整事件或 SMTP 诊断。HMAC secret 不可直接替换，否则已有抑制无法匹配；轮换和生产保留/清理政策另行审查。历史存在时 014 拒绝破坏性 downgrade，回退采用关闭发送并保留表。
- 模板英文回退，只使用服务端固定本站 `/privacy`、`/refund`、`/contact`，不写未经确认的退款承诺、不读取客户端 redirect/metadata。`billing@` 不额外发 Creem 收据。没有添加跟踪像素；控制台的 Configure 打开的是 New tracking subdomain 表单（未提交，默认 click 选中/open 未选中），不据此宣称已实测关闭所有账户跟踪。TLS 当时为 Opportunistic，未修改。

客服收发已通过；真实接入仍需：用户受控填写 Resend 最小发信权限 key、Supabase Hook secret、Resend callback secret 和独立 HMAC secret；确认公开 HTTPS 测试服务并部署；配置两条 Hook，至少订阅 bounced/complained/suppressed/delivered；用指定 Gmail/Outlook/Yahoo 地址验收。未完成这些步骤不勾选 MAIL-01–06。

## 4. 退信、投诉与模板

- 至少准备 `email.bounced`、`email.complained` 回调；签名验证必须使用 raw body 和 `svix-id` / `svix-timestamp` / `svix-signature`，提交去重记录后处理事件。原始 body 重序列化后不能拿来验签。
- 硬退信/投诉进入抑制与运营检查，不无限重发；重复/乱序通知不能解除抑制、按邮箱绑定身份或变更套餐余额。解除抑制必须核验原因。
- 登录模板显示验证码、十分钟有效期、非本人请求提示及实际客服/隐私入口；账务模板引用已确认的交易和实际退款页面。无需新增营销订阅或跟踪像素；默认关闭打开/点击跟踪。
- Gmail、Outlook、Yahoo 使用用户指定的测试收件地址，分别验证送达、垃圾箱、DKIM/SPF/DMARC 头部、8 位登录/过期/复用与客服回复。发送前核对收件人与测试用途，API 返回 ID 不证明进收件箱。

## 5. 当前完成与下一步

- 已完成：Supabase Test 项目、Creem Pro Test 商品；精确本地回跳，8 位/600 秒参数；OTP 兼容回归、独立审查与受忽略的本地配置骨架。
- 已核验 Resend 已登录控制台与 Free 用量限制；2026-10-12 按用户确认创建 `mail.notavue.io`（Ireland / eu-west-1），2026-10-13 已 Verified，收信关闭。本轮已按授权创建 `SongDance Auth Test`（Sending access、仅该域）；已用其完成一封真实测试 OTP，不启用付费功能。
- 已按用户确认创建 Cloudflare `notavue.io` Free 区域，关闭附加 robots.txt 偏好同步，在 Pending 区域配置 DKIM TXT、两条发信 CNAME、`_dmarc.mail` TXT；两条现有 A 记录改为 DNS only，IP 未变。实际 SPF/Return-Path 配置采用账户生成的 CNAME，不照搬官方文档的旧 MX/TXT 示例。
- 本轮现场已补客服两端收发证据、专用两路 HTTPS listener、受限发送 key 和 Resend 四事件回调；已补签名 secrets/Supabase Hook 与真实供应商 OTP 证据；已补私有视图会话 DSN、BFF/账户页和退出撤销，测试服务已关闭；未完成：三家邮箱头部与收件验收、完整 MAIL/BA 签收。已补本地 Hook/API/日志/回调代码，实际测试与限制见 [邮件交付记录](reviews/2026-10-13-mail-delivery.md)。DNS/NS/DNSSEC 迁移已于 14:50 通过受测验收。
- Resend 开户页面最初显示加载错误，随后已恢复为可访问的 onboarding/Usage/Domains；已登录状态由实际控制台核对，不凭跳转 URL 推断。

2026-10-12 的授权边界只准备 Cloudflare 记录，当日未操作 Spaceship，也未点选“已更新域名服务器”或“已添加记录”冒充生效。2026-10-13 10:48 的恢复阶段，用户另行确认禁用旧 DNSSEC，出现故障后再次确认恢复，生成 DS 32322，NS 未改、迁移暂停；这是历史状态。随后用户选择维护迁移并现场确认关闭旧 DNSSEC，11:53 已确认 DS 撤销，等待缓存退出。后续安全操作仍须具体确认；需要新密码/认证凭据、接受条款、创建密钥或扩展公开访问时交由用户完成或在操作时确认。域名发信尚未验收，不投递真实邮件、不打开登录/收费。

用户重申目标为注册与续费留 Spaceship、DNS 迁 Cloudflare Free、Web 按既有方案部署 Vercel、HTTPS 由平台签发；不转移注册商。随后明确接受维护窗口中断风险、确认关闭旧 DNSSEC、切 NS 和恢复新 DNSSEC。当前 Cloudflare 委派和新 DNSSEC 的受测链验收已完成，原网站 IP 保留；Vercel/应用部署仍待后续阶段。支持聊天编号为 `SPS-YGU-3557`。

### 2026-10-13 迁移前只读复核

- Cloudflare 控制台仍为 Pending，六条记录与既有准备一致。`dig @1.1.1.1` / `@8.8.8.8` 查询公开 NS/DS 均仍为 Spaceship 与原 DS；查询原/新权威服务器的根域 A 仍为两个相同 IP。
- 直接向四个 `.io` 父区服务器 `a0/a2/b0/c0.nic.io` 查询，均发布原 DS（64580 / 13 / 2），TTL 3600；父区 NS 仍为 `launch1/launch2.spaceship.net`，TTL 3600。这是迁移前基线，不是旧 DS 已撤下或缓存已过期的证据。
- `whois notavue.io` 返回注册商 `Spaceship, Inc.`（IANA 3862）、原两个 Spaceship NS 和 `DNSSEC: signedDelegation`，已确认注册商，不仅按 NS 猜测登录目的地；账户归属及完整记录仍须登录后核验。
- 原 DNSSEC 迁移网址返回 404；已读取官方 DNSSEC 总览及 Full setup 原文。普通迁移顺序为移除旧 DS→从父区确认撤下并等待旧 TTL 缓存退出→切换 NS→等待原 NS 缓存退出→启用 Cloudflare 新签名并提交匹配的新 DS。不能从本次查询时刻开始固定等一小时就切换，也不能只关旧区签名而保留父区 DS。
- Spaceship 当前未完成登录，不能核对完整旧 DNS 清单/账户控制权，不能操作 DNSSEC 或 NS。已请用户在浏览器自行完成登录，未重试已填写的密码、重置凭据、修改任何解析或发送邮件。登录后须先核对/备份完整记录，再在具体安全变更前请求确认。

以上为当时预检。用户随后完成登录，已核对域名账户、0 条自定义记录/重定向及原 DS；经确认尝试禁用、发现故障并另经确认恢复。10:48 恢复阶段 Spaceship DNSSEC 开启、新 DS 32322 与父区匹配，受测公开解析 NOERROR + AD，NS 未改；这不是当前维护窗口状态。操作、暂时故障、恢复及支持沟通见 [10 月 13 日恢复记录](reviews/2026-10-13-dnssec-recovery.md)，11:53 的维护进度以上述总览和维护记录为准。

## 官方核验

2026-10-07 使用 agent-reach 网页读取路径，代理超时后直接读取公开官方 Markdown；获取原文不等于账户联调通过。

- https://supabase.com/docs/guides/auth/auth-hooks/send-email-hook ：签名 Hook 输入 `user/email_data`、OTP 与 Email Provider/Hook/SMTP 行为；原文 schema 示例仍为 6 位，当前控制台实际为 8 位，不能照抄该位数限制。
- https://resend.com/docs/dashboard/domains/introduction.md ：验证自有域名/子域名、发件身份与收信能力区分。
- https://resend.com/docs/dashboard/domains/dmarc.md ：先验证 SPF/DKIM 与送达，再逐步收紧 DMARC；报告邮箱须可收信。
- https://resend.com/docs/api-reference/emails/send-email.md ：From/To/Reply-To、HTML/text 和 24 小时幂等键合同。
- https://resend.com/docs/webhooks/introduction.md ：事件回调、重放和投递状态。
- https://resend.com/docs/webhooks/verify-webhooks-requests.md ：raw body 与 Svix 签名头。

2026-10-12 补读 https://resend.com/docs/knowledge-base/cloudflare.md ：人工配置需按实际账户记录、邮件 CNAME 为 DNS only；文档的旧 MX/TXT 示例与本账户生成的两条 CNAME 不同，以实际记录为准。Cloudflare DNSSEC 迁移网页两次读取因解析超时/失败未取得正文；其控制台明确提示迁移前确保旧 DNSSEC 关闭，与公开旧 DS 风险核对一致，不将未读到的原文列为核验通过。

2026-10-13 使用 agent-reach 网页路由，读取代理超时后直接以 `Accept: text/markdown` 获取 https://developers.cloudflare.com/dns/dnssec/ 与 https://developers.cloudflare.com/dns/zone-setups/full-setup/setup/ 完整原文；已核对上述迁移/恢复顺序。官方也提供多签名持续 DNSSEC 迁移，但依赖旧供应商外部 DNSKEY 能力，当前未确认，不据此跳过旧 DS 处理。

2026-10-13 实施核验补充：已读 Supabase Auth Hooks 的 HTTP 5 秒预算、429/503 + Retry-After 重试合同；Resend idempotency-keys、API errors、`webhooks/emails/bounced.md`、`complained.md` 和 `suppressed.md` 原文；Python 包注册表 `standardwebhooks` 1.1.0 与实际 SDK 源码确认签名/时间窗。早先猜测的 `webhooks/email-bounced.md` 和 `email-complained.md` 返回 404，随后从官方索引定位正确路径。pip 的证书链错误后改用 uv 的系统证书验证安装，未关闭 TLS 验证。

公开价格读取代理超时，实际 Free 限额另从已登录 Usage 页核对；Resend 真实权限与发送结果尚待核验。本文件不承诺未来免费价格、投递率、合法退款条件或生产发布完成。
