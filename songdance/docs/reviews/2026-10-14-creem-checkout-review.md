# Creem checkout 局部独立审查

审查日期：2026-10-14。只读审查，未修改仓库、提交、推送或写入通过标记。

## Findings

### P2：显式 `request_id: null` 被当作字段缺失接受

位置：`songdance/api/app/services/billing.py:163`。

当前判断 `response.get("request_id") not in {None, checkout.id}` 无法区分属性缺失和属性存在但值为 null。若 Creem 创建接口返回其余字段合法的 200 响应，且 `request_id` 显式为 null，实际状态会落为 `pending` 并返回可跳转 checkout URL；本次验收目标要求“若字段存在仍必须匹配”，该输入应保留 `uncertain`。已缓存官方 Create Checkout schema 把该字段声明为可选 string，未声明 nullable（`/tmp/notavue-creem-create-checkout.md:177`，required 列表见第 278 行）。

已通过实际 `CreemClient` 加离线 HTTP transport 验证此路径可达；不是仅靠 FakeProvider 绕开适配器校验。若后续 GET 同样返回 null，`billing_events.py:116` 会拒绝关联，checkout 留在 pending，事件进入 retry，用户已能进入支付页却无法自动完成确认。未发现此输入能够绕过 GET 绑定或直接授额。

修复方向：单独判断字段是否存在；仅属性缺失可放行，属性存在时要求字符串值严格等于本地 checkout.id。新增显式 null 的回归用例，并保留现有缺失、空字符串及不同 request_id 的测试。

证据：临时测试 `test_present_null_request_id_requires_correlation_match` 断言期望 uncertain，实际得到 pending；完整路径观察测试进一步确认 checkout URL 被返回、后续 GET 无法关联、PaidPeriod 未生成。

## 审查范围与已核对行为

直接范围为四个当前 diff 文件：
- `songdance/api/app/services/creem_client.py`
- `songdance/api/app/services/billing.py`
- `songdance/api/tests/test_creem_client.py`
- `songdance/api/tests/test_creem_failures.py`

按调用链核对了 BILL-01/02、billing 路由、数据库约束、webhook/对账中的 sync_checkout 与 sync_transaction、前端幂等键清理和错误呈现，以及账户删除对未决 checkout 的处理。没有扩展到新 listener 或全产品审计。

已验证：
- 仅 POST /checkouts 的 HTTP 400 被分类为确定拒绝；官方文档将其定义为 Invalid input parameters。401/403/404/409/422/429/500/503 保留未知状态。
- 确定拒绝落为 failed，保留同 key 的幂等结果；新 key 可重试。其它未知结果继续复用已有 checkout，不重复创建。
- 同步缺失 request_id 可保存 provider_id；仅同步 completed 仍不授额。
- GET 中缺失、null、空字符串或不同关联值均不能生成订阅绑定或付费周期；provider_id 冲突和不同用户的重复 provider_id 也未重绑定。
- 回调先完成绑定后，同步创建响应不会把 completed 降回 pending。
- provider 原始错误 body 没有进入异常公开消息；本次变更未放宽托管 URL、Test 环境或交易核验。

除上述 P2 外，本次范围内未确认其它可行动问题，也未确认严重安全、重复授额或跨用户数据归属问题。

## 实际验证

所有 Python 测试从独立临时目录运行，使用清理后的环境变量、临时 SQLite/存储/临时文件路径、离线 provider/transport，关闭 pytest cache 和 Python bytecode 写入。没有读取 `.env`、`.data`，没有访问真实 Creem 或既有数据库。

1. 在 API 目录执行：
   `.venv/bin/ruff check --no-cache app/services/creem_client.py app/services/billing.py tests/test_creem_client.py tests/test_creem_failures.py`
   结果：通过。
2. 使用 API `.venv/bin/python -m pytest -q -p no:cacheprovider --basetemp <隔离目录>/pytest`，文件参数为 API 绝对路径下的 `tests/test_creem_client.py tests/test_creem_failures.py tests/test_creem_billing.py tests/test_billing_ui_contract.py`。
   结果：122 passed，2 条依赖弃用警告。
   工作目录：`/var/folders/yj/435qh6d544b93x6v2_p_dt6m0000gn/T/notavue-checkout-review-3clxpn5x`。
3. 同样隔离运行临时 `test_review_boundaries.py`。
   结果：8 passed、1 failed；失败即上面的 null 关联值问题。
   测试文件：`/var/folders/yj/435qh6d544b93x6v2_p_dt6m0000gn/T/notavue-checkout-review-extra-gj4c1fn1/test_review_boundaries.py`。
4. 同样隔离运行临时 `test_review_transport.py`，验证真实 CreemClient 在离线 HTTP transport 下的 9 种状态映射及 null 响应的当前行为。
   结果：10 passed；其中 null 观察用例通过表示成功确认当前错误行为，不代表该行为符合验收目标。
   测试文件：`/var/folders/yj/435qh6d544b93x6v2_p_dt6m0000gn/T/notavue-checkout-review-transport-nwv53wip/test_review_transport.py`。

未覆盖：真实 Creem Test 卡/供应商响应、PostgreSQL 并发与真实服务套件、浏览器实际渲染、全量 API/Web 回归。本轮未修改 UI，前端仅静态检查调用契约。GET schema 也将 request_id 列为可选；本次按指定安全目标保留 GET 严格绑定，实际供应商能否稳定返回关联字段仍需真实联调确认。

结论：发现 1 项 P2，建议修复显式 null 的判断后针对该分支复验；本报告不代表商业化或 Live 发布验收。
