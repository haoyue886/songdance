# Test 支付历史对账与退款取消恢复

日期：2026-10-07，基线 `170691e`。用户确认先完成本地开发。本批没有连接真实商户、创建支付产品、推送或部署，既有收费开关保持默认关闭。

## 实现

- 012 迁移增加 `billing_cancellations`，全额退款撤销原交易额度与持久取消意图同事务；同环境/交易唯一，任何状态的取消历史均阻止降级删除。旧 011 数据不变。
- 工作进程持有取消意图和用户准入锁，核对原交易完整退款、订阅/用户绑定、本地后续已核实付款及供应商最新交易，向原订阅提交明确 `mode=immediate`。后续 GET 确认 canceled/scheduled_cancel 才记 verified。请求失败/未知结果留退避状态，下一轮先查询，不因成功响应丢失立即重发。
- 发现后续有效/冻结付款、最新交易变化或陈旧快照时持久转人工 review；重复 webhook/扫描不重置。旧退款只撤销原交易，不撤销新周期额度。最多 8 次后转 review，人工重放保留累计 attempts。CLI 使用 `--replay-cancellation-id=ID` 兼容前导短横线。
- Test 商户交易列表按官方 `items/pagination` 每页 100 条扫描，默认最多 100 页。记录数/页数/导航严格验证，重复、变化、失败或达到上限不报完成；对账下次从首页重跑并去重。
- 发现的订阅付款形成持久内部 inbox，重新 GET 交易/订阅核验后授权或撤销；未知订阅持久审查，不按邮箱自动认领，后来合法绑定可恢复处理。保存最小引用与财务指纹，不保存完整 provider body。外部 webhook 拒绝内部保留事件类型。
- `--loop --reconcile` 默认每日扫描，通知及取消每 15 秒处理一批；单次扫描未完成返回非零供 scheduler 发现。枚举完成与后续权益核验分开记录，部分退款及未绑定仍需审查。未创建外部调度资源。

## 核验与测试

使用 `dev-builder` 沿用账本、持久 inbox 和隔离测试模式；通过 `agent-reach` 的网页读取路由核验 Creem 官方交易列表、取消接口与退款说明。读取代理超时后直接读取官方 Markdown，来源见 [Test 设置](../creem-test-setup.md)。未新增依赖。

API 目录的扩展回归：

```text
.venv/bin/pytest -q tests/test_billing_recovery.py tests/test_billing_worker.py tests/test_billing_cancellation_migrations.py tests/test_creem_billing.py tests/test_creem_client.py tests/test_creem_failures.py tests/test_migrations.py tests/test_entitlements.py tests/test_usage_ledger.py tests/test_durable_jobs.py tests/test_guest_usage.py tests/test_billing_ui_contract.py tests/test_auth_ownership.py tests/test_settings.py tests/test_transcription_service.py
```

**300 passed**，83.32 秒，5 条既有依赖弃用提醒。该次覆盖付款、退款、原子补偿、历史周期、用户归属和原任务流程。随后加入分页类型/缺字段反例及已核实续费保护，按影响重跑：

- 执行型 Agent：`test_billing_recovery.py test_billing_recovery_real_services.py test_creem_client.py test_creem_billing.py`，**155 passed**（151 本地、4 临时 PostgreSQL），11.28 秒。
- 最终账本保护专用回归：`test_billing_worker.py test_billing_recovery.py`，**70 passed**，6.45 秒，包含等时间戳冲突快照与合法前导短横线恢复。
- 本批生产代码和所有变更测试的 Ruff、`git diff --check` 通过。

迁移执行型 Agent：SQLite 新旧迁移回归 **42 passed**；临时 PostgreSQL 的 009 历史保护/空往返、010 旧任务及用量升级 **4 passed**。

主 Agent 在 API 目录运行：

```text
SONGDANCE_TEST_REAL_AUTH_SERVICES=1 .venv/bin/pytest -q tests/test_billing_recovery_real_services.py tests/test_creem_real_services.py tests/test_usage_real_services.py tests/test_dispatch_real_services.py tests/test_guest_real_services.py
```

**35 passed**，36.42 秒，迁移 012 后既有支付、用量、可靠派发及游客并发仍通过。最终后续付款保护追加后重跑 `test_billing_recovery_real_services.py test_billing_worker.py`，**11 passed**，4.37 秒。测试自行建立/停止临时 PostgreSQL，无现有数据库或真实供应商写操作。

PG 取消竞争首轮失败来自测试 barrier 误匹配内部普通查询，收窄为真正候选查询后重跑通过；未修改生产逻辑规避。分页布尔值被 Python 等同整数的缺口已严格校验并覆盖。本批没有修改 Web/UI，未重复浏览器或音乐模型质量测试。

## 独立审查

fresh `code-reviewer` 确认并独立复验三项问题：savepoint 回滚丢失已见新付款导致下一轮旧快照误取消；等时间戳旧快照忽略本地已核实续费；以短横线开头的恢复 ID 被 argparse 当选项。现分别持久转 review、用户锁内查后续付款账本、用等号形式且固定反例测试，全部关闭。

审查者独立定向检查最新 **149 passed**，同时用隔离真实调用链复验两类旧退款/新续费交错，最终范围内无遗留可行动 P1/P2。其 149 项执行时专用等时间戳永久用例尚未加入，后者由主 Agent 的 70/11 项最终验证覆盖，不混记。审查者未运行 PG 或真实 Creem，采用上述独立执行证据。

## 运行与接续

配置和恢复命令见 [Creem Test 设置](../creem-test-setup.md)。先迁移至 head 012，升级兼容的 billing worker。关闭 checkout 后继续排空通知/退款取消意图；禁止删除账务历史或用 schema 降级代替事故恢复。

本地两次 GET 与用户锁不构成供应商取消/续费原子操作；没有官方条件式取消合同，边界竞争仍需真实 Test 验证与人工处理。取消后周期字段、税额、商户分页行为、动态历史变化、Portal/真实支付及完整 BA 尚未验收。保留原模型质量/人工复评与 5/10 分钟门槛，Pro 实际仍限 90 秒。

下一本地项为跨周期任务结算/完整选区端到端及账号删除停止续费流程。实际供应商配置、法律/客服、收费开放与部署仍待完成。
