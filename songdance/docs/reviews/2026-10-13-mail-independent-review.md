# 邮件增量独立只读审查

审查提交：`23d2a601b608d4715176540f017cba07ad24573d`（`959be6c..23d2a60`）。

## 结论 / findings

在本次范围内未发现可行动问题。此结论只覆盖默认关闭、禁止 production、限定测试收件人的本地邮件实现，不代表 MAIL-01–06、BA-02 或真实接入验收完成。

派发消息的 payload 在本审查会话中多次为空；因此按当前 HEAD 的邮件提交、AUTH-04 和 Phase 38.1 邮件增量确定范围，已尝试向主 Agent 确认。未扩大为全产品或生产发布审计。

## 审查范围与已核对项

- `Billing-Auth-Spec.md` AUTH-01/AUTH-04、`DEV-PLAN.md` Phase 38.1 及邮件配置/交付说明。
- `songdance/api/app/routes/mail.py:23` 两个签名入口、精确 Origin 例外、体积限制、整请求超时、安全错误与默认关闭。
- `songdance/api/app/services/mail_contract.py:49` 测试配置约束、独立 secrets；`:103` SDK 原始正文验签；`:123` Supabase 输入、测试收件人、6/8 位 OTP、固定模板和链接。
- `songdance/api/app/services/mail_delivery.py:27` 持久摘要、稳定幂等、CAS claim、重试时限和次数、attempt fencing；`:85` 事件验签后落库、去重、发送关联、退信投诉抑制和乱序处理。
- `songdance/api/app/services/resend_client.py:24` Resend 响应分类、未知结果、不自动重定向、不泄露原始错误、单次时间/响应体上限。
- 014 迁移、模型、相关测试和邮件入口受影响调用者；BFF 仍经 Supabase 生成/验证 OTP，邮件事件不涉及身份或账本变更。

## 独立执行的验证

在 `songdance/api` 下，设置 `PYTHONDONTWRITEBYTECODE=1`、禁用 pytest cache、使用隔离 SQLite 与 `/tmp` 存储，未触达现有服务或真实邮箱：

```
PYTHONDONTWRITEBYTECODE=1 SONGDANCE_DATABASE_URL=sqlite:// SONGDANCE_AUTO_CREATE_SCHEMA=false SONGDANCE_LOCAL_STORAGE_PATH=/tmp/songdance-mail-review-storage SONGDANCE_TEMP_PATH=/tmp/songdance-mail-review-temp SONGDANCE_MAIL_ENABLED=false .venv/bin/python -B -m pytest -p no:cacheprovider tests/test_mail.py tests/test_mail_migrations.py tests/test_migrations.py -q --tb=short
```

结果：**73 passed，2 个既有依赖弃用警告，17.58 秒**。

```
.venv/bin/ruff check --no-cache app/routes/mail.py app/services/mail_contract.py app/services/mail_delivery.py app/services/resend_client.py app/models/mail.py app/migrations/versions/014_mail_delivery.py tests/test_mail.py tests/test_mail_migrations.py tests/test_mail_real_services.py
```

结果：**All checks passed**。

在仓库根目录执行 `git diff --check HEAD^ HEAD`，结果通过。

另以隔离 Python 片段核实当前 `starlette.concurrency.run_in_threadpool` 配合 `asyncio.timeout(0.2)` 可在 0.201 秒向请求协程返回 TimeoutError；底层线程不能因此被强制终止，所以仍保留原实现的持久状态与重试栅栏要求。

使用 agent-reach 网页路径核对官方文档：Jina 路径因 DNS 失败，随后只读获取官方公开 Markdown 成功。

- https://resend.com/docs/webhooks/emails/bounced.md：`data.tags` 为对象，`bounce.type` 示例为 Permanent/Temporary，与实现一致。
- https://supabase.com/docs/guides/auth/auth-hooks：整个 HTTP Hook（含重试）只有 5 秒预算；429/503 且非空 Retry-After 可重试，当前供应商只检查 Retry-After 非空，不按数值调度。
- https://supabase.com/docs/guides/auth/auth-hooks/send-email-hook：输入 user/email_data、Standard Webhooks、Hook 代替 SMTP、200 空对象响应与实现一致。

120 秒本地重试窗口是处理再次到达的同一请求的上界，不能作为 Supabase 会在 120 秒内持续重投的证据；当前实现与说明未将这项标为真实联调通过。

## 未覆盖项

- 本次未重跑 opt-in 临时 PostgreSQL 测试；阅读了其并发/迁移用例及已有交付记录，未把历史结果当作本次执行结果。
- 未连接真实 Supabase / Resend，未发邮件，未验证 Gmail/Outlook/Yahoo 收件、垃圾箱、邮件头认证、回复或邮件 HTML 实际客户端呈现。
- 未验证公开 HTTPS 部署、真实重试时序、实际 8 位登录/过期/复用、客服收信、供应商控制台跟踪设置。
- 未重跑无关音乐回归或 Web build；本提交无新前端页面。

审查前后 HEAD 相同。工作区仅有原有未跟踪文件 `songdance/docs/reviews/2026-09-29-deployment-readiness.md`；未修改仓库、提交或推送。本文件是隔离审查记录，不是仓库验收通过标记。
