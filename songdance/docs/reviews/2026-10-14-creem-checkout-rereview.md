# Creem checkout 修复复审

日期：2026-10-14。只读核对当前 diff；未修改仓库、提交、推送或写入通过标记。

在本次范围内未发现可行动问题。上一轮 P2 已解决。

## 复核结果

- `songdance/api/app/services/billing.py:163` 现在使用字段存在性判断，仅缺失 request_id 时放行；显式 null、空字符串、不同字符串、对象或数组都不能匹配本地 checkout.id，会保留 uncertain。
- `songdance/api/tests/test_creem_failures.py:94` 已在冲突回归中增加 None、空对象、空数组；检查了不会保存 provider_id、不会创建 PaidPeriod，换 key 也不会重复发起 POST。
- 重跑上一轮独立临时测试，原先失败的显式 null 用例现已通过。缺失字段仍能创建 pending 会话；GET 缺失/冲突仍不能绑定或授额；provider_id 冲突、同步 completed 不授额、回调先到不降级等边界均通过。
- 本次修复没有改变 HTTP 400 确定拒绝的分类范围或后续 GET/交易校验。原四个范围文件的 Ruff 检查通过。

## 实际验证

命令均使用项目 Python 3.11 虚拟环境。测试从新临时工作目录执行，清理环境变量、关闭 pytest cache 和 bytecode，临时 SQLite/存储及离线 provider 隔离；未读取 .env/.data，未访问真实 Creem 或既有数据库。

1. API 目录：
   `.venv/bin/ruff check --no-cache app/services/creem_client.py app/services/billing.py tests/test_creem_client.py tests/test_creem_failures.py`
   结果：All checks passed。
2. 执行 `.venv/bin/python -m pytest -q -p no:cacheprovider --basetemp <隔离目录>/pytest`，路径参数为：
   - API 的 `tests/test_creem_client.py`
   - API 的 `tests/test_creem_failures.py`
   - API 的 `tests/test_creem_billing.py`
   - API 的 `tests/test_billing_ui_contract.py`
   - `/var/folders/yj/435qh6d544b93x6v2_p_dt6m0000gn/T/notavue-checkout-review-extra-gj4c1fn1/test_review_boundaries.py`
   结果：134 passed，2 条依赖弃用警告。包含 125 项仓库测试及 9 项上轮独立边界测试，全部通过。

本轮隔离工作目录：`/var/folders/yj/435qh6d544b93x6v2_p_dt6m0000gn/T/notavue-checkout-rereview-3sknalzw`。

未覆盖真实 Creem Test 卡/供应商响应、PostgreSQL 并发、浏览器实际渲染及全量 API/Web 回归。本结论仅针对指定 checkout 拒绝分类与可选 request_id 的 diff 及调用影响，不代表商业化或 Live 发布验收。

上一轮发现及失败证据保留在 `/tmp/notavue-creem-checkout-review.md`；其 P2 已由本轮复审确认解决。
