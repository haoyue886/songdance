# Cloudflare 维护窗口迁移

日期：2026-10-13。时区：Asia/Shanghai。目标为注册/续费留 Spaceship，DNS 改为 Cloudflare Free；不转移注册商、不改网站 A 目标、不启用代理、付费、应用部署或业务邮件。

## 当前状态

14:50 验收完成：Cloudflare 已接管，签名已启用，新 DS 2371 / 13 / 2 与实际 KSK 复算结果匹配。四个 `.io` 父区发布相同新 DS，`1.1.1.1` 和 `8.8.8.8` 的 DS/A 查询均 NOERROR + AD、A 返回原两个 IP，受测 DNSSEC 委派链已恢复；Cloudflare 控制台显示“Success! notavue.io is protected with DNSSEC.”。本次 DNS/NS/DNSSEC 迁移范围已完成，按用户约定已通过应用工具将临时跟进 `notavue-dns` 设为 PAUSED。无需再提交 NS/DS、请求重复恢复授权或执行周期复查。

起算证据保留：**13:14:27（05:14:27 UTC）首次确认四个 `.io` 父区全部更新为 gannon/romina**，旧委派等待门槛为 **14:14:27（06:14:27 UTC）**。不将少量受测解析器的结果当全球所有缓存已经独立验证。

## 事件与证据

- 用户明确接受维护窗口内可能暂时中断解析，并在实际动作前再次确认关闭 Spaceship 自动 DNSSEC、撤下 DS 32322、暂时保留原 NS。
- 11:39:42–11:39:45 预检：四个 `.io` 父区 DS 为 32322，TTL 3600；两家公共 A 均 NOERROR + AD。Cloudflare UI 为 Pending/Free，两条 A 及四条邮件记录均匹配既有准备，代理关闭；分别直接查询 gannon/romina 的 A、DKIM TXT、两条 CNAME、DMARC TXT，均 NOERROR + aa，内容一致。
- Spaceship 账户仍显示原 NS `launch1.spaceship.net` / `launch2.spaceship.net`、0 条自定义 DNS；自定义 DS 入口可用，现为 0 条记录。尚未提前登记任何 Cloudflare DS。
- 约 11:44–11:45 经确认执行一次禁用，UI 随后确认“DNSSEC 已禁用”。11:45:12–11:45:14 父区仍发布 DS 32322，旧权威无 DNSKEY，两家公共 A 均 SERVFAIL。该中断为已披露且获用户接受的供应商行为，不是本地超时推断。NS 未切，未反复开关。
- 11:53:26–11:53:28 首次确认四个父区 DS 查询均 NOERROR、ANSWER 0，并返回父区 NSEC3/SOA 否定答案。以最后完成的 **11:53:28（03:53:28 UTC）** 为旧 DS 缓存退出起算点；至少到 **12:53:28（04:53:28 UTC）** 后才能复核切 NS 条件，不把该时间当自动批准或保证所有缓存已退出。
- 11:53:28 两家公共 DS 查询均无 DS；11:53:29 Cloudflare 公共 A 为 NOERROR、原两个 IP、无 AD，Google A 暂为 SERVFAIL。该阶段 DNSSEC 保护尚未恢复，局部 A 恢复不代表所有公共解析器恢复；NS 仍未切换。
- 11:57:17 复查：Cloudflare 公共 A 仍为 NOERROR/原两个 IP、Google A 仍为 SERVFAIL；`a0.nic.io` 委派保持原 Spaceship NS，TTL 3600。未提前切换或用其他验证模式掩盖 Google 的失败。
- 11:59:28–11:59:33 首次自动复查：四个父区仍无 DS，委派均为原 Spaceship NS（TTL 3600）；两家公共 DS 均无答案，A 均 NOERROR、返回原两个 IP、无 AD，Google 本次受测解析已恢复。旧 DS 起算点仍为 11:53:28，最早 12:53:28 后再复核切 NS；不因两家 A 恢复而提前变更。未操作控制台或修改外部配置。
- 12:14:04–12:14:06 自动复查：四个父区仍无 DS、原 NS 未变，两家公共 DS 均无答案；Cloudflare A 为 NOERROR，Google A 一次 SERVFAIL。12:14:40–12:14:41 只读复核 Google DS 仍无答案、两家 A 均 NOERROR/原两个 IP/无 AD。本轮观察到公共查询仍可能短暂波动；尚在既定旧 TTL 等待期，不更改 11:53:28 起算点，不提前切 NS，不把一次恢复当全球稳定。未修改外部配置。
- 12:54:24–12:54:30 门槛后复核：距离 11:53:28 已超过旧 DS TTL 3600 秒；四个父区仍无 DS、原 NS/TTL 3600 未变，两家公共 DS 均无答案、A 均 NOERROR/原两个 IP/无 AD。12:54:28–12:55:05 分别直接查询 gannon/romina 的 A、DKIM TXT、两条发信 CNAME 和 DMARC TXT，全部 NOERROR + aa、内容与准备记录一致。没有用关闭验证获得成功，也不宣称所有全球缓存已经独立验证。
- 12:55 已通知旧 DS 等待门槛满足，并首次请求现场确认仅将 NS 改为 gannon/romina；尚未收到本次 NS 切换的用户回复，未提交外部设置。后续无变化的自动轮次仅复查、静默，不重复发送同一确认；收到具体回复后由交互轮次再次核对状态并执行。本步暂不登记 Cloudflare 新 DS，待新委派缓存退出后再恢复 DNSSEC。
- 用户随后明确确认将 NS 换为 gannon/romina。13:07 在已有登录的 Spaceship 表单填入两个精确值，保存后重新读取页面：自定义名称服务器显示这两个值、状态“在传播中”、DS 0 条。仅提交一次，未增加其他 NS 或 DS。
- 13:07:28–13:07:31 查询：四个父区仍是 launch1/launch2，TTL 3600，DS 均无答案；两家公共 NS 是旧值（TTL 1800），A 为 NOERROR/ANSWER 0，旧区 SOA TTL 1800。这个阶段存在实际无地址解析结果，不等于服务可用。
- 13:09 左右点击一次 Cloudflare 的 Check nameservers now，随后页面显示正在检查，请等待更新；仍待确认 Active。13:10:01–13:10:02 四个父区仍为旧 NS。旧权威两台的直接 UDP NS 及 TCP NS/A 查询超时，未据超时推断旧区已删除或获得其完整 NS TTL；受测父区旧委派 TTL 为 3600，公共旧 apex NS 剩余 TTL 为 1800。
- 13:14:26–13:14:27 四个父区 NS 均为 gannon/romina、TTL 3600，DS 均无答案。13:14:27–13:14:28 两家公共 NS 已更新，A 均 NOERROR、原两个 IP、无 AD。公共查询显示的新 Cloudflare apex NS TTL 86400/21600 是新记录的缓存时间，不当作旧委派等待 TTL。以最后一个父区 NS 查询完成的 13:14:27 为新阶段起算点。
- 13:44:17–13:44:19 自动复查：四个父区仍为新 NS、无 DS，两家公共 NS 为新值。Cloudflare A 正常；Google A 一次 NOERROR/ANSWER 0，返回旧 launch1 SOA，负缓存 TTL 1800。13:44:58–13:44:59 只读复核 Google NS 仍为新值、A 恢复原两个 IP。仍在已知旧委派等待期，不重置父区起算点或提前恢复 DNSSEC；到门槛后仍须结合公共 A/旧区负缓存状态复核。未修改外部配置。
- “更新自动跟进提示”及“刷新 Cloudflare 页面”分别遇自动审批服务 403（review could not be completed），均未执行；没有改写 automation.toml、换入口绕过审批或再次提交 NS。既有 `notavue-dns` 每 5 分钟跟进保持原配置，并按本文件的最新状态接续。独立 NS 文档审查 Agent 也因模型服务 403 失败，本次改由主 Agent 自审，不宣称独立复审通过。
- 14:09:57–14:10:02 自动复查：四个父区和两家公共 NS 均为新值，DS 均无答案，两家 A 返回原两个 IP、无 AD。随后尝试只读核对 Cloudflare Active，Chrome 中的用户同步操作使两次标签/窗口操作被中止（user changed app）；未继续抢占页面、处理其他站点验证或修改外部配置。14:13:19 尚未到缓存门槛，Active 仍待页面稳定后复核。
- 14:16:51–14:17:04 门槛后复核：四个父区及两家公共 NS 为新值，DS 均无答案、两家 A 返回原两个 IP且无 AD；分别核对 gannon/romina 的 A、DKIM TXT、两条发信 CNAME、子域 DMARC，均 NOERROR + aa 且内容一致。两台新权威 DNSKEY 均 NOERROR/ANSWER 0，符合当前签名尚未启用的状态；没有提交 DS。
- 本轮只读控制台复核：Chrome 专用标签连接报告 auth token 不可用，沿用已授权原生窗口读取。一次刷新初始仍显示等待传播，后续重新读取已更新为接管完成欢迎页，仍为 Free、注册商显示 Spaceship。DNS Settings 列出 gannon/romina、“Enable DNSSEC”，Multi-signer/Multi-provider 均关闭。通用欢迎页的代理文案不作为实际代理开启证据；本轮未操作代理、付费或其他安全开关。
- 14:25 首次发出恢复 DNSSEC 的现场确认，请用户授权启用 Cloudflare 签名、核对两台新权威 DNSKEY/签名并将匹配新 DS 登记到 Spaceship。尚未收到该确认回复；后续无变化自动轮次不重复催促。启用入口已准备，但未点击，未注册新 DS。
- 用户随后回复“确认，恢复 DNSSEC”。约 14:28–14:29 点击 Cloudflare Enable DNSSEC，14:29:28–14:29:31 两台权威均 NOERROR + aa、发布相同 KSK（257/3/13）和 ZSK（256/3/13）；DNSKEY 的 RRSIG key tag 2371，A 的 RRSIG key tag 34505。Cloudflare UI 为签名已启用、等待注册商添加 DS 的 Pending setup，没有提前标记父区或公共链完成。
- 14:30 使用 API venv 的 Python 标准库 base64/struct/hashlib，将实际 KSK RDATA 与 notavue.io 的规范线格式名称复算 key tag/SHA-256；得到 2371 / 13 / 2 及下列摘要，与 Cloudflare DS 弹窗完全匹配。dnspython 未安装，未安装新依赖或把 RRSIG 的存在冒充独立密码学验签通过；完整委派链仍以父区匹配及公共 AD 为验收。
- 约 14:34–14:35 在 Spaceship 0 条自定义 DS 的表单新增一条记录，将默认算法 8 改为 13 ECDSA/SHA-256，摘要类型保留 2，核对 key tag 与完整摘要后保存一次。重新读取 UI 后为 1 条持久记录、四字段匹配、保存/撤销按钮消失并显示删除入口。未新增历史 Spaceship DS、其他 DS、NS 或付费设置。
- 14:35:41–14:35:43 查询四个父区 DS 仍 NOERROR/ANSWER 0；两家公共 A 返回原两个 IP及 RRSIG，但均无 AD。域名地址解析正常，父区新 DS 发布和公共验证仍待完成，保留 Cloudflare 签名不中断。
- 14:42:24–14:42:25 四个父区均发布下列 DS 2371；Cloudflare 公共 A 已带 AD，Google DS 带 AD但 A 尚无 AD。14:45:41 Google A 仍为先前缓存（剩余 TTL 101），未将其标记为验签完成。Cloudflare 页面随后确认 DNSSEC Success；没有取消签名或清除公共缓存。
- 14:50:07–14:50:08 最终复核四个父区 DS 一致，两家公共 DS/A 全部 NOERROR + AD，A 均为 34.216.117.25 / 54.149.79.189。本轮判定受测迁移验收完成，不宣称每个全球缓存均已单独检查，也不据此签收邮件送达、应用部署或产品上线。
- 用户曾授权每 5 分钟只读跟进，并要求迁移完成后停止。完成上述验收后，通过 automation_update 保留原名称、提示、频率和目标聊天，仅将 `notavue-dns` 状态改为 PAUSED，工具确认更新成功；未手工改写 automation.toml。

## 已执行的安全条件与后续

1. 已记录四个父区均撤下 DS 32322 的首次确认时刻 03:53:28 UTC。后续若重新发现旧 DS，不使用原起算点跳过检查；不能从按钮点击或任意前置查询时刻起固定等一小时。
2. 自上述时刻起至少等待实测旧 DS TTL 3600 秒，即 04:53:28 UTC 后，并复核父区、公共 DS/A；普通解析应为 NOERROR，而非用关闭验证获得成功。不声称所有全球缓存均已检查。
3. 用户确认的目标 NS 已保存，四个父区/公共委派、新权威完整记录、Cloudflare 接管状态及 A 地址答案均已核对。历史旧区 NODATA 已在最终受测 A 查询中退出。
4. 新 NS 起算点为 05:14:27 UTC，06:14:27 UTC 的旧委派等待门槛、门槛后公共 NS/A、新权威记录与控制台接管完成状态已复核。恢复授权、新签名和匹配 DS 已落实，14:50 父区 DS / DNSKEY / 两家公共 AD 一致后完成验收。
5. 后续进入 Resend 域名验证、客服收信和邮件 API/Hook 联调。该阶段尚未完成，迁移验收不自动开启真实登录、邮件发送或收费。

## 当前 Cloudflare DS（公开参数）

```text
2371 13 2 83EAD592FA3AE8F58AD863B4FA4B735C9B35B1FB297DF863D6CDEB2FA0A1EEE2
```

对应实际 KSK 公钥（公开 DNSKEY，不是私钥）：

```text
mdsswUyr3DPW132mOi8V9xESWE8jTo0dxCjjnopKl+GqJxpVXckHAeF+KkxLbxILfDLUT0rAK9iUzy1L53eKGQ==
```

## 验证与边界

DNS 查询使用 `dig`，针对父区 DS/NS、新旧权威 A/DNSKEY、公共 DS/A；网络权限放行仅用于公开只读查询。Chrome 扩展连接报告 auth token 不可用，控制台实际采用 cua_repl 的原生 Chrome 窗口，不读取 Cookie、网络响应或绕过审批。

此前故障恢复和支持结论见 [恢复记录](2026-10-13-dnssec-recovery.md)，支持编号 `SPS-YGU-3557`；邮件记录见 [DNS 准备记录](2026-10-12-resend-dns-preparation.md)。本轮未运行无关产品测试，也未把 DNS 迁移当 Resend Verified、邮件送达、生产 TLS 或上线验收。

本轮通过 agent-reach 代理读取超时后直接获取 Cloudflare 官方 DNSSEC Markdown，核对移除 DS、等待旧 DS TTL、切 NS、等待旧 NS TTL、启用新签名及匹配 DS 的顺序。OpenAI Docs 技能通过官方搜索结果读取 [Scheduled tasks](https://learn.chatgpt.com/docs/automations?surface=app)，确认当前聊天的分钟间隔跟进、权限与本机运行边界；早先终端官方页面返回 Forbidden，未将其当正文读取成功。

独立文档审查首轮只读检查本批维护记录、邮件准备与计划，未确认范围内 P0–P2；指出邮件总览的恢复历史仍写成当前状态的 P3，主 Agent 已修正并自检。复审委派未成功收到任务正文，不能将最终更新冒充已独立复审。首轮审查核对 22 个本地链接及差异检查，未独立查询 DNS/操作控制台；本轮外部状态证据由主 Agent 实测提供。

最终 DNSSEC 恢复批次另派独立 code-reviewer，但工具未传递派发正文，审查者仅读取技能/工作区状态，未给出通过结论。按项目降级约定由主 Agent 自审 DS 复算、字段、时序与文档一致性；不把这次失败的派发算作独立复审。实际验证为上述供应商 UI、公开 DNS/AD、标准库 DS 复算及 `git diff --check`，未运行无关产品回归。
