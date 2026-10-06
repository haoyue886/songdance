# 游客体验账本与账户周期任务摘要

日期：2026-10-07；基线 `9806cf2`。用户已确认先完成本地开发，未配置独立 Supabase/Creem 测试项目。本批未推送、部署或启用收费。

## 完成范围

- 迁移 011 新增 `guest_trials`、`guest_days`、`guest_submissions`、`guest_ledger` 和任务的游客预占标识；保留旧任务数据，有游客历史时拒绝降级删除。账本与任务文件生命周期分离。
- 服务端签名访客标识绑定一次成功体验。创建原子预占体验及每 IP 每 UTC 日一个新任务的名额，任务/outbox/提交键同事务。无效音频/选区回滚准入；任务接受后失败只释放成功体验，不退 IP 日名额。原任务最多两次重试，不占新日名额。
- 可用 MIDI 才消费；无音符、无效 MIDI、处理失败、删除或过期清理释放。单终态索引和身份锁防重复结算。成功后删除不返还体验。认领沿用原游客预占与访问归属，不消费 Free/Pro；已认领重试仍遵守账号活跃任务限制。
- 同访客/key/内容重放返回同一任务和访问凭证，变更内容拒绝，过期/删除/认领后返回 410。关闭新准入开关后仍可恢复旧提交（须保留签名密钥），既有任务继续结算和排空。
- 账户摘要从当前权益周期的用量流水聚合，不依赖临时任务行；同任务重试合并，成功优先，其次进行中，其余释放计为“未成功/已取消”。周期/账号隔离，认领游客不计入 Free/Pro。清理后计数保留。
- 前端保存访客签名，上传携带；额度耗尽禁用新任务，未知响应允许原草稿重放。价格页说明 IP UTC 日限制，裁剪提示使用实际 30/90 秒上限。八语参数同步，中英文翻译、其余语言保留既有英文回退。隐私说明明确访客浏览器存储与防重复记录独立保留。

## 验证记录

API 目录执行：

```text
.venv/bin/pytest -q tests/test_guest_usage.py tests/test_task_summary.py tests/test_durable_jobs.py tests/test_dispatch_migrations.py tests/test_guest_migrations.py tests/test_migrations.py tests/test_jobs.py tests/test_usage_ledger.py tests/test_entitlements.py tests/test_auth_ownership.py tests/test_phase6.py tests/test_transcription_service.py tests/test_settings.py tests/test_billing_ui_contract.py tests/test_queue_privacy.py
```

**192 passed**，111.18 秒；覆盖新账本、任务成功/失败/删除/清理、迁移历史保护及既有认证/用量/派发行为。5 条既有依赖弃用提醒。

```text
SONGDANCE_TEST_REAL_AUTH_SERVICES=1 .venv/bin/pytest -q tests/test_guest_real_services.py tests/test_dispatch_real_services.py tests/test_usage_real_services.py
```

**24 passed**，26.00 秒。修复默认容量下同键重放后追加：

```text
SONGDANCE_TEST_REAL_AUTH_SERVICES=1 .venv/bin/pytest -q tests/test_guest_real_services.py tests/test_guest_usage.py
```

**29 passed**，23.53 秒（其中 10 项真实临时 PostgreSQL，19 项本地行为）。数据库每例隔离；测试自行创建/停止临时 PostgreSQL，没有使用现有数据库。身份与队列为本地替身，不冒充真实 Supabase/Creem 或模型质量测试。

Web 目录：`pnpm lint`、`pnpm typecheck`、`pnpm test` 通过，**39 文件 / 254 tests**。`SONGDANCE_NEXT_DIST_DIR=.next/guest-build-20261007 SONGDANCE_TSCONFIG_PATH=.next/commercial-build-config/tsconfig.json pnpm build` 成功，93 页面；隐私文字补充后定向检查 i18n。

`node scripts/guest-ui-smoke.mjs` 最终 **5/5 passed**，外部请求 0：身份刷新复用、日限额错误、耗尽禁用、未知响应重放及更改选区阻断、Free 账户摘要。真实浏览器音频解码/裁剪配合本地 HTTP 协议替身；不证明真实供应商连通。最终截图目录 `web/test-results/songdance-guest-ui-8rTmoQ`，主 Agent 查看桌面实际 30 秒提示及手机账户摘要，无溢出。首轮测试替身错误使用 HTTP 200 返回未登录，修正为实际合同 401 后重跑通过，没有改业务逻辑迎合替身。

本批生产代码与变更测试 Ruff、`git diff --check` 通过。全量 `ruff check app tests` 报 4 项既有历史候选脚本问题（3 个 E501、1 个 F401），四文件与 HEAD 完全相同；未为通过格式检查改写历史实验脚本。没有重跑全量音乐质量集或修改既有质量门槛/评级。

## 独立审查

fresh `code-reviewer` 首轮复现两项 P2：认领后游客重试漏账号并发限制，以及默认 IP 活跃上限 1 时同 key 并发请求抢先被拒。前者抽出共享账号活跃检查，后者在容量准入前串行化访客提交、通过线程池等待锁避免阻塞前一上传。均补回归并独立复验；最终本次范围内无遗留可行动问题。审查者独立执行 35 项定向检查、最终 23 项行为/摘要测试和两种交错复现；PG/页面证据由主 Agent 执行。审查服务中途一次不可用，重试后完成，不以失败调用充当通过。

## 配置与下一步

`SONGDANCE_GUEST_USAGE_ENABLED=false` 保持默认关闭；启用要求 auth/usage/reliable queue、迁移 011 和独立稳定游客密钥。配置模板与密钥轮换/排空注意事项见 `../auth-setup.md` 和 `../../infra/env.auth.example`。无需浏览器或 Worker 持有游客签名密钥。

Free 保持每 UTC 自然月 1 次成功转录、单次 90 秒；Pro 当前仍 90 秒，5/10 分钟没有通过验收。游客识别仅尽力控制，清存储与换 IP 可绕过，共享 IP 共用日额，当前未实现多密钥轮换和防滥用记录自动删除政策。

下一本地项：扩大支付对账覆盖，补退款/停止续费的一致性与故障恢复。真实 Supabase/Google/SMTP、Creem Test、生产法律/客服配置、完整选区/跨周期端到端、音乐人工复评和长音频门禁仍待完成；不签收整个 Phase 38。
