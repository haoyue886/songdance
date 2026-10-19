# 2026-10-19 双真实身份账单与 Portal 隔离

双真实身份的限定账单/Portal隔离已通过：Google返回自己的原已退款账单及Portal，邮箱仅获自身Free摘要且Portal409；归属注入均未越权。本轮另发现账单错误响应缺少禁止缓存头，已修复并复验，实际结果见下文。用户已现场授权最多1封OTP至hello@notavue.io、最多1次原已退款客户的Test Portal链接生成，以及临时签名邮件入口；无新付款或订阅变更。BA-11尚不整体签收。

## 数据与运行边界

- 复用已停止的隔离PostgreSQL集群，新建 `notavue_billing_isolation_20261019`，以第一份真实付款账本为模板复制；原user、issuer/subject、revoked付费期及30秒消费保留。复制存储到本轮独立目录，历史过期任务不作为本次权限夹具。
- 从上一轮双身份SQLite只读获取现存Google和邮箱issuer/subject，精确核对Google身份与付款库一致后，向新副本加入邮箱user/identity；没有按付款邮箱认领账单，也没有直接修改原4份PostgreSQL库或上一轮SQLite。新副本中Google有原客户绑定，邮箱无客户/checkout/订阅/付费期绑定。
- 准备前保存原4库全表摘要；模板复制后摘要一致。新私密配置 `.env.billing-isolation-test.local`、`.env.billing-isolation-mail-test.local` 均0600、Git ignored、默认flags false。仅API进程临时启用auth/usage/paid/reliable/Creem Test；生产认证verifier、session reader及业务路由保持原样。
- 独立Web/API/Redis监听本机3002/8002/58779，队列/配额/存储/临时目录独立。没有启动模型、Dispatcher、Billing或删除循环。Web只接收所需认证配置，不接收业务DB或Creem密钥，OAuth开发日志丢弃。
- 供应商适配器包装只允许GET和一次 `POST /customers/billing`，该POST必须使用原Google绑定客户ID，传输前持久记录一次性栅栏；其余付款/订阅写请求在网络前拒绝，未知结果不重复POST。包装不替换身份、账单查询或Portal归属逻辑。

## 已执行核验

在API目录运行 `.venv/bin/pytest tests/test_creem_billing.py tests/test_billing_ui_contract.py -q --tb=short`：25项通过（1.60秒），2条既有依赖弃用警告；这些为离线供应商回归，不算真实身份验收。临时Python准备/运行入口编译通过。Node预加载最初猜测的Next compiled/undici路径不存在，改用当前锁定且已安装的undici6.28.0，无新增依赖；模块检查通过。

使用原Test凭据真实GET原checkout、subscription、transaction：request_id/customer/product/订阅绑定一致，checkout completed、subscription canceled、transaction refunded，Test模式。仅3次GET，没有付款、退款或订阅修改。

原 `/billing/me` 与Portal/checkout路由的权限以已验证user为准：查询参数不用于切换owner，写body为extra=forbid。测试页只调用现有BFF与API，用当前真实会话，token和Portal链接仅在浏览器内存；输出身份标签、状态码及请求编号，无JWT/Cookie/Portal capability持久化。public测试页是临时本机验收工具，非产品UI，结束移除，私密源留档。

### Google侧

真实Google→Supabase PKCE登录回到账户页，显示原30秒消费及退款/审查暂停提示。临时测试页确认：

1. 自有 `/billing/me` 200，owner_id为当前Google业务user，plan=pro/state=revoked/used30/remaining1770、subscription canceled、portal_available=true；不把剩余展示数当作可用付费权益。
2. 同接口带邮箱user_id及原Google客户customer_id的伪造query，仍200且完整JSON与自有摘要相同，没有切换owner。
3. Portal body指定另一user/customer返回422；checkout附合法幂等key但body指定另一user/customer同样422，没有进入供应商。
4. 空body的合法Portal调用200，真实供应商恰一次POST且客户ID匹配原绑定；返回HTTPS Creem地址，通过原URL校验。链接仅在内存核对，未打开Portal操作订阅、未输出或保存链接。

这5个API请求有 `billing-google-*` 唯一编号，API状态日志和供应商审计对应。成功摘要与Portal响应private/no-store由实际浏览器观察；初始错误响应缺头的问题另记，未将全部初始响应误标为禁止缓存。

## 邮件接入与后续

用户批准后恢复独立mail副本、8024 listener和Quick Tunnel，仅两条签名邮件路由；真实HTTPS无签名POST分别401，`/me`404。原Supabase Send Email Hook保留secret，更新本轮临时地址并显示ENABLED。Resend事件回调不启用，2/h不改。

Google从产品页退出后，发送本轮唯一OTP，Resend接受；用户在本站输入验证码并确认“已登录”，账户页实际显示hello@notavue.io、Free剩余1次、无管理账单入口。随后已将Hook保存并复核DISABLED，按PID关闭Tunnel/listener，Web/API继续受测；没有使用旧的“剩余1封”授权或额外重发。

### 邮箱侧

邮箱真实会话在相同检查页确认 `/billing/me` 200且owner_id为本user，plan=free/state=active/used0/remaining1/portal_available=false/subscription_status=null。携带Google user_id/customer_id的query返回完整JSON仍等于自有摘要，不泄露对方checkout key、订阅或用量。

伪造user/customer的Portal及checkout body均422；空body合法Portal返回409/BILLING_CUSTOMER_NOT_READY，并未进入供应商。Google与邮箱各5个请求，共10项隔离检查通过。供应商日志仍恰3个准备GET、1次原Google客户Portal POST；没有第二次POST、付款或取消调用。

## 现场发现与修复

第一次邮箱Portal409的真实页面结果显示 `private_no_store=false`。复现确认FastAPI的HTTPException替换了路由注入的Response，导致私有账单错误响应没有Cache-Control。6条新增回归在修复前全部失败，覆盖/me401、Portal/checkout401、无客户Portal409和归属body422；这不是授权绕过，状态与数据隔离仍正确。

按已有私有响应不缓存要求，局部修改 `app/observability.py`，将 `/billing/me`、`/billing/checkout`、`/billing/portal` 加入既有最终响应头处理；成功和业务错误统一 `private, no-store`。公开 `/billing/config` 保持原`no-store`，没有扩大为所有billing或webhook路由。新增回归在 `tests/test_billing_ui_contract.py`。

实际执行 `pytest tests/test_creem_billing.py tests/test_billing_ui_contract.py tests/test_auth_ownership.py -q --tb=short`：45项通过（4.20秒），Ruff与compile通过。最初命令引用不存在的 `test_observability.py`，pytest退出4未执行，不计作产品失败或通过；随后使用上述实际存在的相关范围。早先25项与45项重叠，不累加。

重启仅本任务API加载修复，保留Portal一次性栅栏及登录会话；测试页追加cachefix请求编号，并强制断言每个响应缓存头。邮箱摘要、query注入、两个422及Portal409共5项实测复验通过，不重做Google的供应商POST。初始10项与修复后5项共15个带编号请求保留；完整账本摘要断言再次执行，原四库和8财务表保持一致。

完整BA-11中的两个不同付费客户Portal互访、并发认领、同邮箱不同未验证身份等仍未由本轮覆盖；这次使用一个真实客户绑定与一个无绑定账户。没有打开Portal内部页面或操作订阅，不将链接生成等同Portal全部功能验收。

临时入口 `/tmp/notavue-billing-isolation-20261019.py`、`/tmp/notavue_billing_runtime_20261019.py`、`/tmp/notavue-stop-billing-isolation-20261019.py`，审计保存于受忽略的 `.data/notavue-billing-isolation-20261019`。本轮生产改动限定为私有账单错误响应缓存头与相应回归；未提交、推送或部署。

## 独立审查与实际证据

fresh `code-reviewer` 在本次账单隔离与缓存修复范围内未发现可行动问题。审查了三个私有账单接口与缓存中间件、真实身份归属路径及body拒绝；核对15个编号请求及3GET/1Portal POST审计，并独立执行45项相关回归、Ruff通过（2条既有依赖警告）。新6项回归修前失败、修后通过，未把早先25项重复计为新增用例。

审查者只读确认两份SQLite来源摘要未变、配置0600/落盘开关false。没有直接完成当前四库及财务表的独立PostgreSQL重验，相关事实来自主Agent实际运行的 `/tmp/notavue-billing-final-check-20261019.py`：原4库全表摘要相同，原SQLite来源摘要相同，目标与源第一库的8张财务表逐表完整内容摘要完全相同；邮箱在accounts/checkout/subscription/paid/usage/ledger均无绑定，两个业务身份仍独立active，删除申请0。Google的revoked/used30保持，不按邮箱相同错误合并。

审查者未重新操作真实登录、供应商控制台或Portal内部页面。其端口观察不作为最终停服依据，主Agent按本轮PID/run_id执行收尾并提权只读核对端口。未把审查者未执行的供应商或数据库验证写为独立通过。

主Agent最后断言共15个编号请求、3GET和1Portal POST、1封新delivery，原4库/8财务表及SQLite来源全部不变。Portal生成栅栏仍保留，不再次生成或保存敏感链接。本轮唯一生产改动是错误响应缓存策略及6条回归，前批dirty改动保持原样；未提交、推送或部署。

## 环境收尾

- Google会话切邮箱前已退出；最后邮箱会话也已从产品按钮退出，实际页面回到 `/zh/login`。按钮首次位于可视区域外，滚入视区后才产生实际退出，没有把未响应点击标为成功。
- 临时public验收页已比对私密审计源哈希后删除；源码和脱敏证据保留。Hook先保存并实际复核DISABLED，再关闭Tunnel/listener；Resend事件回调没有恢复，邮件限额未修改。本轮1封新授权已用完。
- 执行 `/tmp/notavue-stop-billing-isolation-20261019.py`：按本轮PID/命令关闭Web4进程、API1进程，Redis按PID/run_id、PG按postmaster.pid核对后停止。3002/8002/8024/58776/58779连接断言均关闭，原资源清单`stopped=true`。原4库及新副本共5份数据库、存储和审计均保留。
- Web执行 `NEXT_PUBLIC_AUTH_ENABLED=false SONGDANCE_AUTH_ENABLED=false pnpm exec next typegen`退出0，生成类型引用恢复默认；新配置0600、Git ignored、落盘开关false。本轮没有新增凭据、白名单、付款、部署或系统代理设置修改。
- 最终 `git diff --check`通过，3份相关文档32个本地链接有效，26份待交付文本未命中10份实际私密配置的凭据值；10份配置均0600、默认开关false。public临时页不存在、Hook关闭记录存在、原资源清单stopped=true；提权只读lsof确认3002/8002/8024/58776/58779均无监听。结果另存`final-files-check.json`。
- 完整BA-11及生产发布门槛继续未勾选；本轮改动尚未提交、推送或部署。
