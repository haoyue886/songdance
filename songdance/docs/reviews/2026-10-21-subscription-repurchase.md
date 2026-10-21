# 2026-10-21 到期重订及旧退款隔离本地验收

本批继续BA-09/10的本地指定分支，验证旧订阅停止与付费期到期两个独立重购条件。用户此前已停止原交易18分补退，该部分退款和review账本保持，不调用退款API，不恢复任何原Test库或站点，不增加供应商请求、邮件或真实付款。

新增 `api/tests/test_subscription_repurchase.py` 共6个参数化用例，复用现有临时SQLite/TestClient、离线FakeProvider、固定应用时钟和原签名事件/账单服务，不修改系统时钟或生产逻辑。

- active、scheduled_cancel、expired、past_due、unpaid五种未确认停费状态：状态经原事件处理落库后，推进到旧付费期精确结束，原checkout路由仍409/SUBSCRIPTION_EXISTS，供应商创建仍只有首次1次。这里expired是订阅状态，不能与checkout expired混淆；其可能继续重试扣款，不当作停止。
- 旧订阅canceled但原期未结束：仍409；旧期精确到期后新幂等键允许创建第二个checkout，传入原已绑定customer，不按邮箱重建客户。异key再次请求复用该pending意图，供应商创建总数2而非3。
- 新checkout completed及新交易paid经原sync_checkout/sync_transaction重复投影两次，只产生一个相邻新PaidPeriod；旧grant、旧usage全字段保持。随后旧交易全退，原退款投影仅旧期revoked，原停费补偿只核旧已canceled订阅为verified、repeat0，不发取消POST；新grant和新usage全字段不变，当前摘要仍Pro/1800秒。

旧退款在本批是离线构造的另一交易事实，不重试用户已停止补退的真实交易。新付款也仅本地协议夹具。新期首次授额未经过真实收银台或真实通知投递，本轮不把本地成功称为Creem真实续费/重订通过。

## 实际检查

在 `songdance/api` 执行：

```sh
.venv/bin/python -m pytest -q tests/test_subscription_repurchase.py tests/test_subscription_period_boundary.py tests/test_billing_recovery.py
.venv/bin/ruff check tests/test_subscription_repurchase.py
```

75 passed、Ruff通过，保留Starlette/httpx和pkg_resources两项已有依赖弃用警告；无生产改动，不需迁移或Web构建。测试使用fixture临时数据和fake供应商，原10库、真实身份/付款和18分差额记录不参与。

尚未验证真实Creem周期控制、同平台重订、浏览器重订及扣款次数、真实PG并发重订、平台退款/续费竞态；完整BA-09/10不勾选。下一真实供应商验收先核其可用周期推进/测试控制能力，不为模拟自然月而新建多笔重叠付款或改旧账期。

最终独立审查在4文件及相关计费调用链范围无可行动问题，独立新6项/Ruff通过，三文件收集75项与主Agent执行计数一致；未独立重跑全部75项，不涉及真实Creem、原数据库、PG并发重订或平台退款/续费竞态。断言及文档范围符合BILL-03/BA-09/10，本批只签收上述本地指定分支。
