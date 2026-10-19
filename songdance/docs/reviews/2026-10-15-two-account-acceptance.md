# 2026-10-15 双真实身份任务验收

**指定任务范围已完成：真实Google/邮箱身份的双向任务访问控制、下载、控制操作拒绝及游客认领/旧凭证失效，共30个带请求编号的接口检查通过。** 其中1个Google任务由真实页面提交，3个补充任务为显式数据库夹具；月用量/付款关闭，账单/Portal等完整BA-11继续待验。首次网络阻塞、429与最终审查/收尾分别保留在下文。

## 已准备

- 原auth-mail测试SQLite库中有两个不同的issuer/subject，分别来自既有邮箱和Google登录，两个业务用户均active、任务数0。只输出身份摘要，不导出JWT、刷新令牌或密码。
- 使用SQLite只读连接backup到 `.data/notavue-two-account-20261015/auth.sqlite3`，邮件历史同样复制到独立mail.sqlite3。原两份SQLite文件的SHA-256在复制前后相同；此前四份PostgreSQL业务验收库未启动或修改。
- `.env.two-account-test.local`、`.env.two-account-mail-test.local`均0600、Git ignored、默认功能开关false；独立存储、临时目录、Redis队列与配额命名空间。本机站点沿用已登记的localhost:3002，不新增Google用户、凭据或回跳白名单。
- 先验收两账户正常任务可见性及游客任务认领。收费功能关闭，账单与Portal隔离仍是未覆盖项；不能将功能关闭返回当作授权隔离通过。

## 已执行检查

在API目录执行：

```sh
.venv/bin/python -m scripts.run_mail_hook --env-file ../.env.two-account-mail-test.local --check
.venv/bin/pytest tests/test_auth_ownership.py -q --tb=short
```

配置格式、邮件必需字段和客服标记通过，MAIL_ENABLED仍false；供应商连接未验证。首次以文件路径运行脚本因Python模块路径报错，随后按既有文档改为`-m scripts.run_mail_hook`成功，未修改产品代码。

权限回归14项通过（2.39秒），两条既有依赖弃用警告。这些用例使用离线身份替身，不计作真实双身份验收。

另以本轮邮件配置在进程内启动既有listener、仅临时启用其开关检查路由：两个无签名POST均401，`/me`、`/jobs`、`/docs`、`/openapi.json`均404。没有发送邮件、启动公网隧道或修改供应商设置。脱敏结果见私密测试目录的`preparation.json`与`listener-preflight.json`。

## 实际接入与阻塞

既有邮件联调记录明确保留1封未使用的验证码授权，收件人仍仅hello@notavue.io。继续时复用现有Resend发送key和Supabase Hook secret，临时HTTPS仅指向两条签名邮件回调，完成后禁用Hook并停止隧道/listener；不提高2/h邮件限额。

用户现场确认“允许本轮临时恢复”后，已启动独立Redis（58778）、API（8002）、Web（3002）、仅邮件listener（8024）和Quick Tunnel。实际本机API/Web均200；公开HTTPS的两个无签名POST均401，`/me`404。Supabase Send Email Hook更新到本轮临时地址并实际显示ENABLED，保留原secret；Resend事件回调未启用，邮件限额未修改。

随后从真实本地登录页发起Google登录，Chrome在Supabase authorize页面显示`ERR_CONNECTION_RESET`。一次重载仍失败；从本站重新发起新流程后，最终进入Google authorize页面但显示`ERR_CONNECTION_TIMED_OUT`。查询参数均脱敏，没有导出JWT、Cookie或OAuth凭据。

同一Supabase项目的服务端 `/auth/v1/settings` 经既有本机代理查询返回200，google/email均enabled。因此当前只能定位为浏览器OAuth链路不通，不能据此断言Supabase整体故障或应用权限逻辑错误。只读系统代理/进程检查未给出足以确认根因的结果，没有修改系统或浏览器代理设置。

没有点击发送验证码、没有新增任务或认领。两份副本的逻辑数据仍与来源库一致，源文件SHA-256也保持不变；之前剩余1封授权仍未使用。真实双账户、认领、账单和Portal均未标通过。

## 收尾与续接

- Supabase Hook已保存并实际复核为DISABLED；先禁用再按本轮PID/命令关闭Tunnel、listener、Web/API，Redis按PID/run_id核对后关闭。自有3002/8002/8024/58778端口连接检查均关闭。
- 原四份PostgreSQL验收库未启动或修改。保留本轮两份SQLite副本、合成WAV、配置与审计；新私密文件0600、Git ignored、默认开关false。
- Web执行 `NEXT_PUBLIC_AUTH_ENABLED=false SONGDANCE_AUTH_ENABLED=false pnpm exec next typegen` 退出0，恢复默认类型引用。
- `lark-mail`流程的现有CLI状态检查不可用，未新增邮箱授权，也未读取或发送邮件；未将其当作本轮登录阻塞原因。
- 续接前先确认Chrome能够完成Google/Supabase正常登录跳转，再恢复同范围签名邮件入口并使用剩余1封邮件。当前临时URL在Tunnel停止后失效，不能沿用为可用回调。

准备入口 `/tmp/notavue-prepare-two-account.py`，运行入口 `/tmp/notavue_two_account.py`，定向停止入口 `/tmp/notavue-stop-two-account.py`。脱敏证据在私密测试目录的`runtime-ready.json`、`https-preflight.json`、`provider-state.json`、`shutdown.json`和`closeout.json`。

本轮未修改生产逻辑，未提交、推送或部署。

## 网络恢复后的真实双身份续接

只读检查发现系统HTTP/HTTPS/SOCKS代理关闭、TUN也关闭；Google/Supabase直连分别超时/重置，经既有7897代理均可收到正常响应。没有擅自修改网络设置。用户选择自行恢复后回复“已恢复”，Chrome实际打开Google账户页成功，本站Google→Supabase PKCE→账户页也随后通过。

复用既有隔离库重启Web/API/Redis（原进程清单归档于`first-run-process-markers`），保持收费、月用量、账户删除关闭。Google用户在真实上传页选择原30秒 `02-brahms-intermezzo.wav`，现场确认版权/隐私/条款后提交，任务归属Google身份、queued、attempt=1。未启动模型Worker，不据此评价音质。

此前同范围邮件授权延续到本轮：新的Quick Tunnel仅指向8024签名listener，实测无签名回调401、`/me`404；Send Email Hook更新并显示ENABLED。实际发出唯一剩余验证码，Resend接受；用户在本站输入验证码并回复“已登录”，页面显示hello@notavue.io。邮件授权剩余0，未额外发送或修改2/h限额。邮箱登录后已先将Hook保存并复核DISABLED，再按PID关闭Tunnel/listener，业务Web/API继续受测。

### 生产页面与接口矩阵

邮箱身份在原任务页面访问Google刚提交的任务，接口404，实际页面显示“任务不可用”，未展示源文件或删除入口。对应原Google身份之前可看queued任务；该任务不用于破坏性探测。

补充接口矩阵使用本机临时验收页，复用生产 `/api/auth/access-token` BFF会话、真实Supabase JWT验签与session reader、真实FastAPI路由；没有替换认证verifier、注入JWT或读取浏览器Cookie。access token仅在浏览器内存短时传递给API，不输出、持久化或发送至其他目标。临时页不作为产品UI验收，结束后从web/public移除，私密审计副本保留。

为安全探测重试/删除/认领等控制接口，创建两份5秒合成owned数据库夹具，分别归属现存Google和邮箱user，原用户上传任务保持。首次尝试通过真实匿名上传创建游客任务，被原 `client_active_job_limit=1` 拒绝429；没有放宽限额、重启API清限流或标为上传成功。随后游客任务也用显式数据库夹具，采用生产 `new_guest_secret` 生成能力凭证。三份夹具拥有正常source asset和WAV，状态queued/attempt1，24小时有效期；它们验证访问控制和认领，不能替代新的浏览器上传、派发或模型验收。准备前保存SQLite backup用于恢复。

邮箱矩阵已实际通过10个请求：自有任务查询、签名源链接和源字节200；Google合成任务查询、下载签名、retry、DELETE、claim、事件上报均404；原Google浏览器上传任务查询也404。每请求带唯一 `two-email-matrix-*` ID，与API状态日志对照。

邮箱认领已实际通过8个请求：游客无凭证404、有正确凭证200；登录邮箱但无凭证/错误凭证认领404；正确凭证认领200、本人重放200、本人查询200；旧游客凭证匿名重用404。数据库确认owner变为邮箱user、guest_secret_hash为空、attempt仍1。不是本机代码直接改owner；该变化由真实claim接口完成。记录在`matrix-email-result.json`与API日志。

Google矩阵也已通过12项：自有合成任务/源文件、原浏览器提交任务200；邮箱合成任务及其控制路由均404；已归邮箱账户的游客任务查询404，即使带原游客凭证再认领也404。真实测试页显示Google身份摘要与complete/passed=true，已查看实际渲染；邮箱/Google两个业务身份摘要不同。结合邮箱10项与认领8项，共30项。

`/tmp/notavue-two-account-final-check.py`实际只读查询与日志断言通过，核对30个request_id及状态、两用户active、两个不同issuer/subject及user映射、四任务queued/attempt1、source asset均存在、游客owner邮箱且旧hash清空。原两份SQLite源文件摘要未变，只有本轮mail副本新增1个delivery，授权余量0；未创建付款、删除申请或用量记录。结果保存为`completion-assertions.json`，未包含JWT或真实登录凭据。

### 验收边界

收费关闭，因此账单、Portal、跨付款周期、双身份同时认领竞争及同邮箱未验证身份不合并仍未在本次真实供应商验收，不整体勾选BA-11。正常产品认领按钮、完整双用户上传/模型/导出不是本次测试页所覆盖；不得把夹具认领等同完整UI闭环。

临时夹具脚本 `/tmp/notavue-seed-two-account-fixtures.py`，测试页源 `/tmp/notavue-two-account-harness.html`；受测时的展开页在`web/public/__notavue-two-account-20261015.html`，只允许localhost:3002，包含专用合成游客任务能力凭证、无真实登录凭据。已比对私密审计副本哈希后从public移除。

## 独立审查

fresh `code-reviewer` 在本次任务权限与游客认领范围内未发现可行动问题。独立追踪生产授权/认领和身份映射，核对30个唯一请求编号与响应、两identity映射不同user、guest归邮箱且旧hash清空、四任务queued/attempt1、原两份SQLite源库摘要未变及SQLite完整性。

审查者独立执行 `tests/test_auth_ownership.py tests/test_auth_coordination.py`，18项通过，2条既有依赖弃用警告；本轮早先主Agent14项与其重叠，不合计覆盖数。没有新增生产逻辑或重跑无关全量构建。

审查者未亲自执行真实登录、供应商控制台、产品UI或完整双用户上传/模型/导出。审查中关于“端口均关闭”的观察未采用：主Agent提权只读检查当时确认Web/API/Redis仍在运行，最后按PID/run_id执行停止并再次确认，关闭证据以实际收尾为准。审查者未修改仓库、提交或推送。

## 本批最终收尾

- 最后一轮Google会话通过产品退出按钮退出，实际页面回到 `/zh/login`；邮箱会话也已在切换Google前退出。没有为测试导出JWT、刷新令牌或Cookie。
- 临时public测试页已删除，私密审计源保留。先前已关闭的Tunnel/listener维持停止，最终执行 `/tmp/notavue-stop-two-account.py` 关闭自有Web3进程、API1进程和Redis（PID/run_id匹配），3002/8002/8024/58778连接检查均关闭。没有启动模型、Dispatcher或清理循环。
- Supabase Hook已实际复核DISABLED；Resend事件回调始终未恢复，邮件限额未修改。唯一剩余授权邮件已使用，后续不可再按“剩余1封”重发。新配置落盘flags均false、0600、Git ignored。
- 两份原SQLite源库摘要未变，四份PostgreSQL历史验收库未启动；本轮四任务、源文件和必要审计保留于隔离目录，既有Google/邮箱身份仍active。本轮没有账户删除或支付。
- Web执行 `NEXT_PUBLIC_AUTH_ENABLED=false SONGDANCE_AUTH_ENABLED=false pnpm exec next typegen` 退出0，恢复默认 `.next/types/routes.d.ts` 引用；原网络配置由用户自行恢复，本轮没有改动系统代理设置。
- 最终重跑只读 `/tmp/notavue-two-account-final-check.py` 断言与4个临时Python入口编译均成功；`git diff --check`通过。3份相关文档30个本地链接有效，23份待交付文本未命中8份实际私密配置的凭据值或本轮guest能力凭证；8配置均0600、默认flags false。提权只读`lsof`确认3002/8002/8024/58778均无监听；public临时页不存在，私密审计副本保留。
- 需求BA-11整体继续未勾选，下一步补真实双身份账单/Portal及其余未验条款。未提交、推送或部署。
