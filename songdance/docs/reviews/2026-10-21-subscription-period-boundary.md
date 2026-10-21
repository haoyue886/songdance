# 2026-10-21 续费失败与付费周期边界本地验收

用户已明确停止上一笔Test交易剩余USD0.18补退，保留部分退款和差额记录后继续其他验收。本批独立验证BA-09的指定本地分支，不恢复原数据库或服务，不调用供应商、不发信、不新建真实付款。

## 本批覆盖

新增 `api/tests/test_subscription_period_boundary.py` 共6个参数化用例，沿用项目TestClient、临时SQLite、离线FakeProvider、签名通知入口和原支付/权益服务；可控时钟推进到2030年2月1日精确边界，不修改系统时间或旧账本。

- canceled、scheduled_cancel、past_due、unpaid四种订阅状态只更新原订阅状态：已核实原付款在截止前仍为Pro/1800秒，到期时转为本自然月尚未用过的Free/1次。旧PaidPeriod和1800/0/0用量原样保留，不提前撤销、不延长已付期，也不自动取消或重新结账。
- declined、uncollectible两类失败续费发来paid形状通知时，原权威交易核验拒绝授新期，事件持久retry；原期到期后仍为Free。相同交易后续实际变paid，再收同事件3次，仅产生一份相邻新周期；旧失败事件退避到期重放及原GET投影仍保留同两份grant/usage id、新期1800秒，而非累加3600秒。

保留历史grant为active不等于过期后仍可使用，准入按 `period_start <= now < period_end` 选择当前期。该测试不涵盖同月Free已用情况（已有相关测试），不宣称恢复重订或供应商真实续费已验证；续费失败事件的具体输出仅是本地协议夹具。没有真实跨月等待或测试时钟API调用。

## 检查

在 `songdance/api` 实跑：

```sh
.venv/bin/python -m pytest -q tests/test_subscription_period_boundary.py tests/test_billing_recovery.py tests/test_cross_period_jobs.py
.venv/bin/ruff check tests/test_subscription_period_boundary.py
```

结果82 passed、Ruff通过。保留Starlette/httpx、pkg_resources及audioread导入的aifc/audioop/sunau共5项已有依赖弃用警告；没有新失败或为通过放宽断言。本批不改生产逻辑或Spec，不需要API迁移或Web重建，未重复音乐质量或部署检查。

全部数据库和文件由测试fixture在临时目录管理，不使用原10份商业Test库/任何真实支付身份，不需用户第三方操作。原18分未退差额、partialRefund review及Test订阅canceled事实保留，不冒称全额退款通过。真实多周期续费、重订、续费与退款平台竞态和完整BA-09继续待验。

独立审查指出处理数1不能证明状态同步成功，现增加精确BillingSubscription状态和对应inbox processed/error为空的断言；旧失败事件重放后也显式核processed。修正后主Agent重跑新增6项与Ruff通过；此前组合82项中其余76项未受断言补强影响，不重复无关测试。审查者用离线故障注入使状态同步抛错，确认四种状态测试均会失败，不会把retry冒充成功。

最终独立复审在本次5文件及受影响调用链范围无可行动问题，独立新增6项/Ruff通过；未重跑全部82项、未连接供应商或原数据库，不扩大为真实多周期/重订/平台竞态通过。
