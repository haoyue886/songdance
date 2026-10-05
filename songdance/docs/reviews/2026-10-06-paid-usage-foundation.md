# Pro 已付周期与秒级用量基础

日期：2026-10-06。基线 `9bef907`。本批交付内部付款事实投影和用量基础，不包含 Creem checkout/webhook 或真实收费。

## 行为

- 迁移 008 新增 `paid_periods`。付款事实包含环境、交易、订阅、产品、套餐版本、最小货币单位金额、币种和真实起止 UTC；重复事实返回同一周期且不重置用量/撤销状态，冲突拒绝。用户周期重叠拒绝，同订阅跨用户绑定通过 PostgreSQL 事务 advisory lock 串行。
- 内部 `grant_paid_period` 不核验 Creem 付款，也无 HTTP 授额入口。后续支付接入必须先核实付款、产品、用户绑定和环境，不能把本函数的测试输入视为真实到账。
- 本地 Pro 周期默认 1,800 秒；上传采用服务端实际解码选区时长，`max(15, ceil(seconds))`。重试使用已存服务端 source duration。有效付费周期优先；耗尽/冻结/撤销不转扣 Free；正常到期回到该 UTC 月份原有 Free 额度，旧预占结算仍归旧期。
- `/billing/me` 只返回当前账号的计划、单位、预占/消费/剩余和 UTC 边界，`private, no-store`；开关关闭时返回 enabled=false。账号最多一个有效排队/运行任务。Pro 独立配置 IP 安全小时预算，内存/Redis 均保留全局活跃及日预算。
- 修复基线仅查相同终态造成的 release→新任务预占→迟到 consume 漏洞：consume/release 使用同一互斥数据库索引，余额通过条件 UPDATE 预占，任一终态都阻止另一终态。结算 helper 不自行提交；结果、失败、队列失败和删除意图与用量在调用者事务内提交。
- 用量任务生成清洗 MIDI 后实际解析并校验非空音符及有限正时间轴；MusicXML 单独失败而 MIDI 可用仍消费。相同 attempt 的迟到结果不得删除已发布 MIDI。完整处理选区证明仍属后续验收，基本解析不等于 BA-06 通过。
- 用量模式下关闭未接账本的 YouTube config/提交入口，避免绕过额度。旧开关关闭路径继续回归。

## 配置与迁移

- `SONGDANCE_USAGE_ENABLED=false`、`SONGDANCE_PAID_USAGE_ENABLED=false` 均默认关闭；`SONGDANCE_BILLING_ENVIRONMENT=test`。Production 拒绝启用 Test 付费权益，Test/Live 查询隔离。安全 IP 小时上限 `SONGDANCE_PAID_IP_HOURLY_JOB_LIMIT=60` 是本地可配置初值，需按容量验收冻结。
- 先在隔离环境执行 `alembic upgrade head`。008 保留已有 007 Free 账本；检测到已有 consume+release 冲突时停止并要求有审计的人工对账，不删除/改写历史制造迁移成功。此前未结算的终态任务也须对账后再启用。
- 空付款表可回滚 008；已有付款记录时拒绝降级删除该表。生产回退须保留数据库、用量执行和既有已付权益，仅关闭新购买/新授权入口，不能通过切换环境或关闭账本把既有用户转成 Free。当前没有生产开关操作。
- 本地 Pro 单次仍为最多 90 秒（模型及迁移均有上限）；不得售卖 5/10 分钟，等待 Phase 39。

## 验证证据

命令从 `songdance/api` 执行，均使用隔离临时库、存储和测试账号。

```text
.venv/bin/pytest -q tests/test_usage_ledger.py tests/test_paid_periods.py tests/test_entitlements.py tests/test_migrations.py tests/test_auth_ownership.py tests/test_jobs.py tests/test_phase6.py tests/test_transcription_service.py tests/test_settings.py tests/test_youtube.py
SONGDANCE_TEST_REAL_AUTH_SERVICES=1 .venv/bin/pytest -q tests/test_usage_real_services.py tests/test_paid_quota_redis.py
```

- PostgreSQL/Redis 最终 14 passed。真实临时 PG 覆盖 007→008 带数据迁移、部分唯一索引、20 秒并发两次 15 秒、Free 首次月份竞争、consume/release 竞争、同订阅跨账号竞争；真实 Redis 覆盖双实例 IP 限流、预算隔离、取消幂等、完成不回补、共享全局和日熔断。临时进程均清理。沙箱首次阻止回环监听，经自动权限审核后实跑，不使用现有服务。
- 独立 reviewer 的临时 PG 对照证实旧 User FOR UPDATE 与结算外键 KEY SHARE 死锁；本批 User FOR NO KEY UPDATE 后两事务成功。独立 Pro 第四次上传/迟到 persist_result 产物保护复现均通过。
- 静态检查：全 app 与本批测试 Ruff、`python -m compileall -q app`、`git diff --check` 通过。依赖弃用警告保留，未安装新依赖。
- 独立审查发现的 Pro 旧 IP 限流、已发布产物删除及 PostgreSQL 锁问题均修复；最后一次复审无未修复 P1/P2。Redis 新用例发现容量错误分类差异，改为 paid 分支显式跳过 client 活跃限制后 14 项服务回归通过。

- API 定向与相关回归最终 **190 passed / 5 既有依赖弃用警告**（55.75 秒），覆盖上列十个测试文件。未重跑完整音乐质量套件，历史人评/指纹缺口不计为本批通过；Web/UI 未改动，本批无新浏览器验收。

## 接续

38.2 与 BA checkbox 继续保留未完成。下一实现为 38.3：核对官方 Creem API/事件合同，持久 webhook inbox、验签、权威付款核验、幂等 checkout、Portal 和对账，调用本批内部授额接口。游客成功/IP 日额、可靠 outbox/提交幂等、完整选区覆盖、账号删除先停止续费、商业 UI 及真实供应商/生产验收仍待完成。未推送、部署、创建支付产品或开放真实收费。
