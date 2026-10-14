# 2026-10-13 邮件独立审查与客服邮箱核对续接

## 范围与状态

本次续接提交 `23d2a60` 的邮件代码独立审查，并按用户提供的客服收件地址核对现有配置。本地邮件开关继续关闭；未创建凭据、部署服务、发送邮件或操作收费。

已取得 fresh 上下文独立 `code-reviewer` 的完整报告：在提交 `23d2a60` 的邮件增量范围内未发现可行动问题。审查者独立执行同一 73 项定向测试、Ruff、提交 diff 检查，并核对 Supabase/Resend 官方合同。完整原文保存在 [独立审查证据](2026-10-13-mail-independent-review.md)。

首轮因 `stream disconnected before completion` 失败，消息传输还出现空 payload；恢复后取得可读取报告。期间为减少再次中断的影响另派过边界 reviewer，完整报告到达后已中止尚未形成结论的第二轮，不将其计为额外审查通过。原交付中的“独立审查未取得有效结果”是当时状态，由本次证据补齐。

## 客服邮箱事实

- 用户指定目标 `hello@notavue.io`，并明确确认已经创建、可收信、登录和回复。
- `dig @1.1.1.1 notavue.io MX`、`dig @8.8.8.8 notavue.io MX` 和对 `romina.ns.cloudflare.com` / `gannon.ns.cloudflare.com` 的权威查询均返回三条飞书 MX：优先级 1 `mx1.feishu.cn`、5 `mx2.feishu.cn`、10 `mx3.feishu.cn`；TTL 600，两家公共解析器返回 NOERROR + AD。
- 根域 TXT 读到飞书 SPF `v=spf1 +include:_netblocks.m.feishu.cn -all`。初次默认本机解析器的 MX 无 answer，未据此断言 MX 缺失；随后以上述公共/权威交叉查询核实。
- 已登录飞书后台显示 `notavue.io` 已启用，成员 `hello@notavue.io` 状态正常。经用户具体授权进入编辑页仅查看，“企业邮箱别名”为空；未填写任何字段，已点击取消退出，未保存。
- 早先计划的 Cloudflare 根域免费转发不能直接套用当前飞书托管配置。建议保留 MX，在飞书内给 `hello@` 添加 `support@notavue.io` 别名；初次只读核对时尚未添加，之后获授权添加的结果见下节；仍未验证 `support@` 的真实收信/回复。
- 飞书 CLI 的只读 profile 因用户 token 缺失未取得结果，未初始化/扩大权限；随后利用已有浏览器登录态只读核对。浏览器扩展接口缺少 Codex token，使用原生 Chrome UI 完成。未把 CLI 失败视为邮箱不存在。
- 自动审批最初拒绝进入“编辑基本信息”，理由为编辑流程超出只读授权；取得用户“允许仅查看，不保存”后完成只读核对并取消，未绕过拒绝。

## 主 Agent 已执行验证

在 `songdance/api` 执行：

```sh
.venv/bin/pytest tests/test_mail.py tests/test_mail_migrations.py tests/test_migrations.py -q --tb=short
.venv/bin/ruff check app/routes/mail.py app/services/mail_contract.py app/services/mail_delivery.py app/services/resend_client.py app/models/mail.py app/migrations/versions/014_mail_delivery.py tests/test_mail.py tests/test_mail_migrations.py tests/test_mail_real_services.py
.venv/bin/python -m compileall -q app/routes/mail.py app/services/mail_contract.py app/services/mail_delivery.py app/services/resend_client.py
```

结果：73 passed；Ruff 和编译通过。测试使用隔离 SQLite、合成签名与模拟 provider，没有真实发信。保留既有 Starlette/httpx 和 resampy 弃用警告。本轮未重跑临时 PostgreSQL、全量 API/Web、实际供应商投递或音乐质量回归。主 Agent 与审查者各自运行同一 73 项用例，不能合计为 146 个不同测试。

独立审查特别核对了 Supabase 整个 HTTP Hook（含重试）仅有 5 秒预算，且当前只以 Retry-After 非空判断可重试、并不按数值调度。本地 120 秒窗口只是同请求再次到达的接受上界，不能理解为 Supabase 会持续重投 120 秒；真实退避/超时行为仍须联调验证。

## 经授权添加客服别名

用户在明确预览“给 `hello@notavue.io` 添加 `support@notavue.io` 别名、共用现有收件箱并保持 MX 不变”后回复“允许”。本轮在飞书成员基本信息中仅新增企业邮箱别名 `support` / `@notavue.io` 并保存。保存后成员详情显示主邮箱 `hello@notavue.io` 和企业邮箱别名 `support@notavue.io`；刷新页面后仍可见。没有修改 MX/DNS、主邮箱、登录凭据或其它成员字段，没有发送测试邮件。

这是添加别名时的状态。后续用户指出已完成测试，主 Agent 从 `SD-20261013-01` 线程和外部收件箱核对了真实两端收发，专用私密测试配置已据证据设 support verified=true；完整 MAIL-01/05 仍保留其他待验项。最新证据见 [测试接入记录](2026-10-13-mail-test-connection.md)。

## 下一步

独立代码审查已完成，无确认问题需要代码修复。客服收发已在后续现场核实，下一步为已准备的 HTTPS 服务接通真实 Resend/Supabase 签名 secrets、Hook 与 OTP；以 [测试接入记录](2026-10-13-mail-test-connection.md) 的最新状态续接。MAIL-01–06 / BA-02、Google/Creem Test、生产政策/容量/音乐质量门槛继续待验。
