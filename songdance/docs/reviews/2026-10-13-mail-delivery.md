# 2026-10-13 Resend / Supabase 邮件本地交付

## 结论与真实状态

本批按 AUTH-04 实现默认关闭、禁止 production 的测试邮件通道；未部署、未创建真实凭据、未发送邮件、未开启收费。Resend 域名验证通过不代表三家收件箱或认证全链路通过。MAIL-01–06 与 BA-02 保留待验。

- DNS/NS/DNSSEC 迁移已于此前完成，未重复操作；原维护记录和临时跟进停止状态不变。
- `mail.notavue.io` 控制台显示 15:04 DNS verified / 15:05 Domain verified（北京时间），DKIM 与两条发送 CNAME 为 Verified、Sending on / Receiving off。Ireland / eu-west-1，未开启付费。
- Tracking 的 Configure 链接打开新建跟踪子域名表单，未点 Add domain；表单默认 click 选中、open 未选中，不把未提交表单当账户全局开关验收。TLS 当时 Opportunistic，未修改。
- 用户选择 `support@notavue.io` 免费转发到现有邮箱，回复显示该邮箱；目标邮箱回答“待创建”。没有猜测目标、创建邮箱或修改 MX/转发规则。

## 交付范围

- 两个固定服务器端点：`POST /webhooks/supabase/email` 和 `POST /webhooks/resend`，明确签名头适配、原始 body 大小限制与时间窗；独立 `standardwebhooks==1.1.0` SDK 验签。
- 固定测试项目/site/from 和测试收件人白名单，保留 8 位与旧 6 位 ASCII OTP；应用使用的 signup/magiclink/reauthentication 可发送，其它认证邮件类型返回明确错误。Supabase 继续生成、过期、验证验证码。
- 014 迁移增加 `mail_deliveries`、`mail_events`、`mail_suppressions`。发送前持久请求/正文 HMAC 摘要、原子竞争尝试、稳定 Resend Idempotency-Key；结果未知不报成功，最多 3 次、120 秒内原请求重试。Resend 单次 3 秒、整个 Hook 等待 4 秒，与 Supabase 官方 5 秒预算协调；无明文 OTP outbox 或私自生成/延长验证码。
- 永久拒绝/日月配额不自动重试；暂时失败尊重 Retry-After，未知结果继续同 key/正文。回写数据库失败可由同签名重投恢复。模板或配置改变导致正文不一致时失败关闭，不换 key 重复发送。
- Resend 事件先 SDK 验签再去重与处理；关联发送 tag、From、收件 HMAC 和已知 provider ID。永久退信/投诉/provider suppression 持久抑制；Temporary 不永久封禁，迟到 delivered 不解除抑制。事件不改身份/账本/账号。
- 日志与表不保留 OTP、token/hash、明文收件人、正文、完整回调或诊断消息。HMAC 密钥须稳定；运营保留/清理、换钥和误抑制解除仍需单独审查。已在途邮件无法撤回。
- 模板包含服务器固定隐私/退款/客服入口、不写试行退款承诺；英文回退，不新增营销或重复 Creem 收据。没有新前端页面。
- 同步需求实施状态、Phase 38.1、`docs/resend-setup.md` 与 `infra/env.mail.example`；私密 `.env.commercial-test.local` 未改，生产开关不变。

## 已执行验证

均在 `songdance/api` 执行，合成签名/虚拟 provider，不访问真实邮箱或支付；SQLite 与 PostgreSQL 使用临时目录/集群。

1. `.venv/bin/pytest tests/test_mail.py tests/test_mail_migrations.py tests/test_migrations.py -q --tb=short`：最终 **73 passed**。包括官方 Svix 固定测试向量、篡改/旧/未来/重复签名头、错误项目/类型/收件人、6/8 位、重试正文不变、API 未知/429/409/配额/永久错误、并发 CAS、陈旧尝试栅栏、数据库失败不伪成功、总超时、退信乱序/重复/并发抑制、无秘密持久化、014 迁移/旧数据保留/历史拒绝降级。
2. `.venv/bin/pytest tests/test_auth_config_preflight.py tests/test_auth_coordination.py tests/test_auth_ownership.py tests/test_settings.py tests/test_creem_billing.py tests/test_creem_client.py tests/test_creem_failures.py tests/test_billing_ui_contract.py tests/test_account_deletion_migrations.py tests/test_creem_migrations.py tests/test_billing_cancellation_migrations.py tests/test_dispatch_migrations.py tests/test_guest_migrations.py -q --tb=short`：**238 passed**。
3. `.venv/bin/pytest tests/test_health.py tests/test_jobs.py tests/test_commercial_config.py tests/test_commercial_stack_lifecycle.py -q --tb=short`：**71 passed, 5 skipped**；5 项真实商业栈生命周期检查未启用，不宣称重跑端到端。
4. `SONGDANCE_TEST_REAL_MAIL_SERVICES=1 .venv/bin/pytest tests/test_mail_real_services.py -q --tb=short`：**1 passed**，临时 PostgreSQL 迁移、8 路发送 claim、8 路回调去重和抑制。首次沙箱拒绝本机端口绑定；获准后隔离重跑通过，fixture 已停止本任务集群，未连接现有服务。
5. `.venv/bin/ruff check app tests/test_mail.py tests/test_mail_migrations.py tests/test_mail_real_services.py tests/test_migrations.py`：通过；新增运行模块 `compileall` 通过；`git diff --check` 通过。

合计 **383 passed / 5 skipped**（以上不重复文件的检查集合）。未运行全部音乐质量回归、Web build 或真实三家投递；没有前端改动。现有 Starlette/httpx TestClient 与 resampy 的依赖弃用警告保留，不是本批失败。

开发中首轮发现 SQLite naive/aware 时间比较在 ORM session 同步求值时异常，已改为数据库 CAS 并关闭该次本地同步求值，重跑通过。014 初版测试比较全库时发现旧表默认值与模型差异；按既有迁移测试约定限定新三表做 metadata 一致性，同时保留旧用户数据、全链空表升降和有历史拒绝降级验证，未改旧表默认值或放宽其已有测试。

主 Agent 自查补了异常 action/bounce 字段、超长 Retry-After、官方 24 字节 Svix secret（不能误要求所有供应商 32 字节）、等价 Base64 编码重复密钥拒绝等回归。

## 审查限制

已按 AGENTS/dev-builder/code-review 要求以 fresh 上下文派发独立 code-reviewer，并补发范围与临时文件输出要求。多次返回的消息正文均为空，未生成可读取审查文件，最终中止无有效结果的审查轮次。**本批降级为主 Agent 自审，不宣称独立审查通过**；真实接入/发布前应重新取得独立审查证据。

## 下一步与上线阻断项

1. 用户创建/指定目标邮箱后，配置 `support@notavue.io` 免费转发并验证收信/回复，再填写 support verified；仅有发信域名不能代替客服收信。
2. 受控配置发送权限 key、独立 Supabase/Resend Hook secret、独立摘要密钥；不进聊天/日志/Git。当前未创建真实密钥。
3. 确认并部署公开 HTTPS 测试服务后，接 Supabase Send Email Hook 与 Resend 回调，至少订阅 bounced/complained/suppressed/delivered。不能把本地回跳地址当云端 Hook。
4. 固定用户授权的 Gmail/Outlook/Yahoo 收件地址，真实验证送达/垃圾箱/SPF/DKIM/DMARC、OTP 登录/过期/复用、重试时限、无点击/打开跟踪、客服回复和模板一致性。未验证项不签收。
5. Google OAuth、真实 Creem Test、生产合法政策/容量/保留期限和音乐质量/长音频门槛仍独立待办；不因本批本地测试开启生产。

依赖来源核对与官方链接见 [Resend 设置](../resend-setup.md)。本批只安装了项目虚拟环境中的官方 Standard Webhooks 包；pip 证书失败后使用 uv 系统证书验证，未关闭 TLS、改全局权限或安装全局工具。
