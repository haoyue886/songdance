# 38.2 Free 用量账本本地实现

日期：2026-10-06。范围为登录 Free 每 UTC 自然月 1 次成功转录的本地账本路径；不是 Creem、Pro 或商业化上线批准。

## 实现

- 迁移 007 新增 `usage_periods` 与不可变 `usage_ledger`，按用户、权益类型和 UTC 月份唯一建账；`transcription_jobs.usage_reservation_id` 关联任务预占。
- `SONGDANCE_USAGE_ENABLED` 默认 `false`，`SONGDANCE_FREE_MONTHLY_JOB_LIMIT` 默认 `1`。启用时，登录用户创建任务原子预占一次 Free 额度，现有 90 秒服务端选区校验继续生效。
- Worker 仅在任务成功完成并已有可用结果时消费；流水线失败、RQ 失败、上传/入队失败、删除失败/成功清理、主动删除和过期清理释放预占。reservation 的终态通过唯一约束和状态检查幂等；Worker 结算同时校验 attempt 与 reservation，迟到 Worker 不能结算新重试；账本记录不随任务清理删除，自动释放写入固定 reason。
- 游客 30 秒选区边界仅在用量开关开启时执行；Pro、Creem、游客成功体验独立账本、账号删除/停止续费未纳入本批。

## 验证

在仓库根目录执行：

```text
songdance/api/.venv/bin/pytest -q songdance/api/tests/test_usage_ledger.py songdance/api/tests/test_migrations.py songdance/api/tests/test_auth_ownership.py
```

结果：22 passed，1 条既有 Starlette/httpx 弃用警告。覆盖 UTC 月边界、Free 预占/释放/消费、重复终态幂等、登录端点第二次提交拒绝、重试入队失败释放、删除失败释放、迟到 Worker 栅栏、迁移和任务所有权回归。

另执行 `git diff --check`，无空白错误。数据库/Redis/真实 Supabase、Google、SMTP、Creem Test/Live、队列崩溃恢复和长音频未在本批验证。

## 独立审查

独立 `code-reviewer` 对当前最终 diff 复审结果为 0 个新增 P1/P2；重试入队失败、`DELETE_FAILED` 释放、attempt/reservation 迟到 Worker 栅栏和自动 release reason 已逐项核对并补测。复审不把范围外缺口视为通过项，也不勾选 38.2 或 BA 项。

## 未完成

- 38.2 的完整 BA-01/03–06/12 仍未勾选：Pro paid periods 与秒级计量、游客成功账本、可靠 outbox、跨月并发、完整 MIDI 覆盖判定及跨周期结算仍待实现或专项验收。
- `SONGDANCE_USAGE_ENABLED=true` 只能作为隔离测试配置，不能据此宣称生产免费额度或上线收费；真实认证/数据库权限及开关发布仍按 `auth-setup.md`、部署手册和 Phase 38.5 执行。
