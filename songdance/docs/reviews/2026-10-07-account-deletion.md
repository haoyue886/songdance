# SongDance 账户删除与跨周期结算

日期：2026-10-07；基线 `48cddc1`。用户要求继续本地开发，真实 Supabase/Creem 测试项目尚未配置。本批未推送、部署或开启收费。

## 交付范围

- 013 增加账户删除申请、连续失败计数与逐订阅核验记录；按账户幂等，有删除历史时禁止降级删除，兼容原身份、用量、付款和游客账本。
- `SONGDANCE_ACCOUNT_DELETION_ENABLED=false` 默认关闭；开启要求 auth/usage/reliable queue。`DELETE /me` 校验本站 Origin、明确 DELETE 确认、已验证身份的会话创建时间在最近 10 分钟；JWT 刷新或浏览器时间不作为重新登录证据。
- 先持久申请并阻止新任务/重试/购买/认领，再核对未决 checkout 与完整顾客订阅列表。未知绑定或环境转人工审查，不能猜邮箱归属；原订阅明示取消，GET 确认停止未来续费后才持久切换清理阶段。
- 清理阶段停用业务访问，分批删除任务、源文件/产物和邮箱。必要身份映射、交易/用量及删除审计保留；同一身份重新登录/换邮箱不会创建新业务账号。本人仍可凭有效供应商身份查询删除进度。不物理删除 Google/Supabase 用户。
- 文件失败持久保留 DELETE_FAILED 栅栏与原预占释放，迟到 Worker 不会回写消费。清理还覆盖所有历史 attempt 的已知产物，包含 PUT 完成但未登记的文件；任务删除与过期清理共用修复。旧模式上传也在任务行锁内完成 PUT，避免删除后写回。
- 已验证的后续订阅重新激活会重开停费处理，保持业务账号停用。Webhook、对账和退款取消中，财务投影失败不回滚已核验的停费义务；恢复不授新额度，也不复活账户。
- 累计 attempts 留作审计，另按连续 retry_failures 控制八次故障预算。成功批次不消耗故障预算；本人重新确认或受信 CLI 重放可重新启动故障预算，累计执行次数保留。
- 账户界面提供影响确认、重新登录、取消/清理/重试/审查/完成进度、有限轮询、查询恢复与支持入口。未知 DELETE 结果先 GET，不自动重发；核对当前 owner，账号切换清除旧确认。完成只信独立状态查询，邮箱显示清除，处理中和完成后隐藏不可用任务入口。

## 验证

API 目录最终执行：

```text
.venv/bin/pytest -q tests/test_account_deletion.py tests/test_account_deletion_client.py tests/test_account_deletion_migrations.py tests/test_lifecycle_attempt_cleanup.py tests/test_cross_period_jobs.py tests/test_auth_ownership.py tests/test_auth_coordination.py tests/test_creem_client.py tests/test_creem_billing.py tests/test_creem_failures.py tests/test_billing_recovery.py tests/test_billing_worker.py tests/test_billing_ui_contract.py tests/test_durable_jobs.py tests/test_guest_usage.py tests/test_entitlements.py tests/test_usage_ledger.py tests/test_task_summary.py tests/test_phase6.py tests/test_jobs.py tests/test_settings.py tests/test_transcription_service.py tests/test_migrations.py
```

**455 passed**，148.12 秒；5 条既有依赖弃用提醒。新增回归覆盖删除确认/状态/预算、关开关排空、未决 checkout、取消丢响应、分页绑定、清理失败、未登记 attempt 文件与其他任务隔离、财务投影失败后继续停费，以及旧流程兼容。CLI `python -m app.jobs.account_deletion --help` 可运行，恢复预算用例直接验证 CLI main；累计次数保留。

```text
SONGDANCE_TEST_REAL_AUTH_SERVICES=1 .venv/bin/pytest -q tests/test_account_deletion_real_services.py tests/test_cross_period_real_services.py tests/test_billing_recovery_real_services.py tests/test_creem_real_services.py tests/test_dispatch_real_services.py tests/test_usage_real_services.py tests/test_guest_real_services.py tests/test_auth_real_services.py
```

**54 passed**，62.12 秒；新临时 PostgreSQL/Redis，自行清理，没有使用现有服务。包含删除与创建/重试/购买/认领交错、并发工作进程、清理与迟到 Worker、真实只读 Supabase 风格会话表，证明 refreshed_at/新 JWT 不能替代 created_at。混合开关场景采用经 Settings 验证的独立配置对象，不依赖不可达 flag 组合。旧上传 PUT 的新增锁路径由既有接口回归覆盖，未另补独立 PG PUT 交错用例。

跨周期执行型 Agent 另验证 134 项相关回归与 2 项临时 PG：Free 跨 UTC 月、Pro 正常到期/取消与新付款、原预占期消费/释放、旧 Worker 跨期重试栅栏。30.1/90 秒选区校验服务器时长/哈希、实际模型输入首尾，90.001 秒拒绝。使用离线转录替身，仅证明运输、裁剪和结算，不替代真实音乐质量或完整 BA-06/LA。

Web `pnpm lint`、`pnpm typecheck`、`pnpm test` 通过，**41 文件 / 298 tests**；独立输出目录生产构建成功（93 页面）。最后隐藏删除后的返回任务链接后，相关 44 项定向测试、lint/typecheck 与浏览器流程重跑通过，不重复无关构建。

`node scripts/account-deletion-ui-smoke.mjs`：最终 **6/6 passed**，74 个本地请求、外网 0，真实浏览器与本地协议替身。覆盖默认关闭/旧响应、确认到取消重试/清理/完成、丢失响应查询、拒信创建响应的假完成、中文重新登录回跳、身份变化。截图目录 `web/test-results/songdance-account-deletion-ui-PFJ0Q0`，执行型 Agent 查看多组桌面/手机，主 Agent 查看最新完成态；375/1280 无横滚/重叠。

本批 app 与变更测试 Ruff、`git diff --check` 通过。未修改模型、音乐评级或放宽门槛，未重跑全量音乐质量集。新增 attempt 清理测试首轮误用了旧 helper 参数，修正到真实接口后通过；PG 同步 hook 首轮匹配过宽，收窄到候选扫描后通过，没有修改生产行为规避断言。

## 独立审查

fresh `code-reviewer` 确认三项 P2 并独立复验关闭：未登记 attempt 文件遗留、金融 savepoint 回滚丢失已核验停费义务、成功批次消耗故障预算。另执行型 PG 测试确认旧的非计费准入分支缺锁内删除门禁，修复并用合法混合配置复验。

独立审查者最终 **160 passed**（删除/客户端/迁移/既有计费恢复）与新 schema 的 PG **14 passed**；三条停费恢复入口和原多批次预算复现场景均实际验证。最终本次范围无未关闭可行动 P1/P2。审查者未执行浏览器或真实供应商，视觉证据采用上述实跑结果。

## 运行与下一步

设置见 [认证接入](../auth-setup.md)，模板 `../../infra/env.auth.example`。迁移至 013 后部署兼容工作进程，`python -m app.jobs.account_deletion --loop` 每 15 秒一批；已有申请在新准入关闭后仍需排空。没有创建平台服务。现有本项目本地 Web 预览 `http://127.0.0.1:3001/account` 已确认 HTTP 200，删除入口仍受关闭的服务端开关控制。

Supabase/Google/邮件真实重新登录、Creem Test 卡/Portal/取消列表合同、平台取消与续费外部竞争、正式保留/匿名化策略、音乐人工复评和 5/10 分钟能力尚未验收。此处本地 SongDance 停用与清理不等于供应商实体用户删除；不签收完整 Phase 38 或发布门禁。

下一本地项为商业化整条路径的端到端验收与测试环境配置检查，随后待独立供应商项目补真实登录、付款、转录、取消/删除证据。
