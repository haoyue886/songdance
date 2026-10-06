# 可靠派发与账号提交幂等

日期：2026-10-07。基线 `55dbe87`。用户确认尚未配置独立 Supabase/Creem 测试项目，先继续本地开发。本批交付可靠任务接收与恢复，不开启收费或部署。

## 实现与边界

- 迁移 010 增加 `job_submissions`、`job_dispatches` 及任务 `dispatch_managed`，旧任务为 false。账号+key 唯一，提交绑定源字节 SHA-256、文件名和所选区间；同 key 内容变化拒绝，查询/重放校验归属。任务删除/24 小时清理保留提交墓碑和用量记录，过期重放 410，不创建新任务。
- `SONGDANCE_RELIABLE_QUEUE_ENABLED=false` 默认关闭。启用后任务、预占、提交记录与 uploading outbox 同事务保存；存储完成后置 pending。Redis 短时故障不会删除已接受的任务，HTTP 返回 queued，派发器退避恢复。存储中断后的原请求可找回 uploading 任务；恢复时校验完整源大小/哈希，缺失/不完整终止释放，存储服务不可用不误判缺失。
- 新游客请求先运行容量限流，登录用户以受限上传字节查幂等，确定新提交后在 ffprobe/FFmpeg 前限流。匿名有可靠派发，但未实现账号式提交重放/访客成功/IP 日账本。
- RQ 2.10.0 的 `unique=True` 原子入队使用现有散列 job+attempt ID；重复投递保留原 RQ metadata。Redis connect/read 上限 3/5 秒，关闭隐式重试由 outbox 控制。已 published 但 Redis job 消失时可重新发布；已 running 不重发。默认排队发布预算 900 秒，Worker 每次启动采用 900 秒硬超时+60秒回调余量。
- 同 attempt Worker 用 PostgreSQL session advisory lock（本地 SQLite 用 flock）防并行执行；失败/删除/attempt 状态在各写回路径检查。超时置失败与释放同事务，迟到 Worker/旧派发不能结算新重试，旧回调不释放新 attempt 的容量配额。执行锁异常退出后释放。
- 明确 retry 使用新 attempt/预占/dispatch；同 retry key 重发只返回该任务当前状态。前端草稿复用同一裁剪 File 和 UUID，网络/503/丢失响应可在额度已预占时重放；更换文件/选区重置资格。Retry key 在 sessionStorage 保存，空/null/错 ID 响应视为未知并保留。手工恢复 running 状态后继续轮询。
- 上传草稿仅保存在当前页面内存，整页刷新不恢复文件/上传 key；任务 retry key 支持标签页刷新。未实施匿名重放、YouTube outbox、供应商联调、完整选区证明或全部 BA。Redis 总丢失后的全局容量计数重建仍需暂停准入并核对，不以任务可重投证明计数已恢复。

## 验证

仓库根目录运行：

```text
songdance/api/.venv/bin/pytest -q songdance/api/tests/test_durable_jobs.py songdance/api/tests/test_dispatch_migrations.py songdance/api/tests/test_migrations.py songdance/api/tests/test_jobs.py songdance/api/tests/test_usage_ledger.py songdance/api/tests/test_entitlements.py songdance/api/tests/test_auth_ownership.py songdance/api/tests/test_phase6.py songdance/api/tests/test_transcription_service.py songdance/api/tests/test_settings.py songdance/api/tests/test_billing_ui_contract.py songdance/api/tests/test_queue_privacy.py
```

最终 **157 passed**，5 条既有依赖弃用提醒，76.18 秒。定向覆盖丢确认、上传中断、同 key 冲突、重复预占、删除、超时、恢复、迟到 Worker、独占执行和旧流程。迁移检查保留旧记录、空库往返、有历史拒绝降级。专项 Ruff、compileall 和 diff --check 通过。

api 目录 `SONGDANCE_TEST_REAL_AUTH_SERVICES=1 .venv/bin/pytest -q tests/test_dispatch_real_services.py tests/test_outbox_queue.py tests/test_queue_privacy.py`：**13 passed**，10.35 秒，真实临时 PostgreSQL/Redis。覆盖同 key 并发一次接收、跨账号隔离、派发竞争、删除/重试交错、数据库执行锁及 Redis 接收后丢确认。追加现有用量 PostgreSQL 验证见下述收尾记录。每例隔离数据库/队列，临时进程自动结束。

Web：`pnpm lint`、`pnpm typecheck`、`pnpm test`：38 文件 **235 tests passed**。默认 Turbopack `pnpm build` 在独立输出目录完成，93 页面。未引入依赖或修改音乐模型/质量门禁。

`node scripts/submission-ui-smoke.mjs`：**5/5 passed**，真实浏览器音频解码与裁剪+本地 HTTP 替身，外部请求 0。检查 503/已接收但响应丢失后同 key 同裁剪哈希返回原任务、更改草稿不能借旧请求绕过用量、空 Retry 响应跨刷新保留 key。截图 `web/test-results/songdance-submission-ui-VUrNUw`，主 Agent 实际查看手机超额禁用页，无截断/溢出。首轮失败包含 Chromium 自动 TCP 重发和控件名称定位问题，脚本改为服务端收下后拦截丢响应及按实际控件名称定位，未放宽业务断言。

独立 reviewer 首轮发现 Retry 空响应清 key、限流晚于 ffprobe，均修复；复审补发现错误恢复后停止轮询，已修并测试。审查服务一度中断，恢复后只读复审最终无遗留 P1/P2；独立执行 28 项 API 与 Node/JSDOM 恢复验证。真实 PG 新锁测试初次断言误插入旧测试作用域，已修正并重跑通过，不冒充首次即全绿。

追加 migration 010 后兼容回归：`SONGDANCE_TEST_REAL_AUTH_SERVICES=1 .venv/bin/pytest -q tests/test_usage_real_services.py`，**7 passed**（3.52 秒），验证原 Free/Pro 并发及单终态合同仍成立。

## 运行与接续

设置见 `../deployment.md`，服务声明 `../../infra/railway-dispatch.toml`，启动 `python -m app.jobs.dispatch --loop`。需要 migration 010、相同共享库/Redis/存储/签名及队列名，生产 Worker 使用可持有 session advisory lock 的 PostgreSQL 连接。关闭新准入开关后仍需让派发器处理既有 managed 任务，不能降级删历史或人工复投旧 attempt。未创建平台服务或启动生产开关。

下一本地任务：游客成功账本/IP 日额与账户周期任务摘要。真实 Supabase/Creem、完整支付/取消闭环、音乐人工/长音频和发布门禁保留未完成。未推送或部署。
