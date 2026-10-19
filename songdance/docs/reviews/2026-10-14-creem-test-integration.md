# 2026-10-14 Creem Test 真实联调

**指定 Test 环境已完成 Google 登录 → Creem 模拟付款 → 1,800 秒到账 → 真实转谱/三格式导出 → Portal 取消续费 → 全额模拟退款/权益撤销。** 本轮仅完成一笔模拟付款和退款，没有真实扣款。四类真实签名通知全部处理成功；临时 webhook 已禁用，本轮本机服务和独立数据库/Redis均已关闭。完整商业化、音乐质量和生产验收继续待补。

2026-10-15 续验已完成第二笔授权模拟交易的漏通知对账恢复、单页两笔商户历史、active 退款自动停止续费、退款后页面/退出；见 [补充验收记录](2026-10-15-creem-reconciliation.md)。下文是10月14日当批事实与边界，不将其历史未验项误作最新状态。

## 实际配置

| 项目 | 实际状态 |
|---|---|
| 商店/环境 | moonAI，Creem Test Mode；未切 Live |
| 商品 | `prod_6VunYruwAmrEXb70DJdNrl`，已由 SongDance Pro Test 保存为 Notavue Pro Test |
| 合同 | USD 990 分/月，every-month，30 分钟/已付周期，单次最长 90 秒，无试用或 usage_prices |
| Test 密钥 | Notavue Test Integration；checkouts read/write、products read、customers read/write、subscriptions read/write、transactions read；Full access 关闭 |
| Webhook | Notavue Test Billing；仅 `/webhooks/creem`，13 类既有账务事件；现已禁用 |
| 本机应用 | `http://localhost:3002`，API `http://127.0.0.1:8002`；默认功能开关始终保存在 false |
| Supabase | songdance-test；沿用 Google provider 与既有 9 字段专用 session reader |
| 认证回跳 | Site URL 改为 `http://localhost:3002`；两条精确 allowlist 为 localhost 与 127.0.0.1 的 `/api/auth/callback`，无通配符 |
| 业务资源 | 独立 PostgreSQL、Redis、RQ 队列及 `.data/notavue-creem-test-20261014` 存储，未借用已有业务库/队列 |

Client key 和 webhook secret 经用户授权的本机剪贴板传入 `.env.commercial-test.local`，文件 0600 且被 Git 忽略；剪贴板已替换为普通文本。Web 进程仅接收所需公开/Auth 配置，不接收 Creem key、webhook secret 或数据库 DSN。邮件 Hook、账户删除和游客新准入本轮未启用。

## 真实证据

1. Test 商品 API 返回 200：Notavue Pro Test、mode=test、price=990、currency=USD、billing_type=recurring、billing_period=every-month，无试用/计量附加项。真实收银台、客户 Portal 和商户退款页均显示 Notavue Pro Test；商店名仍为 moonAI，未将产品改名扩展为商户身份变更。
2. Chrome 从 localhost Notavue 登录页经真实 Google/Supabase PKCE 返回账户页，初始为 Free 1 次。支付邮箱是用户授权的 hello@notavue.io；应用归属仍按已登录身份和 checkout 绑定，不按付款邮箱猜测。
3. 一笔官方 Test 卡付款：商品 990 分，德国测试账单 19% 税额 188 分，模拟实付 1178 分。用户现场确认了该含税总额和收银台条款。交易 GET 实际返回 amount=990、amount_paid=1178、tax_amount=188、status=paid、mode=test，周期为毫秒时间戳。
4. `subscription.paid` 先到时因关联未就绪进入一次 retry；`checkout.completed` 完成绑定后自动处理成功。账本仅一份 1,800 秒权益，没有因两类事件重复授额。返回页先出现超时提示，刷新后显示 Pro access active；账户页实际显示 Pro 月付、剩余 1800 秒、已用/预占 0。
5. 当前测试浏览器完成 `01-bach-capriccio` 约 30 秒片段任务 `JK4oa2dgjeL7PpSnOelhWa3GZBomfYWl`，真实 RQ/Basic Pitch Worker 成功，实际页面可见五线谱、272 个 MIDI 音符、版本与不确定性提示。账本恰有 reservation=30、consume=30 各一次，remaining=1770、reserved=0；账户周期摘要成功 1 次。
6. 浏览器实际下载下列三个文件；MIDI 可解析，MusicXML 可解析，PDF 头尾完整、5 页 A4，Title/Creator 为 Notavue。PDF 第一页已渲染并查看，谱面与标题可见；没有对全部页作专业音乐复评。清洗后 MIDI 下载由既有客户端解析/重写，字节哈希不要求与服务端 MIDI 相同。

| 导出 | 字节 | SHA-256 |
|---|---:|---|
| MIDI，272 音符 | 2295 | `f9b0bc1f90d176c13fbd68313ffaa5654c37f59f406be47431ee2c3d83e4c8ff` |
| MusicXML，396 个 note 元素（含休止等），1 part | 115388 | `71cec622b0fdf85ccffed7a3ff94548ad8fba6fa274f13e36d40fe34b29d4ba5` |
| PDF，5 页 | 403611 | `c1cf2aa68586e99d4410aaeeca89ceac1fc56f7e6bb8cb8143ddd00e3f738955` |

7. 从应用“管理账单”进入真实 Test Portal，取消未来续费。Portal 显示 Canceled、结束于 2026-11-14；`subscription.canceled` 通知处理成功。权威订阅状态为 canceled，原已付周期仍 active，1770 秒保留。
8. 商户 Test 付款页按客户请求全额退款 11.78 美元；刷新页面实际显示已退款。权威交易返回 refunded_amount=1178、status=refunded；`refund.created` 已处理，PaidPeriod=revoked，持久取消核验=verified。该订阅此前已经取消，此处验证的是“退款后确认已停止”的分支，没有实测对 active 订阅自动发出取消 POST。
9. 退出浏览器核对前，审批服务自身 API key 额度耗尽，最后的退款后账户 UI/退出未完成；没有将其记为通过。随后使用实际测试账本调用既有准入逻辑（事务回滚，无新任务）确认返回 403 `ENTITLEMENT_SUSPENDED`，不会回落成 Free。历史 30 秒用量保留，账面 remaining=1770 不表示 revoked 权益可用。四条 inbox 均 processed，pending/retry/review=0。
10. 收尾时浏览器操作能力恢复，主 Agent 再次只读核对 Notavue Test Billing 显示“禁用”、按钮为“启用”；控制台显示 4 次投递、4 次成功、0 失败、100%。无需重建或再次禁用。

## 联调修复

- Creem 对 `http://127.0.0.1:3002/billing/return` 明确返回 HTTP 400，消息为 URL invalid；相同商品改用 localhost 的未付款诊断 checkout 返回 200。经用户授权切换本机 Site URL 与精确认证白名单，未关闭 Origin 或身份校验。
- 原适配器将所有创建失败均保守记 uncertain，明确 400 也无法重试。现仅将 `POST /checkouts` 的 HTTP 400 定义为确定拒绝并落 failed，保留同 key 幂等结果，新 key 才可再试；网络/超时、其它状态和无效成功响应仍 uncertain，绝不自动重发 POST。错误正文不进入公开错误。
- 真实 POST 创建响应省略可选 request_id，后续 GET 却返回正确的已保存 request_id。现允许同步创建响应缺失该属性，若存在必须严格匹配；显式 null/空串/对象/数组/其它值拒绝。后续 GET 与签名绑定仍必须核对 request_id，未放宽跨用户或环境校验。
- 初次原始状态码未持久留存的本地 uncertain 意图，经用户明确授权人工结束为 failed/`MANUAL_TEST_ABANDONED`，原记录及独立审计文件保留。没有删除记录、替它伪造 provider_id，或据此授额。两次诊断请求均未付款，其中 127 请求被 400 拒绝，localhost 请求只创建未付 pending 会话。
- 新增 test-only 回调 listener，仅注册现有 `POST /webhooks/creem` handler，精确路由、HMAC、大小限制、持久 inbox 均复用；不公开账户、任务、checkout、docs。私密配置显式读取，忽略进程污染，启动前验证 inbox 迁移。

## 验证与独立审查

在 `songdance/api` 实际执行：

```sh
.venv/bin/pytest tests/test_creem_client.py tests/test_creem_failures.py tests/test_creem_billing.py tests/test_billing_hook_listener.py tests/test_billing_worker.py tests/test_billing_recovery.py tests/test_billing_ui_contract.py tests/test_creem_migrations.py tests/test_billing_cancellation_migrations.py -q --tb=short
SONGDANCE_TEST_REAL_AUTH_SERVICES=1 .venv/bin/pytest tests/test_creem_real_services.py -q --tb=short
.venv/bin/ruff check app/billing_hook.py scripts/run_billing_hook.py tests/test_billing_hook_listener.py app/services/creem_client.py app/services/billing.py tests/test_creem_client.py tests/test_creem_failures.py
```

结果：218 项定向测试通过，6 项独立临时 PostgreSQL 测试通过，Ruff 通过；仅有两条既有依赖弃用警告。测试不用真实商户/当前测试账本，真实服务证据由上述浏览器和只读查询取得，不混为一类。

[Listener 独立审查](2026-10-14-creem-listener-review.md)未发现可行动问题，35 项隔离测试通过；[Checkout 初审](2026-10-14-creem-checkout-review.md)发现显式 null 误接受的 P2，已修复并由[复审](2026-10-14-creem-checkout-rereview.md)确认关闭，134 项独立隔离测试通过。不同轮次存在重叠，不合并为新用例总数。

本轮没有修改 Web 源码，未重复运行上一批全量 Web 构建；已执行 `NEXT_PUBLIC_AUTH_ENABLED=false SONGDANCE_AUTH_ENABLED=false pnpm exec next typegen` 恢复默认生成类型引用。MIDI/MusicXML 解析脚本、`pdfinfo` 与 `pdftoppm` 均实际执行；Poppler 报字体缓存目录警告但退出 0、首页图像生成并已查看。

## 收尾与边界

- 临时 Tunnel 与 3002 Web、8002 API、8025 listener、Billing/Dispatch/RQ Worker 已停止；独立 PostgreSQL 58776、Redis 58777 已核对本任务 PID/Redis run_id 后关闭。`lsof` 复查上述端口及 8027 均无监听。未终止其它服务。
- Test key 与已禁用 webhook 配置保留；`.env.commercial-test.local` 0600、Git ignored，全部功能开关 false。隔离业务账本、审计和测试文件保留，未回滚迁移或清空历史。浏览器自动化会话已 reset，临时内存状态已清理。
- 最终 `git diff --check` 退出 0；9 份相关文档的 29 个本地链接均存在，改动文件的凭据模式检查未命中。
- 真实商业化证据只涵盖一笔 Test 周期与一个约 30 秒任务。未验证第二用户/第二付款周期、失败卡、部分退款/争议、商户历史扫描与漏通知恢复、active 订阅全额退款自动取消、真实退款续费竞态、账户删除整链或生产 HTTPS Cookie。
- 没有直接从 API 重放旧 JWT；本轮退款后的最终浏览器页面/退出因审批服务故障未完成。此前 Google/OTP 退出撤销证据不扩大成该次 UI 验证。
- 下载成功和音符可解析不代表听感/专业记谱门槛通过；实际谱面仍需人工校对，既有固定集、人评、容量/成本、法律政策、生产品牌/部署与 Phase 39 门槛继续保留。完整 BA-07–10/14、Phase 38 不整体勾选。
- 本轮变更未提交或推送，未部署或启用正式收费。

下一步补齐剩余 BA 测试矩阵及真实对账/active 退款取消分支，再进入生产配置、政策、容量和音乐质量验收。已完成的基础登录与本条商业闭环不重做。

官方原文核对经 agent-reach 网页读取路径，Jina 超时后直接读官方 Markdown：

- https://docs.creem.io/getting-started/test-mode.md
- https://docs.creem.io/api-reference/endpoint/create-checkout.md
- https://docs.creem.io/api-reference/endpoint/get-checkout.md

原文与脱敏检查暂存 `/tmp/notavue-creem-*`；持久账本与最终状态在受忽略测试目录。没有将密钥、会话 token、完整支付返回签名或 Portal 链接写入本记录。
