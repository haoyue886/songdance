# 2026-10-14 真实邮件 OTP 与应用登录联调

本记录接续 [测试接入准备](2026-10-13-mail-test-connection.md)。**指定测试环境的真实验证码 → Next.js BFF → FastAPI 验签/会话查询 → 账户页 → 退出闭环已通过。** 错误验证码、真实 600 秒过期和单次使用拒绝已有证据。本轮临时发信与回调已关闭；Google、Creem Test、完整 MAIL/BA 和生产验收继续待验。

## 实际通过的链路

| 验证项 | 实际证据 |
|---|---|
| 客服邮箱 | `support@notavue.io` 为飞书 `hello@notavue.io` 别名；`SD-20261013-01` 的外部 QQ → support → hello 收件与 hello → QQ 回复，两端已查看确认；根域 MX 保留飞书 |
| 供应商发码 | Supabase `/auth/v1/otp` 200，Resend accepted、attempts=1、无 error；飞书收件箱实际看到 8 位验证码及十分钟提示 |
| 供应商验证 | 第一封实际代码 `/verify` 200、邮箱匹配且签发会话，`/user` 200；重复使用 403，`/logout` 204 |
| 真实过期 | 第二封实际代码等待超过 606 秒后 `/verify` 403 / `otp_expired`；结果在本机 `/tmp/songdance-expiry-result.json`，无代码或令牌 |
| 应用发码 | `http://127.0.0.1:3002/zh/login` 输入 hello，实际 BFF `/api/auth/email/start` 200；第三封真实邮件进入飞书收件箱 |
| 应用错误码拒绝 | 将该代码一位改为不同数字，实际 BFF `/api/auth/email/verify` 401，页面显示验证码无效/过期；没有重发邮件 |
| 应用正确登录 | 使用同封真实代码，BFF `/api/auth/email/verify` 200、`access-token` 200；实际账户页显示 `hello@notavue.io`、账户管理和退出按钮。FastAPI 已执行真实 JWT 公钥验签及专用连接会话查询 |
| 应用退出 | 点击账户页退出，BFF `/api/auth/logout` 200，返回登录页；再访问账户页显示需登录，`access-token` 401 |
| 服务端撤销 | 退出前同一真实 session_id 的 `SupabaseVerifier.session_active` 为 true，退出后为 false；`/tmp/songdance-app-revocation-result.json` 仅保留布尔结果，临时 ID 文件已移除 |
| 签名投递回调 | 隔离库最终 3 条 accepted、3 条 `email.delivered / recorded`；本轮最新 provider ID `01a1386d-d6ff-7682-9559-526d154e824e`，attempts=1、error=null |

验证码、refresh/access token、完整 Hook payload 和 DSN 未写入报告或请求日志。没有把原 JWT 导出后重放到 API；上述撤销证据是应用相同会话查询及退出后的真实 BFF 拒绝，不代表跨设备/全局撤销等全部 BA-11 已验收。

## 会话连接的真实阻塞与兼容修复

前序曾因保存位置、管理员连接模板、SQL 选区和两次输入不同密码而未能连接；未使用 postgres 管理员账号登录应用，也未读取密码列/密码哈希。最终由用户在本机向导生成一份随机密码并在 Supabase 提交，用同一页面内存中的密码验证，确认专用 LOGIN 角色可以通过 session pooler 认证。

认证通过后发现真实错误为 `permission denied for schema auth`。只读元数据确认：auth schema 归 Supabase 内部 `supabase_admin` 所有；控制台 postgres 不是超级用户、不是该内部角色成员，对 auth 只有 USAGE，没有 GRANT OPTION。用户授权补执行 `GRANT USAGE` 后，控制台虽显示 Success，但权限仍为 false，因此没有以成功提示冒充授权生效。

已新增 [私有视图 SQL](../../infra/supabase-session-reader-views.sql)，在用户明确授权后由现有迁移角色执行：

- 私有 `songdance_auth.sessions` 只含 id/user_id/created_at/refreshed_at/not_after，users 只含 id/email_confirmed_at/banned_until/deleted_at，共 9 个字段。
- 视图使用默认由所有者校验底层权限的语义；现有 `songdance_auth_reader` 只有私有 schema USAGE 和两张视图 SELECT，专用 LOGIN 保持原密码与 reader membership。
- API 新增固定枚举 `SONGDANCE_AUTH_SESSION_SCHEMA=auth|songdance_auth`，默认 auth 兼容既有直读；会话有效性与近期登录确认均使用同一选择，身份值仍参数绑定。不接受任意 SQL 标识符。
- 真实专用连接通过 TLS、9 字段读取、密码列与底层/视图写入拒绝检查，自动保存至 0600、受忽略的 `.env.auth-mail-test.local`；schema 为 songdance_auth，DSN 固定专用用户名与 `sslmode=require`。错误放在 mail-only 文件的会话连接字段已清空，其余密钥保留。
- 实际 metadata 再核对：专用 reader 的私有 schema USAGE=true；anon/authenticated/service_role 均 false，可见视图字段数为 sessions=5、users=4。没有把 reader 加入这三类或管理员角色。

直接数据库主机的 DNS/IPv6/TLS 网络失败与密码不匹配分别记录，不能混为密码错误；最终使用控制台已确认的 session pooler。Data API 零行探测返回 503 / PGRST002，不能将其当作“schema 未暴露”的成功证据；本轮未修改 exposed schemas，外部 Data API 状态另待复核。上述真实角色 metadata 已确认匿名/认证/service_role 没有私有 schema USAGE。

主 Agent 验证：普通认证/配置/Settings 回归 77 passed，独立临时 PostgreSQL/Redis 4 passed，相关 Ruff 与 diff 检查通过；测试使用临时集群，不连接现有业务服务。fresh 独立审查未发现可行动问题，详见 [会话视图审查](2026-10-14-session-reader-views-review.md)。

## 邮件合同修复与既有独立审查

原 `otp_message` 将签名 Hook 的 `email_data.site_url` 与应用首页比较，真实请求曾返回 MAIL_SITE_MISMATCH，未调用 Resend。供应商官方源码确认该字段来自 Auth API 外部地址。现仅接受配置 Supabase API origin 或其 `/auth/v1`；其它项目、伪造后缀、userinfo/query/任意附加路径继续拒绝。模板链接仍独立取服务端 mail_site_url，不使用客户端 redirect/metadata。

日志只输出固定 provider/error_code/status_code，不记录 Hook 正文。该批次实际执行：

```sh
# songdance/api
.venv/bin/pytest tests/test_mail.py tests/test_mail_hook_listener.py tests/test_mail_migrations.py -q --tb=short
.venv/bin/ruff check app/routes/mail.py app/services/mail_contract.py tests/test_mail.py
```

结果为 87 passed、Ruff 通过；独立复审 `test_mail.py` 77 passed、未发现可行动问题，见 [供应商 URL 复审](2026-10-14-mail-provider-url-review.md)。原邮件与 listener 另有 [原批次审查](2026-10-13-mail-independent-review.md)、[listener 审查](2026-10-13-mail-listener-review.md)。各次测试范围重叠，不合计用例数。

## 测试运行环境与额度

- 项目为 songdance-test / amnsavenqfmmvnauyqzi；8 位 OTP、600 秒；本站 127.0.0.1:3002、API 127.0.0.1:8002，业务 SQLite、存储与 Next 构建目录均隔离。收费、用量和删除开关未开启。
- 原 Quick Tunnel `hill-climb-inkjet-england` 运行中被 Cloudflare 注销，服务端日志为 Tunnel not found；已停止失效进程，恢复同范围的 `dining-gif-seem-furnishings` 临时入口并同步两家回调。实际 HTTPS 两个无签名 POST 均 401，/me 为 404。公网始终只有两条签名邮件路由，没有暴露账户/API/docs。
- Next.js 本次进程使用已锁定 undici 和现有本机代理，localhost 不走代理；临时脚本漏传 NEXT_PUBLIC_API_URL 曾导致首次账户数据加载失败，补回配置的 8002 地址后复验。
- API 的 Python 默认 CA 包曾导致公钥请求 CERTIFICATE_VERIFY_FAILED；本次进程指定已安装 certifi CA 包后，真实 JWKS HTTPS 200、1 个公钥。没有关闭 TLS 校验、改全局网络或安装新依赖；会话 DSN 仅交给 API。
- Supabase 被 Hook 拒绝的请求也曾计额度，用户授权将 2/h 临时提高至 10/h。后续最多 3 封授权中已用 2 封（真实过期、实际应用登录），剩余 1 封未使用；没有无限重发。

## 已执行的收尾

- Supabase Send Email Hook 已保存为 DISABLED；随后 Rate Limits 页实际显示 sending emails=2/h、控件不可编辑，未改动其它限流或转发设置。
- Resend 原四事件 webhook 已禁用，菜单显示 Enable endpoint；配置、发送 key 和签名 secret 均保留，未删除凭据。
- `.env.mail-test.local` 的 MAIL_ENABLED=false；auth 私密配置中 AUTH/NEXT_PUBLIC_AUTH/MAIL 开关均为 false，保持 0600 且受 git ignore。
- 本任务 Tunnel、8024 listener、8027 向导、8002 API、3002 Next.js 均已发送 TERM 并复查无监听；未处理其它端口或服务。临时 HTTPS 已失效。
- 停止 Next 后清除其自动写入的测试 dist include/格式变化，tsconfig 恢复启动前内容；保留隔离测试库、邮件发送墓碑、抑制记录及 HMAC。
- 向导剪贴板已替换为普通文字，页面已关闭；OTP 临时变量与会话 ID 文件已清除。没有提交、推送或正式部署。最终 `git diff --check` 通过；6 份当前文档的 29 个本地链接均有效，26 个待交付文件未发现与本机实际配置凭据相同的值，两个私密 env 文件均为 0600 且受忽略。

## 后续验收

下一开发侧项为真实 Google 登录及 Creem Test 付款/额度/转谱导出/取消退款闭环。邮件仍需三家邮箱送达、认证头/垃圾箱/回复、完整幂等/退信/投诉与 MAIL-01–06/BA 逐项签收；正式 HTTPS Cookie、会话策略/跨设备、生产配置、法律政策、容量和音乐专业质量门槛仍待验，不因本次测试完成而整体勾选。

官方依据：

- https://raw.githubusercontent.com/supabase/auth/master/internal/api/mail.go
- https://raw.githubusercontent.com/supabase/auth/master/internal/api/middleware.go
- https://supabase.com/docs/guides/auth/auth-hooks/send-email-hook
- https://supabase.com/docs/guides/database/postgres/roles
