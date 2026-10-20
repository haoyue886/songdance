# 商业化 Test 配置与验收准备

2026-10-07：认证、Free/Pro 账本、可靠派发、游客体验、Creem Test 和账户删除已有本地实现，开关默认关闭。本清单用于准备隔离测试项目，不创建供应商账户、不部署、不打开正式收费，也不证明真实 Google、SMTP 或商户已经可用。

2026-10-14 更新：真实 Google/OTP 基础闭环及 Creem Test 一笔付款→授额→真实转谱/导出→取消→全额模拟退款已取得证据。Test webhook 和本机服务已关闭，完整 BA、专业音乐质量和生产验收继续待补；最新事实见第 9/10 节，不以第 4–8 节历史准备状态判断当前进度。

2026-10-15 更新：第 11 节已补真实单页商户历史、付款/退款漏通知恢复、active 全额退款自动取消及退款后 UI/退出；本轮服务已关闭。

详细接入沿用 [认证设置](auth-setup.md)、[Creem Test 设置](creem-test-setup.md)、[部署说明](deployment.md) 和 [恢复手册](runbook.md)。范围与验收以 [开发计划 Phase 38/39](../../DEV-PLAN.md) 和 [商业化子规范](../../Billing-Auth-Spec.md) 为准。

## 1. 先完成本地验证

在已有锁定依赖的环境运行，只使用隔离数据库、存储和队列：

```sh
# songdance/api/
.venv/bin/pytest tests/test_commercial_config.py tests/test_auth_config_preflight.py tests/test_settings.py -q
.venv/bin/ruff check app/services/commercial_config.py scripts/check_commercial_config.py tests/test_commercial_config.py

# songdance/web/
pnpm test:commercial:e2e
```

浏览器走实际 Next.js BFF、FastAPI、迁移后的 PostgreSQL、Redis、RQ 和 Basic Pitch，仅外部身份与支付协议由本地服务提供。A4/静音合成音频验证代码路径、导出与失败恢复；不登录真实 Google、不发送邮件、不购买真实商品，也不能替代真实音乐固定集、专业谱面复评或供应商验收。

运行需要 Python 3.11 API 虚拟环境、锁定 Web 依赖、本机 `initdb`/`pg_ctl`/`redis-server`、FFmpeg 和 Chrome（非 macOS 可用 `PLAYWRIGHT_EXECUTABLE_PATH` 指定）。脚本选择随机端口和新临时数据库/存储/队列，测试后验证自有 API/Web/模型 Worker/PostgreSQL/Redis 退出才删目录；清理不能确认时保留临时目录和失败报告。不会借用现有 3000/3001/8000 服务。

本地最终证据见 [整链验收记录](reviews/2026-10-07-commercial-journey.md)。另有隔离的信号/强制退出恢复检查：API 目录 `SONGDANCE_TEST_REAL_AUTH_SERVICES=1 .venv/bin/pytest -q tests/test_commercial_stack_lifecycle.py`，无需真实供应商项目。

当前代码合同为 Free 每 UTC 自然月 1 次成功、单次最多 90 秒；游客最多 30 秒、签名访客一次成功体验；Pro Test 单次仍最多 90 秒。Test 价格与周期额度沿用现有 Test 快照，不能据此承诺 Live 价格或 5/10 分钟长音频。

## 2. 准备一个明确的配置文件

参考 `../.env.example`、`../infra/env.auth.example` 与 `../infra/env.creem.example` 的字段，整理为一个未提交的 `songdance/.env.commercial-test.local`。每个键只能出现一次，不直接拼接模板；保持开关关闭完成配置整理。该文件已受仓库 `.env.*` 忽略规则保护，仍须检查没有误加到暂存区。

- 使用独立测试 Supabase 项目、业务数据库/存储、Redis DB 与命名空间；不要借用线上数据。
- `SONGDANCE_ENVIRONMENT` 用 `test` 或 `development`，`SONGDANCE_BILLING_ENVIRONMENT=test`；当前 Creem 实现拒绝 production/Live。
- `NEXT_PUBLIC_SITE_URL` 与 API 的 CORS 站点一致；`NEXT_PUBLIC_API_URL` 与 `SONGDANCE_AUTH_API_URL` 指向同一 API origin。远程地址使用 HTTPS，本地开发/测试允许 localhost HTTP。
- 使用现代 `sb_publishable_` key，会话查询连接使用独立最小权限角色；管理员、service_role、`sb_secret_` 和完整数据库连接不能放入 `NEXT_PUBLIC_*`。
- 独立生成 bridge、下载和游客签名密钥；bridge 为 32–128 字符 base64url/hex，下载/游客检查采用相同安全字符范围。密钥保存到私密文件或平台密钥管理，不发送到聊天、测试报告或仓库。游客密钥必须跨副本、重启稳定，轮换按认证设置先排空在途任务。
- Creem Test key、webhook secret、Test product、plan version 必须配套。success URL 固定本站 `/billing/return`，已有 `/account` 配置也兼容；设置精确 webhook 路径并保留原始 body。

本地私密文件应只允许所有者读写：

```sh
# songdance/api/；文件需已存在，检查入口不会创建、改写或 chmod 文件
chmod 600 ../.env.commercial-test.local
.venv/bin/python -m scripts.check_commercial_config --env-file ../.env.commercial-test.local
```

检查不联网，只读取指定文件，不从进程环境、默认 `.env` 或文件密钥目录补齐漏项，不改变开关。沿用锁定解析器，重复键、非赋值行、命令/变量展开和异常编码会被拒绝；含私密配置的文件若对组/其他用户开放权限也会拒绝。报告只含字段名、错误码、布尔状态和当前短音频合同，不回显 key、密码、DSN、异常输入或供应商响应。

`configuration_format_valid` 表示文件值及 Settings 约束合格；`features` 列出对应功能的开关与前置条件。关闭且未填凭据的模板即使格式有效，`commercial_test_configuration_valid` 仍为 false，CLI 退出 2；缺少环境名称或明确非法值也会报错。当前完整 Test 组合须同时配置并显式开启 AUTH（Web/API 两处）、USAGE、PAID_USAGE、RELIABLE_QUEUE、GUEST_USAGE、CREEM 和 ACCOUNT_DELETION；符合时 CLI 退出 0。只有在隔离 Test 环境确实准备好后才改这些开关，Web 构建期 AUTH 变更需要重建。

即使退出 0，provider 连通性、数据库实际权限、SMTP/OAuth、商户商品和后台进程状态均固定为未验证，`production_ready=false`。工具不能核对分布在不同服务上的实际部署值是否相同；需另外核对所有副本的凭据、数据库、存储、队列和命名空间。

## 3. 隔离项目的实际联调顺序

1. 按认证设置配置真实 Google callback、本站 allowlist、Resend Send Email Hook/API 和 600 秒 OTP；该 API 主路径的准备见 [Resend 接入](resend-setup.md)，不另行并发配置 SMTP。实际验证送达、过期/复用、重发预算、Cookie、撤销与最近新登录。离线 publishable key/DSN 格式不能证明项目存在或权限最小化。
2. 在隔离业务数据库执行 `alembic upgrade head`，核对存储/Redis/队列一致。准备 API/Web、转录 Worker、Dispatcher、Billing Worker、账户删除 Worker 与清理任务；派发与删除恢复命令见现有设置和恢复手册。离线检查不会启动或探测这些服务。
3. 按 Creem Test 设置创建并核对 Test 商品、签名 webhook 和 Portal。实际执行测试卡付款、重复/乱序通知、查询授权、取消、退款、历史对账与删除前完整订阅核验。价格、币种、周期/税额字段及取消后状态需要供应商证据，不以本地替身代替。
4. 启用隔离 Test 开关后重建 Web，跑游客体验、Free 成功/失败与月边界、Pro 购买/扣量/导出/取消、幂等恢复、撤销、跨用户拒绝及账户删除闭环；保留测试标识、版本与不含敏感值的结果。
5. 另行完成 BA/LA、真实音乐固定集/专业复评、容量成本、实际客服地址、法律/隐私退款条款与商户审核。当前未完成项继续保留，不把 Test 配置合格、本地 E2E 或账户删除实现当作正式发布批准。

关闭新准入开关后继续用兼容后台进程排空已接受的任务、通知与删除申请；保留账本、幂等/身份墓碑和签名密钥，不能通过删历史或降级绕开权限和恢复要求。

## 4. 2026-10-07 控制台创建记录

用户明确确认当前 Test 方案为 US$9.90/月、每已付款周期 30 分钟，不再沿用早期一次性 credits 方案。本轮仅创建测试资源，未修改 Live 商品或开启真实收费。

- Supabase：Free 组织 `SongDance Test`，项目 `songdance-test`，项目 ID `amnsavenqfmmvnauyqzi`，区域 `ap-southeast-1`。数据库密码由用户自行输入并提交创建；项目设置页已可访问，名称与区域已核对。
- 项目地址：`https://amnsavenqfmmvnauyqzi.supabase.co`；控制台为 `https://supabase.com/dashboard/project/amnsavenqfmmvnauyqzi`。创建表单关闭 Data API，仅用于 Auth；尚未从创建后的设置页复核此开关。
- Creem：已在明确显示不处理真实支付的 Test Mode 创建并核对 `SongDance Pro Test`；Product ID 为 `prod_6VunYruwAmrEXb70DJdNrl`，状态 Active，USD 9.90/月，无 trial 或额外按量费用，税额默认另加。
- 商品描述注明每已付款周期 30 分钟、当前单次最长 90 秒及仅用于测试。额度仍须应用根据核验通过的付款授予，不由描述或回跳页授予。
- 创建资源时未获取或创建 API key、webhook secret、SMTP/OAuth 凭据和最小权限会话连接；未创建填好凭据的本地环境文件，未启动真实供应商联调。后续本地骨架与认证参数进展见第 5 节。

下一步按第 3 节配置登录回跳、Google/邮件/OTP 与会话只读权限，再准备配套 Creem Test key 和签名 webhook。邮件主路径已选定 Resend API Hook，详见 [邮件准备](resend-setup.md)。创建凭据或扩展权限前需用户确认；新认证密码的输入、确认与提交由用户完成。项目和商品存在不代表真实登录、测试卡付款、30 分钟授额或取消/退款已验收。

## 5. 2026-10-07 认证参数与 OTP 兼容

- 用户确认后，已保存测试项目 Site URL `http://127.0.0.1:3002`，回跳白名单仅一条 `http://127.0.0.1:3002/api/auth/callback`；页面重新读取核对，不添加通配符或线上域名。
- 当前 JWT 签名为 ECC（P-256），仅核对、未轮换或撤销密钥。邮箱 provider 已启用，OTP 有效期保存并复核为 600 秒，长度按用户要求保留 8 位；未更改 Google、密码或匿名登录开关。
- 新建 `songdance/.env.commercial-test.local` 配置骨架，权限 0600，已核对 Git ignore。填入已创建的 Supabase URL/Test Product ID、Web 3002/API 8001 与独立 Redis 6381/命名空间/存储路径；凭据和业务数据库留空，所有功能开关关闭，未启动这些服务，未修改现有 3001 预览。
- 实跑 `scripts.check_commercial_config`：格式有效、顶层错误为空，但商业化配置未完成，退出 2；缺少凭据/数据库和关闭开关的结果符合当前阶段，不据此开启功能。
- 已修复应用只接受 6 位 OTP 的不兼容：输入框与 BFF 共用严格 6/8 位格式，八语言标签不再限定六位。回归、截图和独立审查证据见 [OTP 兼容记录](reviews/2026-10-07-otp-compatibility.md)。
- 当前未启用 Hook 时默认邮件预览仍为登录链接，Source/Save 不可编辑，控制台要求自有 SMTP 才能编辑该路径。用户随后选定 Resend API Hook 主路径；Resend 已登录 Free 账户与额度已核验，域名列表为空。实际主域名/DNS、验证码 Hook/API、客服收信、Google OAuth、publishable key 和会话只读连接仍待准备；Creem Test key/webhook、隔离数据库迁移及真实供应商联调也未完成。

## 6. 2026-10-12 notavue.io 发信 DNS 准备

用户确认 `notavue.io` 与 Cloudflare Free，并分别确认资源创建及“只准备 Cloudflare 记录”。已创建 Resend `mail.notavue.io` 和 Cloudflare 免费区域，保存实际 DKIM TXT、两条发信 CNAME、子域 DMARC；保留两条原网站 A 的 IP，代理均关闭。直接查询分配的 Cloudflare 域名服务器返回正确邮件/A 记录，区域 UI 仍为 Pending；公开 NS 仍是 Spaceship、旧 DNSSEC DS 仍存在，尚未迁移或完成 Resend 验证。

设置证据与完整待办见 [DNS 准备记录](reviews/2026-10-12-resend-dns-preparation.md) 和 [Resend 接入](resend-setup.md)。客服目标地址为 `support@notavue.io`，当前未配置收信，不写入应用已核实客服配置。API key/Hook/webhook/真实邮件及完整供应商验收继续待办，未开启登录或收费。

## 7. 2026-10-13 DNSSEC 故障恢复与迁移暂停

用户完成 Spaceship 登录后已核对账户内域名、0 条自定义 DNS 和重定向。经单独确认禁用旧 DNSSEC，原签名提前停止但父区仍有旧 DS，导致公开解析失败；另经确认恢复，生成新 DS 32322，并在 10:48:29 核对四个 `.io` 父区及两家公共解析器的匹配/NOERROR + AD，11:06:37 复查稳定。受测解析和验证链已恢复，NS 仍为 Spaceship，Cloudflare 仍未生效。已获授权联系支持，11:07–11:08 明确确认现有自助 UI 不支持单独撤 DS/保签；等待用户选择保留现 DNS 验证发信或接受维护窗口再迁移，不重复同一禁用按钮承诺无中断。事实与查询见 [恢复记录](reviews/2026-10-13-dnssec-recovery.md)。未完成 Resend Verified 或 MAIL-01，未开放真实登录、邮件或收费。

## 8. 2026-10-13 维护窗口迁移（DNS/DNSSEC 受测验收已完成）

用户随后接受维护窗口暂时中断风险，11:39 复核四个父区、两家公共解析器及 Cloudflare 两台新权威记录一致；约 11:44–11:45 在现场再次确认后关闭 Spaceship 自动 DNSSEC。11:45 父区仍发布 DS 32322、旧区已停止签名，公共 A 暂时 SERVFAIL；11:53:28 首次确认四个父区均无 DS，至少 12:53:28 后再复核旧 TTL 缓存退出并现场确认切 NS。11:53 公共 A 一家恢复、另一家尚为 SERVFAIL，原 NS 未改。用户另行确认每 5 分钟只读自动跟进，已创建 `notavue-dns`，不自动跳过安全确认。不反复开关或宣布无中断；新委派稳定后再恢复新 DNSSEC。实时证据/安全条件见 [维护迁移记录](reviews/2026-10-13-cloudflare-migration.md)；本段更新第 7 节的历史暂停状态，不标记域名迁移、Resend 或正式上线已完成。

13:10 更新：旧 DS 等待和 12:54 复核完成，用户确认后于 13:07 在 Spaceship 保存 gannon/romina 两个 Cloudflare NS；UI 为“在传播中”、DS 0 条。四个父区暂仍返回旧 NS；两家公共 A 在 13:07 返回 NOERROR 但无地址答案，不能标记解析可用。已触发一次 Cloudflare NS 检查；继续等待父区/公共委派、旧缓存退出及新 DNSSEC 验证。注册商未转移、Cloudflare 保持 Free，未部署应用或验证邮件。

13:14 更新：四个父区全部更新为 Cloudflare NS 的首次确认时刻为 13:14:27；两家公共 NS 已更新、A 返回原两个 IP、无 AD，受测解析恢复。最早 14:14:27 后再复核旧 NS 缓存退出及恢复新 DNSSEC。Cloudflare 页面刷新和跟进提示更新遇审批服务 403，动作未执行；原 5 分钟只读跟进仍保留，控制台 Active 尚未复核，不将公共委派更新等同 DNSSEC 或邮件验收完成。

14:35 更新：旧委派等待、门槛后 DNS/记录与 Cloudflare 接管状态已复核。用户确认后已启用新签名，两台权威 DNSKEY/RRSIG 可见；用实际 KSK 复算 DS 2371 / 13 / 2 摘要与 UI 匹配后，在 Spaceship 保存唯一一条新 DS。父区暂仍无 DS、公共 A 正常但无 AD，完整验证链尚未恢复；原只读跟进继续核对。Resend、客服与真实登录支付验收继续待办。

14:50 最终更新：四个父区的新 DS 一致，两家公共 DS/A 均 NOERROR + AD、A 为原两个 IP；Cloudflare 控制台显示 DNSSEC Success。本次受测迁移范围已完成，按用户约定将临时自动跟进 `notavue-dns` 设为 PAUSED。注册商仍为 Spaceship、Cloudflare Free；Resend Verified、真实邮件、客服及登录支付联调仍未签收，Phase 38/39 和生产发布状态不因此完成。


## 9. 2026-10-14 Google 测试 OAuth 与应用闭环

Notavue Auth Test / Notavue Web Test 已在用户授权后创建，OAuth 应用为 Notavue、External/Testing、三项基本身份 scope 和单一测试用户；客户端凭据仅配置到 Supabase songdance-test Google provider，未开通计费服务。真实 Chrome 已完成 Google PKCE、账户页及退出，同一会话退出后从数据库移除并被应用撤销查询拒绝。本机测试服务现已关闭，Google provider 保留供下一阶段使用。

完整配置/事实与未验项见 [Google 联调记录](reviews/2026-10-14-google-oauth-integration.md)。正式 Google 品牌呈现、HTTPS Cookie、完整 BA、Creem Test 其余分支、容量/法律/音乐质量验收继续待补；不因本次 Google 测试完成而开放生产。

## 10. 2026-10-14 Creem Test 真实商业闭环

Notavue Pro Test 已完成一次无真实扣款的 Test 卡付款。德国测试税额下商品 990 分、税额 188 分、模拟实付及全额退款均为 1178 分；用户现场确认总额和条款。签名通知绑定并授予一次 1800 秒，真实约 30 秒 Bach 片段转谱仅扣一次 30 秒，MIDI/MusicXML/PDF 实际下载；Portal 取消后 1770 秒保留，全额退款后权益 revoked、续费停止核验 verified，新任务准入返回 403。四条真实通知均已处理，控制台显示投递成功率 100%。

新增单路径 test-only listener，修复明确 HTTP 400 创建拒绝被误记 uncertain、同步创建响应缺可选 request_id 的兼容性；后续 GET 绑定要求保持。218 项定向与 6 项临时 PostgreSQL 回归通过，独立审查/复审无遗留可行动问题。临时 webhook 只读核对为禁用，隧道及本轮全部服务已关闭，默认开关 false、私密文件 0600 且受忽略。

本机商业测试站点和 Supabase Site URL 已按授权改为 localhost:3002，两条精确 callback 保留。本轮未重做退款后最终浏览器账户/退出、active 订阅退款自动发取消 POST、多周期、部分退款/争议、全历史对账与账户删除供应商闭环；不整体签收 BA 或发布。证据、限制及下一步见 [Creem Test 联调记录](reviews/2026-10-14-creem-test-integration.md)。

## 11. 2026-10-15 对账与 active 退款补验

原退款账本重复处理与两轮真实历史对账未复活权益或重置30秒消费；本地合成同通知三次仅一行、篡改正文拒绝。独立第二账本使用原授权剩余的一笔 Test 交易，保持 webhook 禁用：付款 completed 时应用仍未授额，随后对账恢复一份1800秒；同商户旧交易因未绑定保留审查，不按相同邮箱认领。

全额模拟退款1178分后先 GET 确认订阅仍 active，再由应用原后台核实退款并发送取消 POST 一次，GET 确认 canceled、权益 revoked、取消意图 verified；重复扫描不重授额或重取消。原/新两份账本准入均403，退款后真实账户暂停提示和退出后重新登录要求通过。未新增生产逻辑、未重跑上一批已通过的218/6项回归；本轮取得的是实际供应商与浏览器补证。

两次成功模拟付款额度均已用完、均已全额退款；本机服务和隔离集群已关闭，webhook 保持禁用，私密配置0600且默认开关关闭。多页/真正跨付款周期、失败卡、部分退款/争议、退款续费竞态及账户删除供应商闭环仍待验；详细报告见 [补充验收记录](reviews/2026-10-15-creem-reconciliation.md)。

## 12. 2026-10-15 无账单账户删除与订阅保护

真实Creem客户订阅列表及未知绑定保护已核对：两份Test/canceled订阅可读，原账本遇未知订阅先阻止删除、无外部取消或文件清理。专用新建无账单验收库通过真实Google/BFF/最近会话查询发起删除；用户确认后先提交停用检查点，再删除合成任务与邮箱，保留身份和已用1次的墓碑，真实重新登录不复活账户或重赠额度。原两份账本用户仍active、退款权益revoked、消费30/0不变。

115项定向、14项隔离PostgreSQL回归通过，独立审查80项相关回归通过且无可行动问题；审查者未直接验证当前数据库或真实供应商/UI，不扩大为完整独立实测。临时目录初始夹具命名不符合生产规则，其浏览器整链覆盖无效；后续新增2项本地整链，用生产转谱入口与FFmpeg留下真实临时目录，验证申请、原Worker清理、失败重试及另一账户目录保留；新增2项/相关70项及fresh专项审查通过，见 [临时目录补验](reviews/2026-10-15-account-temp-cleanup.md)。已退款/已取消付费副本的限定删除分支另见下一节，正常完整账本/active停费、真实双账户互访与供应商竞态仍待补，BA-11/13不整体勾选。测试服务已关闭，原记录保留，见 [账户删除验收](reviews/2026-10-15-account-deletion-acceptance.md)。

## 13. 2026-10-15 已退款付费副本删除（限定分支）

已新建原第一份付款账本/存储的独立副本，按两份原账本精确一致的已验证issuer/subject导入第二份completed checkout意图，再由原业务代码查询Creem核验两份订阅绑定；两份均canceled。完整付款投影恢复因两个历史周期重叠被既有规则拒绝，副本仍只保留原revoked/used30付费期，第二笔投影retry事件未清除；不把完整恢复标为通过。

只读Creem预检逐一验证2份已取消订阅后回滚；用户现场确认后真实DELETE先因旧会话403，重新Google登录后202。两批原Worker先核验两订阅并提交停用检查点，再清理副本1任务/6文件及邮箱；身份、revoked/used30、账单和retry冲突均保留。实际退出/Google重新登录后仍停用，未获新额度；第三批Worker handled0。仅一条用量周期锁更新时间变化，其余8财务表内容与ready摘要一致，原三库全表摘要始终不变。fresh完成审查及80项相关测试通过，审查者另独立只读核对当前库/文件；不新增付款，限定已退款/已取消分支，active停费及完整BA仍待补。[执行与范围记录](reviews/2026-10-15-paid-account-deletion.md)。

最后真实会话已退出，本轮Web/API与恢复的隔离PG/Redis均按资源身份核对后关闭；四份数据库/审计保留，私密配置默认开关false，未提交或部署。

## 14. 2026-10-15 双身份任务访问与游客认领（限定范围）

初次因浏览器OAuth重置/超时中断并收尾。用户恢复网络后，已用两个不同的真实Google/邮箱身份完成登录及任务权限验证：1个浏览器上传任务、3个显式数据库夹具，真实BFF/JWT/session reader/API下自有查询/下载200，跨身份查询、下载签名、retry/DELETE/claim和事件上报404；游客无/错误凭证拒绝、正确认领幂等、旧cap撤销及他人抢认拒绝。30个编号请求与数据库断言通过，fresh独立审查及18项相关回归通过；没有替换真实认证。

真实匿名上传曾被现有并发限额429拒绝，保留失败而改用显式guest数据库夹具，不放宽限额或冒充完整双用户上传/转谱。唯一剩余授权邮件已用1封，原SQLite源库未变；Hook与公网入口关闭、临时public测试页移除、两会话退出，本轮Web/API/Redis全部停止。账单、Portal、并发认领及完整BA-11仍待验。[本轮记录](reviews/2026-10-15-two-account-acceptance.md)。

## 15. 2026-10-19 双身份账单/Portal限定验收

独立复制原付款库，按精确Google issuer/subject核对后加入既有邮箱身份。真实Google看原revoked/used30账单并生成一次原客户Test Portal；邮箱只获Free摘要，Portal409且不发供应商请求。带另一user/customer的query不能改变本人摘要，Portal/checkout归属body注入422。两个真实身份共10个请求通过；不是两个不同付费客户，未打开Portal内部或修改订阅，没有新付款。

现场发现401/409/422账单错误响应丢失缓存头，新增6回归修前失败，最终响应中间件局部修复后45项通过、fresh独立审查无可行动问题。真实邮箱5请求重验均带private/no-store，总15个编号请求保留；供应商仅3准备GET和1Portal POST，原4库及8财务表全字段摘要保持不变。新授权1封OTP已使用，Hook/临时公网入口关闭、测试页移除、两会话退出、本轮Web/API/PG/Redis均关闭；配置默认flags false，未提交或部署。[执行与边界](reviews/2026-10-19-billing-isolation.md)。

## 16. 2026-10-19 真实双会话并发认领限定通过

审批恢复后实测五个旧测试端口关闭，保留历史失败记录恢复隔离库，复用仍有效的原Google/邮箱真实会话。Chrome普通与无痕分别执行三轮任务锁前同步竞争，24个编号请求全部符合预期：每轮一200一404、赢家读/重放200、败者与旧游客凭证404；PG唯一owner匹配赢家、guest hash清空、源文件与来源摘要完整。单API进程、两真实已验证身份、3个合成游客夹具限定通过；主Agent与fresh reviewer分别PG预检1项通过，独立证据断言复核通过。本轮未发新邮件、开公网入口、生成Portal或付款；生产claim未改。双付费客户、多API、claim/delete及同邮箱未验证身份待验，完整BA-11不勾。[详细记录与收尾](reviews/2026-10-19-claim-race-preparation.md)。

本批两会话原UI退出并确认，无痕关闭；所有本轮服务停止、五端口实测关闭、临时页移除，数据保留。无需重做已通过三轮竞争。

## 17. 2026-10-19 同邮箱身份隔离本地集成

本机RS256签名JWT与一次性PostgreSQL下，原SupabaseVerifier及私有session视图SQL拒绝邮箱未确认身份，即使JWT声明email_verified=true且携正确游客cap，11路径均401且用户/身份/任务/客户绑定快照不变。模拟确认后同邮箱不同subject得到独立业务用户，不继承原任务、客户绑定或Portal；新身份Portal409且离线provider调用为零。新增PG1项及31相关回归/Ruff通过，fresh审查无问题、独立PG1项通过；生产代码未改，无真实邮件或付款。此结果不代表真实Supabase注册/关联或付费额度验收，完整BA-11继续待验。[记录](reviews/2026-10-19-same-email-identity-isolation.md)。

## 18. 2026-10-19 多API认领本地集成

两独立spawn HTTP进程/连接池和同一一次性PG下三轮同步竞争，一200一404；OS/backend PID及锁前事件证明跨进程，两实例的胜者/败者/旧cap门禁与最终唯一owner一致，替换一个服务进程后归属保持，源文件完整。多API与同邮箱集成2项、18回归和Ruff通过；fresh独立审查无问题、多进程PG独立1项通过。生产逻辑未改，无真实发信/付款/公网入口，所有自有测试进程和PG已清理。云端负载均衡、真实BFF多实例、两个付费客户及认领/删除竞争未覆盖，不整体勾BA-11。[记录](reviews/2026-10-19-multi-api-claim-isolation.md)。

## 19. 2026-10-19 认领与删除竞争本地集成

两个app/独立engine以本机签名JWT、原验签/私有会话SQL验证两种同user操作顺序，pg_blocking_pids确认实际锁等待。认领先行200→删除202，任务纳入Worker清理；删除先行202→认领409，未归属guest保留。两个app的后续门禁、两批停用/清理、必要身份墓碑与他人源文件保持、重复Worker handled0通过。新增2项、删除PG组合16项、67普通回归及Ruff通过；fresh独立审查无问题、独立PG2项通过。仅合成无账单账户，测试资源已清理，生产未改；真实active停费、多进程删除竞争、付费消费/退款与完整BA-11/13仍待验。[记录](reviews/2026-10-19-claim-account-deletion-race.md)。

### 2026-10-20 双客户补验受阻与客户归属冲突修复

唯一新授权USD9.90 Creem Test付款返回Google既有customer，无法建立第二份独立客户，真实双付费客户验收未通过，两份Portal均未调用。唯一新交易已全额模拟退款、新订阅canceled，未改原Google绑定，原五库与Google七张财务表逐字段摘要不变。现场发现冲突事务回滚使用户永久payment_confirming，已修复为持久review_required/blocked且不串绑、不授额、不许重购；补齐历史终态与新pending共存、PG并发唯一绑定、cleanup/completed删除单迟到冲突重开billing/review门禁。主Agent171 passed/1 skipped、PG聚焦12 passed与Ruff通过，fresh独立复审无可行动问题；真实隔离库及邮箱账户页待审状态复验通过。两会话退出、临时页面移除、五端口实测关闭、私密配置flags禁用，证据保留。未新增第二笔付款或绕过唯一约束；BA-11/13及两个同时active客户仍未整体签收。详见[冲突、退款及修复记录](reviews/2026-10-20-provider-customer-conflict.md)。

### 2026-10-20 两个不同真实付款客户的指定矩阵通过，退款受阻

新隔离副本中邮箱应用身份使用Gmail付款，实际Creem新customer与Google原hello@付款客户不同；唯一Test实付USD11.78，原后台对账授1800秒/used0。两身份各6条summary/query/body拒绝及各1Portal共14编号通过，用户确认两matrix complete/passed和Portal客户邮箱；provider owner各成功一次，Portal前后邮箱七财务表不变。六来源PG库、来源mail、Google七财务表摘要未变。生产代码未改，临时受限provider9项与投影4项离线检查、独立复审无可行动问题；第三方UI由用户操作，状态/内容证据边界保留。

用户全额退款被Creem Test“余额不足”拒绝，GET确认交易仍paid、未退款；随后用户单独取消新订阅，GET与本地投影确认canceled，PaidPeriod active及1800秒保留，取消不等于退款。真实refund/repeat未通过，未充值或新增付款，不勾完整BA-11/13、两同时active客户或真实付费删除。两应用会话用户确认退出、Hook禁用；本轮全部服务停止、临时页移除、五端口关闭。支持草稿仅本地保存、未发送；需用户向Creem核实Test余额规则后再推进退款。详见[验收与退款阻断记录](reviews/2026-10-20-distinct-payment-email-preparation.md)。

### 2026-10-20 两期完整账本的本地付费删除恢复

一次性PG/离线身份与支付下，两相邻非重叠PaidPeriod、旧期30秒consume、当前15秒预占及另一付费客户任务/账本验证通过。停费前失败与取消成功响应丢失均保留billing/retry及文件；恢复核实后先停用再清理，不重复取消，原期release一次、旧consume/付款/身份墓碑保留，同subject换邮箱不新建用户/Free周期；另一客户各表全字段及源字节不变。新增2项、PG组合20项、64普通回归/1opt-in skip、Ruff通过，fresh审查与独立PG2项通过。初次测试存储API误用及审查发现的他人任务快照缺口已修正，生产未改，临时测试资源由fixture清理。此为本地指定分支，不解除真实Test退款阻塞或签收真实付费删除/完整BA-13。[记录](reviews/2026-10-20-paid-history-deletion-local.md)。
