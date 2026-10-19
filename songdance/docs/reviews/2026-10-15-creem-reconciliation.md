# 2026-10-15 Creem Test 对账与 active 退款验收

**已补真实商户历史对账、漏付款/退款通知恢复、active 订阅退款后自动停止续费、退款后账户页面与退出验证。** 本轮完成已授权范围内的第二笔模拟付款与全额退款，未处理真实资金。生产源码本轮未新增改动，使用上一批已审查的原有对账和取消流程；前批代码与本记录尚未提交。

## 环境与授权

- 复用 moonAI 商店的 Creem Test key、Notavue Pro Test 商品、原 Supabase Test Google 登录及最小权限会话读取连接，没有新建凭据或扩权。
- 原隔离数据库保留第一笔 10 月 14 日退款和 30 秒用量；在同一隔离 PostgreSQL 测试集群另建数据库 `notavue_creem_active_refund_20261015`，使用独立队列/存储命名空间。它是第二份验收账本，不代表同一业务环境已支持退款后立即重复购买，未清空或绕过原账本保护。
- 第二笔商品 990 分、德国测试税额 188 分，模拟实付与全额退款均 1178 分。用户在最终提交前现场确认了第二笔总额及付款/数据处理条款。两次成功模拟付款的原授权额度已用完，没有第三笔。
- Notavue Test Billing 全程保持禁用，本轮没有建立 Tunnel 或公开新入口，专门验证缺少 webhook 时通过真实 API 对账恢复。

## 原退款账本：重复和历史扫描

1. 恢复原集群后，真实商户历史第一次两轮扫描均 pages=1、scanned=1、scan_complete=true、failed=0、scan_failed=0；第一轮为退款交易创建一条内部核验，第二轮 queued=0。原一份权益继续 revoked，已用 30 秒、预占 0、历史额度未改变。
2. 用本地合成 event ID，通过真实签名 handler 对实际测试账本提交同一 paid 通知三次，返回 200/200/200，仅新增 inbox 一行。原签名配篡改正文返回 400。随后按真实供应商 GET 处理，事件 processed，权益仍 revoked，用量不变。这是本地合成重放测试，未将它当作 Creem 真实重投。
3. 真实浏览器账户显示历史 Pro 月付、1770 秒余额/30 秒已用，同时提示“账单状态需要人工审查，新任务和新购买已暂停”。历史 remaining 值不表示 revoked 权益可消费。实际退出后返回 `/zh/login`。

## 第二笔：缺少付款通知时恢复

| 阶段 | 真实供应商 | 本地账本 |
|---|---|---|
| 付款前 | 待支付 checkout | 1 个 checkout，inbox=0，paid_periods=0 |
| Test 卡付款完成、对账前 | checkout=completed、mode=test | checkout=pending，inbox=0，paid_periods=0；返回页继续确认中 |
| 第一轮对账 | 商品/checkout/订阅/交易详情与历史查询 | 绑定本次 checkout，核实交易并授予一份 1800 秒权益 |
| 第二轮对账 | 商户历史 scanned=2、scan_complete=true | queued=0、processed=0，额度未重复授予 |

两轮 paid 阶段报告分别为 completed=2/3、failed=0、scan_failed=0；真实交易 GET 为 amount=990、amount_paid=1178、tax_amount=188、status=paid，订阅 active。真实账户页面显示 Pro 月付、剩余 1800 秒、已用/预占 0。

商户历史包含第一笔已退款交易，但它不属于第二份账本，故保留一条 `RECONCILIATION_UNBOUND`/review，未按相同 hello@notavue.io 认领。unbound=1 是正确隔离结果，不是扫描失败；没有为清零删掉这条记录。此测试验证跨账本绑定边界，不能替代完整跨用户权限矩阵。

## 第二笔：active 退款自动取消

1. 仅对 10 月 15 日第二笔 Test 付款提交全额退款 11.78 美元，原因“客户请求”。退款表单的“取消活跃订阅”保持未勾选，没有在 Portal 或控制台提前取消。
2. 对账前实际 GET：transaction=refunded、amount_paid=1178、refunded_amount=1178；subscription 仍 active。本地 paid 仍 active、取消意图数 0，证明自动取消尚未发生。
3. 调用现有 `reconcile_known`、`process_pending`、`process_cancellations`。后台先撤销权益并保存取消意图，再查询原绑定/退款/最新交易，向该 Test 订阅发送一次 `POST /subscriptions/{id}/cancel`（原适配器显式 `mode=immediate`），随后 GET 确认 canceled，取消意图 verified、attempts=1。
4. 观察类仅记录实际 `CreemClient._request` 的方法/路径类别并委托原始网络实现，未替换供应商响应或取消实现。本阶段记录取消 POST=1；重复一整轮对账后 queued=0、processed=0、cancellations=0，没有第二次取消。
5. 最终第二笔交易 status=refunded、订阅 canceled、唯一权益 revoked。商户页面刷新后实际显示“已退款 $11.78”。最终真实账户页提示新任务/购买暂停；退出后再次访问账户显示“登录已过期，请重新登录”。
6. 对两份实际账本分别调用原 `reserve_job`（诊断事务回滚，无新任务）：均返回 403 `ENTITLEMENT_SUSPENDED`。原账本 used=30，第二份 used=0；两者各自一份 revoked 权益和 verified 取消记录，没有回落成 Free 或恢复余额。

## 实际执行与证据

临时脚本均使用 `songdance/api/.venv/bin/python`；私密配置只在本机读取，不回显。关键入口为：

```text
/tmp/notavue-creem-reconcile-20261015.py
/tmp/notavue-creem-duplicate-20261015.py
/tmp/notavue-creem-active-phase-20261015.py paid
/tmp/notavue-creem-active-phase-20261015.py refunded
/tmp/notavue-creem-final-check-20261015.py
```

上述真实供应商检查通过；既有代码的 218 项定向回归、6 项临时 PostgreSQL 并发回归及独立审查证据沿用[上一批记录](2026-10-14-creem-test-integration.md)，本轮没有重跑或重新计数。未因文档补证而重复执行全量 Web/API 回归。

脱敏报告保存在受忽略目录：原账本的 `reconciliation-20261015.json`、`duplicate-20261015.json`；第二份账本的 `missed-paid-before-reconciliation.json`、`paid-result.json`、`refund-before-reconciliation.json`、`refunded-result.json`、`final-admission-results.json`。不提交填好密钥的 env、数据库文件、支付返回签名或 Portal URL。

## 收尾和剩余验收

- 本轮仅使用本机 3002 Web、8002 API 与原隔离 PostgreSQL/Redis；未启用回调 listener、RQ/Dispatcher 或账户删除 Worker。Web/API 已停止，集群与 Redis 按资源清单身份核对后关闭，两份数据库及审计记录保留。
- 两份私密配置均 0600、Git ignored、全部默认功能开关 false。Google provider 和 Test key 保留；webhook 保持禁用。已执行 `NEXT_PUBLIC_AUTH_ENABLED=false SONGDANCE_AUTH_ENABLED=false pnpm exec next typegen`，退出0、生成引用恢复默认路径；浏览器自动化会话已 reset。
- 最终 `git diff --check` 通过；5份相关文档的25个本地链接均存在。改动文件未命中本次实际私密配置中的 key/secret/DSN/bridge 值。`lsof` 检查 3002/8002/8025/8027/58776/58777 均无监听（退出1、无输出），资源清单 stopped=true。
- 未完成真正跨付款周期续费、失败卡、部分退款/争议、供应商历史多页/并发变更、退款与续费边界竞态、不同真实用户的权限矩阵、账户删除供应商闭环。单页两笔历史不能替代多页/多周期验收；完整 BA-07–10/14/15 仍不整体勾选。
- 当前 UI 对 revoked/frozen 使用通用账单审查提示，同时展示历史套餐与余额；新任务被拒绝的行为已实测，不将界面历史余额当作有效权益。
- 生产 HTTPS Cookie、商户审核、政策、容量/成本、专业音乐质量与长音频门槛继续保留。本轮不部署、不启用正式收费。

下一步按剩余 BA 矩阵补失败卡、跨用户/账户删除与部分退款审查；新增模拟付款前需重新确定测试额度。已经完成的基础付款/取消、对账恢复和 active 全额退款自动取消不重做。

同日后续已补无账单账户删除、真实Google重新登录墓碑和真实Creem未知订阅阻止清理，见 [账户删除记录](2026-10-15-account-deletion-acceptance.md)。付费完整停费删除与真实双用户互访等仍保留，不覆盖上文历史分支边界。
