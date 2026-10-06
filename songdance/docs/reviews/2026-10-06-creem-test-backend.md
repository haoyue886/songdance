# Creem Test 后端交付

2026-10-06，基线 `4aaf223`。实现 checkout 意图、客户/订阅绑定、Portal、HMAC 原始体验签、持久 inbox、事务级授额与退款/争议投影。设置与官方原文链接见 [接入说明](../creem-test-setup.md)。默认关闭，固定 Test API 并拒绝 production/Live，未使用真实凭据或创建支付产品。

创建意图先提交再请求供应商。产品查询失败允许新 key 重试；POST 已发出的未知结果保留 uncertain，防止重复订阅。webhook 200 只表示持久 inbox；Worker 查询订阅/交易，校验绑定、金额、币种、周期后授额。checkout.completed/active 不单独授额。退款按原交易撤销，争议冻结账号新任务，部分退款留 review。取消保留已付周期；expired 仍可能重试扣款，不能当作 canceled。

## 实际验证

仓库根目录执行 API 定向回归：

```text
songdance/api/.venv/bin/pytest -q songdance/api/tests/test_creem_client.py songdance/api/tests/test_creem_billing.py songdance/api/tests/test_creem_failures.py songdance/api/tests/test_creem_migrations.py songdance/api/tests/test_migrations.py songdance/api/tests/test_entitlements.py songdance/api/tests/test_settings.py songdance/api/tests/test_auth_ownership.py songdance/api/tests/test_jobs.py songdance/api/tests/test_phase6.py
```

186 passed，5 条既有依赖弃用警告，35.81 秒。支付供应商使用离线协议替身。覆盖重复/乱序、超时恢复、签名/环境、部分/全额退款、旧退款与新周期隔离、Portal 归属、请求体限制、创建前失败恢复及配置拒绝 Live。

在 api 目录执行 `SONGDANCE_TEST_REAL_AUTH_SERVICES=1 .venv/bin/pytest -q tests/test_creem_real_services.py tests/test_usage_real_services.py`：13 passed，8.36 秒。真实临时 PostgreSQL 覆盖并发 checkout 一次 POST、重复事件一次 inbox、双 Worker 一次授额、009 部分唯一索引/降级保护，以及旧用量竞争。临时实例已结束，无现有服务或真实供应商操作。

全 app 与本批测试 Ruff、git diff --check 通过。独立 code-reviewer 首轮发现产品 GET 失败被永久置 uncertain，已修复补测；expired finding 经官方“仍可能重试扣款”原文核对撤回。复审 81 项支付测试通过，无遗留可行动问题。

## 未验收

真实 Creem Test 卡、供应商字段/税额与 Portal 取消、退款停止未来扣款、争议恢复、全历史交易枚举/每日平台调度、商业前端及完整 BA 仍未完成。当前对账只恢复已知 checkout、订阅最近交易和已存历史；多个未知历史周期需控制台核查。无 provider_id 的不确定创建需要签名 webhook 或人工确认，禁止删除意图后直接重购。未推送、部署或批准 Live。下一批接商业 UI 与真实 Test 配置验收，持续补齐这些阻断项。
