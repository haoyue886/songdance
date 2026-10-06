# Creem Test 后端接入

2026-10-06：仅 Test 后端实现，默认关闭，拒绝 production/Live。没有真实商户凭据、测试卡付款或 Portal 取消实测；本地替身不替代供应商验收。

## 配置和运行

先完成 auth-setup.md 的身份配置，在隔离数据库运行 `alembic upgrade head`（009）。参考 `../infra/env.creem.example`，密钥仅放到未提交环境文件。配置认证、用量和付费用量，再启用 CREEM_ENABLED。Test 商品须为 USD 990 cents、every-month、无 trial/usage_prices；1,800 秒和 90 秒单次为当前 Test 快照，不代表 5/10 分钟已验收。

API 提供 `POST /billing/checkout`（空 JSON、已登录 Bearer、本站 Origin、8–128 位 Idempotency-Key）和 `POST /billing/portal`（空 JSON、同样身份/Origin）。服务端决定 product、customer、金额和回跳地址。`GET /billing/me` 包含 sync_state/checkout_status/subscription_status/portal_available。当前前端商业页未接入；success URL 可暂用本站 /account，回跳不授权。

在 Creem Test 控制台配置精确 webhook URL `/webhooks/creem`，密钥与 Test 环境配套。仅此 POST 路径豁免 Origin；仍执行原始 body HMAC、256 KiB 限额及环境校验。代理需保留原始 body，转发链继续遵循部署手册。200 只表示 inbox 已提交，不表示权益已授予。

运行独立进程 `python -m app.jobs.billing --loop` 每 15 秒处理 inbox；进程重启从持久队列恢复。失败按退避最多 8 次后转 review，告警日志不输出 body/密钥。经检查修正原因后使用 `python -m app.jobs.billing --once --replay-id LOCAL_INBOX_ID` 重放，保留累计 attempts。

每天由部署平台 scheduler 执行 `python -m app.jobs.billing --once --reconcile`。本代码未创建外部定时任务。该对账覆盖已知 checkout、订阅最近一笔及已有付款历史，尚不枚举供应商所有交易；漏掉多个历史周期仍需 Dashboard 对账，不能勾选完整 BA-10/16。

## 恢复与限制

- request_id 在官方合同只描述追踪用途，未承诺 POST 幂等。请求发出后超时/进程终止保留 creating/uncertain，不自动重复创建。已知 provider_id 可对账；没有 provider_id 时等待签名 checkout.completed 或人工按 request_id 在控制台核实，不删除意图强行重购。产品 GET 的明确失败标 failed，新 key 可安全再试。
- checkout.completed 只绑定账户/订阅；subscription.paid 查询权威 transaction，验证金额/币种、订阅/顾客和毫秒周期后授额。缺字段/冲突重试后 review，绝不按邮箱归属。Test/sandbox 可接收，prod/local 拒绝。
- canceled 保留已付周期；expired 可能仍重试扣款，不能视为停止扣费并另开订阅。退款只撤销关联交易；部分退款进入 review，不按比例删分钟；争议阻止账号新任务。退款自动停止未来续费、争议恢复仍须人工核对，未实现完整关闭环。
- 009 有任意账务记录时拒绝降级删表。回退代码保留账本和既有权益；禁止直接删除付款/事件记录。生产尚未开放。

## 官方合同核验

2026-10-06 实际读取以下公开原文；网页代理超时后直接读取官方 Markdown。

- https://docs.creem.io/api-reference/endpoint/create-checkout.md
- https://docs.creem.io/api-reference/endpoint/get-checkout.md
- https://docs.creem.io/api-reference/endpoint/get-subscription.md
- https://docs.creem.io/api-reference/endpoint/get-transaction.md
- https://docs.creem.io/code/webhooks.md
- https://docs.creem.io/features/customer-portal.md
- https://docs.creem.io/getting-started/test-mode.md

API 固定 https://test-api.creem.io/v1，x-api-key；支付请求无重定向/自动 POST 重试，响应最多 1 MiB。签名 HMAC-SHA256(raw body)，eventType/id 防重放；订阅周期 ISO、transaction 样例为毫秒时间戳。退款样例旧值/环境 local 不作为放宽当前 API 枚举的依据。真实商户联调必须核实 Test 字段、金额税额口径和实际页面。
