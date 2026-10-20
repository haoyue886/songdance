# 2026-10-20 已删除账户的保留账本退款修复

准备active订阅删除验收时，离线复现：成功付款→删除完成→收到已核实全额退款事件，原处理器持续retry，PaidPeriod仍active。根因是paid_periods._lock_user对所有调用都要求用户active；业务删除保留的既有交易也因此无法核对或更新，部分退款/争议同样受影响。这不符合BILL-03与AUTH-03的财务保留合同。

修复只允许停用账户的**精确既有交易**继续核对。原用户行锁和付款合同逐字段比较保留，锁查询populate_existing以读取最新active；grant_paid_period在无既有匹配交易时仍拒绝inactive用户的新账期。set_paid_period_status仍严格匹配用户、环境、交易，只允许frozen/revoked且已revoked不降为frozen。不会恢复用户、邮箱、任务或Free/Pro额度，不引入HTTP手工授额入口，不改Spec/迁移。

新增测试覆盖cleanup/completed两个阶段的全额退款、部分退款、争议六分支；全退能revoked且已停订阅仅GET核验verified，不重复取消；部分退款保留active与PARTIAL_REFUND_REVIEW，争议frozen，身份及停用墓碑保持。另验证删除完成后的新续费不能产生新PaidPeriod/UsagePeriod，仍保留事件retry。底层单测验证停用用户的既有30秒consume/15秒reservation不变，精确重放与状态更新可用，但新期、冲突产品、另一user的状态变更都拒绝。

## 验证

在api目录执行：

```sh
.venv/bin/python -m pytest -q tests/test_deleted_account_refund.py tests/test_paid_periods.py tests/test_billing_recovery.py tests/test_account_deletion.py tests/test_creem_billing.py --tb=short
SONGDANCE_TEST_REAL_AUTH_SERVICES=1 .venv/bin/python -m pytest -q tests/test_paid_account_deletion_real_services.py tests/test_billing_recovery_real_services.py tests/test_account_deletion_real_services.py --tb=short
SONGDANCE_TEST_REAL_AUTH_SERVICES=1 .venv/bin/python -m pytest -q tests/test_deleted_account_refund_real_services.py --tb=short
.venv/bin/ruff check app/services/paid_periods.py tests/test_paid_periods.py tests/test_deleted_account_refund.py tests/test_deleted_account_refund_real_services.py
```

结果：普通相关 **193 passed**，既有PG集成组合 **20 passed**，新增删除后财务投影PG专项 **7 passed**，Ruff及diff检查通过。PG测试均创建一次性集群/库并finally清理，身份及支付为离线替身，不访问既有验收库或供应商。测试初次fixture导入遗漏导致setup error，修正后复现原生产逻辑active≠revoked失败，再修实现通过；不把setup错误当业务缺陷。后续函数名/导入排序调整不改变场景。

fresh独立code-reviewer在生产修复与SQLite测试范围无可行动问题，独立隔离193项与Ruff通过；新增PG专项的fixture链与七场景已独立只读复核无可行动问题，未重复运行；实际PG7项为主Agent执行证据。未覆盖退款与删除同时执行的竞争。两条既有Starlette/httpx与pkg_resources弃用警告保留。本轮未运行Web、E2E、真实退款或真实删除，不将离线成功标为BA-13整体通过。

## 对当前进程的影响

真实active订阅删除仍处本地准备阶段，未获新付款/邮件/最终删除授权，也没有新外部调用。修复完成后才可继续安排“新Test付款→后台停费→删除→原交易退款”的供应商验收。原八份历史库、已完成删除墓碑和此前交易结果均不改，后续新隔离库须独立记录证据。
