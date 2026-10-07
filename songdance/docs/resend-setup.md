# Resend 邮件接入准备

2026-10-07：用户选定 Resend 免费层、`mail.<主域名>`、API 集成与 `support@<主域名>`。已核验可访问的 Resend 已登录控制台与 Free 额度，尚无发信域名。以下是待完成的准备与实施合同，不是已经运行的邮件服务；实际主域名、DNS 管理方及客服收信账户尚未提供。认证要求见 [AUTH-04](../../Billing-Auth-Spec.md)，开发归属为 [Phase 38.1](../../DEV-PLAN.md)。

## 1. 账户与域名

- 使用 Resend 免费层的独立测试配置，不自动添加付费功能、升级或购买域名。2026-10-07 已登录账户 Usage 页显示 Transactional Free：3,000 封/月、100 封/日；Team Free：3 个域名、10 req/s。事务邮件 Pay-as-you-go 关闭且不可用；尚未产生发送用量。该记录仅是当前账户显示，免费额度和域名数量后续仍以实际账户/官方合同为准。
- 主域名必须由用户确认且有 DNS 控制权，不能从产品名猜测。仅在 Resend 添加 `mail.<主域名>`，取得该账户生成的 DKIM 与 SPF/Return-Path 记录，再在对应 DNS 控制台逐条配置；不手写示例值冒充真实验证。
- 保留现有业务/客服的 MX、SPF 与 DMARC。新增记录前检查同名已有值；同一主机名不新增第二条 `v=spf1`，也不为发信验证覆盖根域收信 MX。
- DMARC 先核查子域继承的现有策略与 SPF/DKIM 对齐。未有既定策略的新测试子域可先监控；已有更严格策略不未经确认降级。报告接收地址必须真实能收信，验证全部合法发信源后再逐步收紧策略。
- Resend 域名 Verified 与三家邮箱认证/收件均通过才启用对真实用户发信；DNS 发布、权限扩展、创建密钥和接受法律条款在具体操作时确认，新认证凭据由用户输入并提交。

## 2. 发件与客服身份

| 用途 | 地址 | 准备条件 |
|---|---|---|
| 登录验证码 | `auth@mail.<主域名>` | 验证发信子域名；服务端固定 From |
| 账务通知身份 | `billing@mail.<主域名>` | 同一发信子域名；先准备身份，不重复发送 Creem 收据 |
| 用户回复/客服 | `support@<主域名>` | 另行配置真实邮箱或转发，并测试收信/回复 |

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

当前没有实现或部署新的邮件 Hook/API、持久发送记录和退信回调。不能把配置字段/官方示例当可用运行代码。公开 HTTPS Hook 地址与目标测试服务尚未准备，不能把 `127.0.0.1` 当 Supabase 云端可访问回调。

## 4. 退信、投诉与模板

- 至少准备 `email.bounced`、`email.complained` 回调；签名验证必须使用 raw body 和 `svix-id` / `svix-timestamp` / `svix-signature`，提交去重记录后处理事件。原始 body 重序列化后不能拿来验签。
- 硬退信/投诉进入抑制与运营检查，不无限重发；重复/乱序通知不能解除抑制、按邮箱绑定身份或变更套餐余额。解除抑制必须核验原因。
- 登录模板显示验证码、十分钟有效期、非本人请求提示及实际客服/隐私入口；账务模板引用已确认的交易和实际退款页面。无需新增营销订阅或跟踪像素；默认关闭打开/点击跟踪。
- Gmail、Outlook、Yahoo 使用用户指定的测试收件地址，分别验证送达、垃圾箱、DKIM/SPF/DMARC 头部、8 位登录/过期/复用与客服回复。发送前核对收件人与测试用途，API 返回 ID 不证明进收件箱。

## 5. 当前完成与下一步

- 已完成：Supabase Test 项目、Creem Pro Test 商品；精确本地回跳，8 位/600 秒参数；OTP 兼容回归、独立审查与受忽略的本地配置骨架。
- 已核验 Resend 已登录控制台、Free 用量限制和空域名列表；添加域名表单已打开，未填写或提交未知域名，未创建 API key、发送邮件或开启付费功能。
- 未完成：实际主域名/DNS、发信域名与客服收信、API key/签名 secrets、Hook/API/日志/回调代码、公开测试地址与三家邮箱测试。
- Resend 开户页面最初显示加载错误，随后已恢复为可访问的 onboarding/Usage/Domains；已登录状态由实际控制台核对，不凭跳转 URL 推断。

先提供主域名与 DNS 服务商，核验 Resend 注册及账户免费层，再取得真实 DNS 记录。需要新密码/认证凭据、接受条款、创建密钥或扩展公开访问时交由用户完成或在操作时确认。无这些信息时不修改 DNS、不投递真实邮件、不打开登录/收费。

## 官方核验

2026-10-07 使用 agent-reach 网页读取路径，代理超时后直接读取公开官方 Markdown；获取原文不等于账户联调通过。

- https://supabase.com/docs/guides/auth/auth-hooks/send-email-hook ：签名 Hook 输入 `user/email_data`、OTP 与 Email Provider/Hook/SMTP 行为；原文 schema 示例仍为 6 位，当前控制台实际为 8 位，不能照抄该位数限制。
- https://resend.com/docs/dashboard/domains/introduction.md ：验证自有域名/子域名、发件身份与收信能力区分。
- https://resend.com/docs/dashboard/domains/dmarc.md ：先验证 SPF/DKIM 与送达，再逐步收紧 DMARC；报告邮箱须可收信。
- https://resend.com/docs/api-reference/emails/send-email.md ：From/To/Reply-To、HTML/text 和 24 小时幂等键合同。
- https://resend.com/docs/webhooks/introduction.md ：事件回调、重放和投递状态。
- https://resend.com/docs/webhooks/verify-webhooks-requests.md ：raw body 与 Svix 签名头。

公开价格读取代理超时，实际 Free 限额另从已登录 Usage 页核对；Hook 超时/重试、Resend 真实权限与发送结果尚待核验。本文件不承诺未来免费价格、投递率、合法退款条件或生产发布完成。
