# 2026-10-19 并发认领补验准备

本轮已完成**真实双浏览器三轮并发认领限定验收**：24个编号请求、锁前同步事件与PostgreSQL最终归属检查通过，独立复核通过。此前Cookie/邮件/审批故障与60秒同步器失败均保留在本文历史记录中。完整BA-11不勾选；本批当前结论见下节，收尾状态须以最终记录为准。

## 最终真实验收结果

审批恢复后先实测3002/8002/8024/58780/62964五端口均关闭，再保留历史记录恢复本轮隔离PG/Redis/API/Web。主Agent与fresh独立reviewer分别复跑180秒runtime的隔离PG/FakeVerifier preflight：各1 passed；发送门闩mock独立4 passed，未发现可行动问题。

现场发现Chrome普通与无痕窗口仍保留原真实Google/邮箱会话；经原BFF、SupabaseVerifier及只读session reader重新核对，映射到两份不同业务owner。未假定此前用户收尾意味着远端会话必然已撤销，本次以实际校验为准。两次已有会话refresh经auth bridge均200。没有发送新邮件、启用Hook/Tunnel、调用Portal或新增付款；新批次发送marker未创建。

两边点击本机验收页后，每个夹具均有两次不同身份的 `before_job_lock` 早于响应，三轮依次：

| 轮次 | Google初次 | 邮箱初次 | 唯一持久owner |
| --- | --- | --- | --- |
| 1 | 404 | 200 | 邮箱 |
| 2 | 200 | 404 | Google |
| 3 | 404 | 200 | 邮箱 |

每身份每轮另查读取、重复认领和匿名旧游客凭证，共24个唯一编号请求全部符合预期：胜者读取/重放200、败者读取/重放404、匿名旧凭证404。两浏览器页面均complete/passed。数据库owner匹配胜者，guest_secret_hash清空，queued/attempt1及3个源文件摘要保持。两个来源SQLite摘要未变，billing_accounts为0。

主Agent执行 `/tmp/notavue-verify-real-claim-race-20261019.py`，脱敏结果保存 `real-claim-final-assertions.json`；独立reviewer实际只读重跑全部业务断言通过，未重写通过标记。验证脚本初版错误假定认证bridge不存在，因真实会话正常refresh而失败；改为核对既有bridge均200，24项业务、锁事件和持久归属标准未改。旧60秒超时日志未删除。

**覆盖边界**：单API进程、两个真实已验证身份、三个显式1秒静音游客夹具；未执行模型转谱或真实上传。双付费客户、多API实例、认领与删除竞争、同邮箱未验证身份仍未覆盖，完整BA-11继续待验。生产认证/claim逻辑未修改，未提交/推送/部署。

**最终收尾已完成**：原UI分别点击邮箱/Google退出并确认返回登录页，无痕窗口关闭。按PID/命令归属停服脚本执行成功，Web/API/Redis/PG停止；五个端口3002/8002/8024/58780/62964独立探测均关闭，PG pid不存在，public页移除。Hook保持关闭（本批未开启），没有启动mail/Tunnel，数据保留。`real-claim-shutdown.json` 和 `shutdown.json` 为最新证据；此前“未收尾/审批403/未通过”段落均为历史，不代表本批当前状态。Next默认route typegen与git diff空白检查通过。

## 改动

`api/tests/test_auth_real_services.py::test_real_postgres_claim_race_has_one_owner` 原先只用线程池检查两请求200/404，未要求二者同时到达数据库任务锁。本轮在原场景中追加：

- 三轮新的匿名任务，交替alice/bob提交顺序；在两个 `SELECT transcription_jobs...FOR UPDATE` 执行前以Barrier(2)同步，15秒有界等待，断言恰两个请求到达同步点。
- 每轮胜者唯一、败者404；持久owner等于胜者业务ID、guest_secret_hash已清空，queued/attempt1/source asset及源文件均保留。
- 胜者正常读取/重复认领200，败者读取/携原凭证再抢认404，旧匿名凭证读取404；事件监听在finally移除，原fixture保留数据库进程清理。

认证仍用已有FakeVerifier，数据库为fixture新建的PostgreSQL；该测试只证明本地事务/锁/路由行为，不能冒称Google/Supabase真实双会话并发。生产认领代码、认证门禁和限额未修改。

## 已执行

在API目录执行：

```sh
.venv/bin/ruff check tests/test_auth_real_services.py
.venv/bin/python -m compileall -q tests/test_auth_real_services.py
.venv/bin/pytest tests/test_auth_ownership.py tests/test_auth_coordination.py -q --tb=short
SONGDANCE_TEST_REAL_AUTH_SERVICES=1 .venv/bin/pytest tests/test_auth_real_services.py -k claim_race -q --tb=short
```

Ruff、compile通过；已有相关回归18项通过（2.23秒），两条既有依赖弃用警告。首次Ruff发现新增闭包绑定和行长问题，已修正；当次命令在静态检查退出，未执行其后的PostgreSQL测试。

PG命令首次需要允许fixture绑定随机回环端口时，自动审批服务返回403，原因是其API密钥超过配置额度，当次未执行。此后独立审查者通过正常自动审批运行成功；主 Agent 也按原命令通过正常审批复跑，结果 **1 passed, 3 deselected，2.36秒**，包含上述三轮竞争，两条既有依赖弃用警告。没有绕过审批；普通18项回归与这项PG测试分别计数。

上述测试批次未触发OTP/Portal/付款、未启动Supabase Hook/Tunnel/Web/API/Redis，没有新增凭据或修改系统代理。测试fixture的临时PG按原fixture清理。随后为真实验收准备新隔离集群，详情见下文；此前账单隔离已完成并停服，验收记录保持。

## 真实双会话验收准备

- 新建 `.data/notavue-claim-race-20261019/cluster`，单独随机回环端口，迁移至head；不启动历史付款集群。准备完成后已停止PG。
- 只读读取10/15双身份库的两份active用户及exact issuer/subject，导入新库；创建3个明确的1秒静音合成游客任务及源文件，无真实上传、转谱、付款或历史账单复制。
- 新建 `.env.claim-race-test.local` / `.env.claim-race-mail-test.local`，0600、被Git忽略、落盘功能开关全部false；邮箱仍限定hello@notavue.io。准备前后两来源SQLite摘要一致。
- 临时runtime保留原SupabaseVerifier、session reader及原claim路由，仅对3个夹具且指定初次request ID加锁前Barrier，60秒有界等待；重放请求不参与同步。事件只记请求编号/阶段/状态码，不记token/capability。
- 本机测试页按BFF session取短期token、先核对业务owner，再三轮调用原claim及读取/重复认领/旧游客凭证检查。真实执行计划使用Chrome与独立IAB会话；尚未登录，不把同cookie切换冒充双会话。
- 停服脚本按PID及命令归属核验后处理本轮进程，保留库及源文件、移除临时public页。供应商Hook禁用状态需另外核对，脚本不会宣称已禁用。

工具源码已保存在上述私密data目录的 `tools/`，不包含真实密钥或展开的夹具凭证；运行副本在 `/tmp/`。真实测试页尚未安装到public，邮件监听、Tunnel、Web、API、Redis均未启动。

以上为准备完成时的状态；随后按两次限定授权启动尝试，最终状态见下文。

执行结果：

```sh
songdance/api/.venv/bin/python /tmp/notavue-prepare-claim-race-20261019.py
PYTHONPATH=. .venv/bin/pytest /tmp/test_notavue_claim_runtime_preflight_20261019.py -q --tb=short
node --check /tmp/notavue-claim-race-harness-20261019.js
git diff --check
```

准备脚本第一次在沙箱绑定随机回环端口时被拒；随后按正常自动审批执行通过，创建2身份/3任务、来源摘要未变、PG停止。离线preflight **1 passed，4.78秒**：使用另一个一次性PG和FakeVerifier，验证ContextVar跨线程传播、三轮锁前两个到达事件先于响应、一200一404、唯一owner、旧凭证失效和重放。没有消费预留给真实浏览器的3任务，也不代表真实JWT验收。Python编译、JS语法检查、配置权限/开关/停服/页面未发布检查与diff空白检查通过。

## 真实尝试与阻塞

1. 用户授权临时邮件入口及最多1封OTP后，启动本轮新PG/Redis/API/Web。Chrome原Google身份真实登录通过；IAB仍匿名，确认两会话没有串用。
2. 临时邮件入口两条无签名POST均401，`/health`、`/me`、`/openapi.json`均404。Send Email Hook启用后，仅点击一次发送；邮件Hook200、审计accepted。用户在IAB完成邮箱登录，账户页与API `/me` 曾成功显示邮箱身份。
3. 导航至本机验收页后，IAB `access-token` 返回401；限定诊断仅输出 `SIGNED_OUT`，对应BFF未收到会话标记/认证Cookie。Chrome仍解析为google身份。尚不能确定IAB或应用何者导致，不据此修改生产认证代码。认领按钮没有执行。
4. Hook已禁用、第一条Tunnel与listener已停后，准备Chrome无痕窗口。用户补充授权最多1封OTP及同范围临时入口，保持2封/小时，不改系统代理。第二条入口仍通过同样401/404检查。
5. 仅点击一次补充发送，但监听收到两条相同原始payload、不同事件ID的回调；两条均一次供应商尝试后503，审计各为 `unknown / PROVIDER_OUTCOME_UNKNOWN`。两条消息因delivery tag不同，message digest不同。未手工重发、未把unknown改成rejected或accepted，也不能将两条审计记录等同两封已送达邮件。用户确认未收到，未进行无痕邮箱验证。
6. 只读、无密钥GET连通性探测：`https://api.resend.com/` 直连 `ConnectionError`，显式使用既有 `127.0.0.1:7897` 代理时200。`ResendClient` 使用 `trust_env=False` 且2秒请求/3秒总界限，所以runtime设置的HTTPS_PROXY不会供其使用。此探测解释当前直连故障，不能证明未知POST从未被供应商接收；未发送诊断邮件、未修改系统网络或生产保护。

临时工具另经fresh独立reviewer审查准备/runtime/页面/停服及原claim调用路径，未发现可行动问题；独立离线preflight **1 passed**。真实IAB会话保持、真实两浏览器竞争、实际供应商发送故障不因离线预检而通过。

## 最终收尾与续接边界

- Supabase Send Email Hook已在页面确认 **DISABLED**；Resend既有endpoint仍为Disabled，本轮未开启它。
- Chrome Google通过原“退出登录”返回登录页；本轮无痕窗口及IAB页已关闭。IAB本地已signed_out，不声称已撤销其无法再持有的远端Supabase会话。
- 停服脚本实际执行成功：本轮Tunnel、listener、Web/API、Redis和新PG全部停止，临时public页移除，数据保留。
- 最终只读断言：两个来源SQLite SHA256未变、3个游客owner仍NULL/guest hash保留/queued/attempt1、3源文件摘要一致、无billing binding、无claim事件/请求、落盘开关全false。证据存私密data目录 `final-assertions.json` 和 `shutdown.json`。
- 本轮两个发送授权均已尝试，保守视为无剩余额度；不自动重发未知结果。未调用Portal、新增付款、修改供应商限额或系统代理，未提交/推送/部署。

下一步先做无需发送邮件的直连/显式测试代理诊断与浏览器Cookie保持预检，确认测试传输路径后再申请必要的发送额度。真实竞争使用Chrome普通窗口与无痕窗口；预留任务过期时创建新的合成任务，不能放宽expires判断或复活已删除账户。此轮不能勾BA-11。

## 续接

### 最新中断状态：代理发送成功，自动审批故障阻断收尾

**最新收尾补记**：用户已手动执行持久停服脚本并确认退出两份Chrome测试会话。主Agent读取新 `shutdown.json`：Web/Redis停止，PG停止，mail/Tunnel already_stopped，API not_started（对应当前api-process marker不存在）。`resources.json.stopped=true`、postmaster.pid和public页均不存在，新claim事件文件也不存在。端口独立探测再次被自动审批403阻断，未执行，故不宣称五端口实测关闭。以下“可能仍运行/未退出”为用户收尾前历史状态；当前以本补记为准。真实并发仍未通过，无新增发信额度。

用户新增明确授权最多一次代理发送后，Hook200（1.28秒），持久一次marker已占用。用户在Chrome无痕完成邮箱登录；原生界面确认邮箱与普通Chrome Google分别有效，导航到验收页后两者identity均ready。Supabase Hook已在原生UI确认DISABLED，mail/Tunnel已核对PID并发送SIGTERM；没有再次发送授权余额。

首次60秒同步器尝试因原生窗口切换/审批延迟产生BrokenBarrierError，页面Failed to fetch。失败日志/事件存 `barrier60-failed-*`；失败后只读确认3任务仍未认领。仅将测试Barrier等待改为180秒并重启隔离API，生产锁/认证/限额未改，未将失败计通过；新一轮未点击开始、无新claim事件。

随后正常申请PG预检及浏览器只读操作均被自动审批服务403 UNKNOWN阻断，非安全拒绝且动作未执行。停服先在普通沙箱因ps权限不足失败，正常提权仍被同一403阻断，未绕过。**当前本机Web/API/Redis/新PG可能仍运行，不能沿用上文停服完成结论；Chrome两登录会话尚未退出。**临时public页已通过本地文件操作移除，Hook禁用与公网入口SIGTERM在故障前已完成。

最新证据 `interrupted-proxy-run.json`。用户需在项目根手动执行 `songdance/api/.venv/bin/python songdance/.data/notavue-claim-race-20261019/tools/stop-claim-race.py`，并在两个Chrome窗口退出登录，或先恢复自动审批服务后继续。不要重发验证码，不勾真实竞争验收；180秒调整后的独立PG预检未执行。

用户再次要求继续后，主Agent正常申请只读进程归属核对，自动审批仍403 UNKNOWN，命令未执行。已把相同停服脚本保存到上述私密持久路径、Python编译通过，复核public页和新claim事件文件均不存在。`resources.json` 中沿用旧批次的 `all_local_processes_stopped=true` 已纠正为null（未知），不冒称当前停服；本次记录 `approval-recheck.json`。未再开启Hook、发送验证码或操作数据库。

### 不发信的连接与Cookie预检（后续批次）

新测试专用 `LocalProxyResendClient` 显式注入 `http://127.0.0.1:7897`，每次生成新AsyncHTTPTransport；固定供应商地址、certifi TLS、零网络重试，复用生产ResendClient原2秒请求/3秒总界限及unknown语义。生产文件和系统代理未改。同httpx配置的无密钥GET对照：直连ConnectTimeout，显式代理200；这仅证实连通性，未发邮件或验证供应商接收。

按上批两条不同event ID回调的风险，新测试client在发前用0600/O_EXCL持久marker限制整个新增授权批次只能调用供应商一次。并发/不同ID/进程重启均共用marker；accepted或unknown都不复位，后续请求返回测试预算拒绝。不复用上批unknown记录，不自动补发。

执行 `PYTHONPATH=. .venv/bin/pytest /tmp/test_notavue_mail_transport_20261019.py tests/test_mail.py tests/test_mail_hook_listener.py -q --tb=short`：最终 **87 passed，12.98秒**（4新增传输/预算场景及83既有邮件检查），两条既有警告。初次命令误用了不存在的test_resend_client.py，0 tests，已纠正；不记为产品失败。Python编译通过。

无凭据本机Cookie探针只用固定合成值，未读取真实Cookie/token。Chrome普通、Chrome无痕和IAB均验证普通HttpOnly/SameSite=Lax Cookie与3800+900字节分块Cookie的设置、导航和刷新保持；无痕初始四项均false，确认不共享普通窗口Cookie；最终三者四项均false，测试Cookie已清理。IAB原真实会话丢失**未复现、未修复**，合成预检不能替代真实登录。

探针进程已按PID归属停止，IAB页已关闭；恢复本机隔离PG/Redis/API/Web供续接，邮件监听/Tunnel保持关闭、未发送新邮件。此前停服证据存 `before-proxy-run/`，当前证据为 `transport-cookie-preflight.json`，新增工具备份于私密 `tools/`。原三游客仍留作真实验收，过期门禁保留。

代理适配器初版与Cookie探针取得独立审查无可行动问题；新增一次预算的后续审查因派发正文未传达未取得有效结果，主Agent完成代码核对和并发/unknown回归，不能宣称该增量已独立审查。下一次真实发送需新限定授权。

本地三轮竞争与准备已完成，真实供应商竞争按上文阻塞点续接。不能把交替提交顺序写成强制alice/bob各胜一次，也不能将锁前同步等同真实供应商并发通过。

本轮测试改动未提交、推送或部署。fresh 独立 `code-reviewer` 审查该测试及相关调用路径，未发现可行动问题；其独立PG运行 **1 passed**。真实浏览器/JWT、多API实例、认领与删除竞争仍未覆盖。
