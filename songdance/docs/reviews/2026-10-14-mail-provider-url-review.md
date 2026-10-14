# Supabase 邮件项目 URL 与固定诊断增量审查

2026-10-14，fresh 独立只读审查。结论：在本次范围内未发现可行动问题，未确认 P0/P1/P2/P3 finding。

范围为 HEAD `23d2a601b608d4715176540f017cba07ad24573d` 上的工作区增量：

- `/Users/lixinyue/Desktop/project/songDance/songdance/api/app/services/mail_contract.py:133`：`email_data.site_url` 改为绑定配置的 Supabase 项目 origin 或该 origin 的 `/auth/v1`。
- `/Users/lixinyue/Desktop/project/songDance/songdance/api/app/routes/mail.py:73`：失败路径新增固定字段诊断。
- `/Users/lixinyue/Desktop/project/songDance/songdance/api/tests/test_mail.py:170`：对应诊断、合法 URL、恶意/不匹配 URL 回归。

按根 AGENTS.md 与 `.agents/skills/code-review/SKILL.md` 执行；原邮件提交和 test-only listener 未重新全量审查。追踪了设置校验、签名解析、`otp_message`、发送及回调服务、`log_event`/JSON formatter 的直接相关调用者，并核对 AUTH-04、MAIL-03/06 要求。

核对结果：

1. 所提供的当前官方源码 `/tmp/songdance-supabase-mail.go:842` 将 `SiteURL` 设为 `externalURL.String()`；`/tmp/songdance-supabase-middleware.go:380` 默认由 `config.API.ExternalURL` 得到该 URL，允许外部 host 时也来自供应商配置白名单。与当前改动的项目 API origin 绑定一致，旧的应用 Site URL 相等条件不符合该合同。
2. 设置验证在启用邮件时将 `supabase_url` 精确绑定到 20 位 `mail_project_ref`；新比较没有宽泛 host 后缀匹配或 URL 前缀匹配。不同项目、恶意子域、userinfo、附加 query/verify 路径及非字符串输入均安全拒绝，且不会调用发送供应商。
3. 模板仍仅使用经过服务端验证的 `mail_site_url` 生成 `/privacy`、`/refund`、`/contact`，未使用 payload 的 `site_url`、`redirect_to`、metadata 或 token_hash。
4. 新日志只含固定事件名、固定供应商枚举、固定 `MailError` 错误码和内部状态码。检查了所有可达 MailError 构造点，没有把异常字符串、供应商正文、邮箱、OTP、token_hash、密钥或完整请求体作为日志字段；数据库/超时异常统一映射为固定错误。

实际验证：

- 用 API `.venv/bin/python -B -m pytest -q -p no:cacheprovider -c <api>/pyproject.toml <api>/tests/test_mail.py --basetemp <隔离临时目录>/pytest`：77 passed，2 条现有依赖弃用告警，13.64 秒。进程使用清空后重建的测试环境、临时 cwd/SQLite/storage/temp、`PYTHONDONTWRITEBYTECODE=1`；发送全部为 MockTransport。未载入 `.env*.local`，未接触真实队列、库或邮件供应商。
- `songdance/api/.venv/bin/ruff check --no-cache songdance/api/app/routes/mail.py songdance/api/app/services/mail_contract.py songdance/api/tests/test_mail.py`：通过。
- `git diff --check --` 上述三个文件：通过。

未覆盖：未确认线上 Supabase 实际部署版本及其真实签名 payload；未调用真实 Supabase/Resend，未发送真实邮件；未验证三家邮箱投递、认证头、OTP 验证/过期/复用或生产可用性。上述属于后续真实联调/MAIL 验收，不因本轮局部审查结论而视为完成。本轮未修改仓库、提交、推送或写入审查通过标记。

审查时文件 SHA-256：

- mail_contract.py：`f38ae0ce2f18455e0a0949fccbe21ee9cd495e437126ff8d2f051ce0e5539aa5`
- routes/mail.py：`f69f37497edda8fb2bff458907149ad4457d782fca90156d50c6d4c4a92df1d9`
- tests/test_mail.py：`f25bd9c792e10e65b34470211a67fdad1721b7d4311cb4f24f438085bf72ab7c`
