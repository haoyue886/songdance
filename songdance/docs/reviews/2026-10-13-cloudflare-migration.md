# Cloudflare 维护窗口迁移

日期：2026-10-13。时区：Asia/Shanghai。目标为注册/续费留 Spaceship，DNS 改为 Cloudflare Free；不转移注册商、不改网站 A 目标、不启用代理、付费、应用部署或业务邮件。

## 当前状态

13:07 用户确认后已在 Spaceship 保存自定义 NS `gannon.ns.cloudflare.com` / `romina.ns.cloudflare.com`。**13:14:27（05:14:27 UTC）首次确认四个 `.io` 父区全部更新为这两个 NS**，DS 均为空；两家公共 NS 已更新，A 返回原两个 IP，受测解析恢复。旧父区委派 TTL 为 3600 秒，最早 **14:14:27（06:14:27 UTC）** 后再复核缓存及新 DNSSEC 恢复条件。Cloudflare 已收到名称服务器检查请求，但后续页面刷新遇审批服务 403，Active 状态尚未重新核验；新 DNSSEC 仍未配置。

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
- “更新自动跟进提示”及“刷新 Cloudflare 页面”分别遇自动审批服务 403（review could not be completed），均未执行；没有改写 automation.toml、换入口绕过审批或再次提交 NS。既有 `notavue-dns` 每 5 分钟跟进保持原配置，并按本文件的最新状态接续。独立 NS 文档审查 Agent 也因模型服务 403 失败，本次改由主 Agent 自审，不宣称独立复审通过。
- 用户另行确认每 5 分钟在当前聊天只读复查并续接；已创建临时 heartbeat `notavue-dns`，状态 ACTIVE。外部写入仍需现场确认，状态不变保持静默；迁移受测完成或用户要求停止时关闭该跟进。须保持电脑与 Codex 应用运行，不能保证睡眠或关闭应用时执行。

## 下一步条件

1. 已记录四个父区均撤下 DS 32322 的首次确认时刻 03:53:28 UTC。后续若重新发现旧 DS，不使用原起算点跳过检查；不能从按钮点击或任意前置查询时刻起固定等一小时。
2. 自上述时刻起至少等待实测旧 DS TTL 3600 秒，即 04:53:28 UTC 后，并复核父区、公共 DS/A；普通解析应为 NOERROR，而非用关闭验证获得成功。不声称所有全球缓存均已检查。
3. 已经用户确认并保存目标 NS，不重复提交或重复请求同一授权。继续核对四个父区/公共委派、新权威完整记录、Cloudflare Active 及 A 的实际地址答案；旧区 NODATA 的负缓存也需退出。
4. 新 NS 起算点已记录为 05:14:27 UTC；至少等待旧父区委派 TTL 3600 秒，即 06:14:27 UTC 后，结合旧 apex NS/公共缓存查询再判断。若发现更长的旧 NS TTL，按更长值处理；旧权威查询超时不能视为其 TTL 已退出。核对 Cloudflare Active 和新权威记录后，条件满足再启用 Cloudflare 新 DNSSEC、取得匹配新 DS，在注册商登记并复验两家公共 NOERROR + AD。
5. 新 DS 加入期间，负缓存未退出的查询可能暂不带 AD，不能误报全部 DNSSEC 验证链完成；父区/Cloudflare DNSKEY/公共验签一致后才标记受测迁移完成。

## 验证与边界

DNS 查询使用 `dig`，针对父区 DS/NS、新旧权威 A/DNSKEY、公共 DS/A；网络权限放行仅用于公开只读查询。Chrome 扩展连接报告 auth token 不可用，控制台实际采用 cua_repl 的原生 Chrome 窗口，不读取 Cookie、网络响应或绕过审批。

此前故障恢复和支持结论见 [恢复记录](2026-10-13-dnssec-recovery.md)，支持编号 `SPS-YGU-3557`；邮件记录见 [DNS 准备记录](2026-10-12-resend-dns-preparation.md)。本轮未运行无关产品测试，也未把 DNS 迁移当 Resend Verified、邮件送达、生产 TLS 或上线验收。

本轮通过 agent-reach 代理读取超时后直接获取 Cloudflare 官方 DNSSEC Markdown，核对移除 DS、等待旧 DS TTL、切 NS、等待旧 NS TTL、启用新签名及匹配 DS 的顺序。OpenAI Docs 技能通过官方搜索结果读取 [Scheduled tasks](https://learn.chatgpt.com/docs/automations?surface=app)，确认当前聊天的分钟间隔跟进、权限与本机运行边界；早先终端官方页面返回 Forbidden，未将其当正文读取成功。

独立文档审查首轮只读检查本批维护记录、邮件准备与计划，未确认范围内 P0–P2；指出邮件总览的恢复历史仍写成当前状态的 P3，主 Agent 已修正并自检。复审委派未成功收到任务正文，不能将最终更新冒充已独立复审。首轮审查核对 22 个本地链接及差异检查，未独立查询 DNS/操作控制台；本轮外部状态证据由主 Agent 实测提供。
