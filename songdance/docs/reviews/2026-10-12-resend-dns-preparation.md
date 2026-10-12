# notavue.io 发信 DNS 准备

日期：2026-10-12。用户明确采用 `notavue.io` 与 Cloudflare 免费 DNS，分别确认创建 Resend/Cloudflare 资源和“只准备 Cloudflare 记录”。本轮没有切换域名服务器、删除旧 DNSSEC DS、发送邮件、创建密钥、启用客服转发或部署应用。

## 已创建资源

- Resend 发信域名：`mail.notavue.io`，ID `fa9b857c-d315-4a35-93d9-5e885488fc6d`，Ireland（eu-west-1），收信关闭。域名创建不等于 Verified，未点选“已添加记录”冒充公共 DNS 已生效。
- Cloudflare：`notavue.io` Free，状态 Pending。自动扫描导入两条原 A，用户确认后改为 DNS only，IP 未改；附加 robots.txt 偏好同步关闭。
- 分配的新域名服务器：`gannon.ns.cloudflare.com`、`romina.ns.cloudflare.com`。公开 NS 仍为 `launch1.spaceship.net`、`launch2.spaceship.net`；未点选“已更新域名服务器”。

## 保存的实际记录

Cloudflare 记录表共六条，TTL 为 Auto；以下名称相对 `notavue.io`。CNAME 和两条 A 均为 DNS only，TXT 不经过代理。

| 名称 | 类型 | 内容 |
|---|---|---|
| `@` | A | `34.216.117.25` |
| `@` | A | `54.149.79.189` |
| `resend._domainkey.mail` | TXT | 下列实际 DKIM 公钥 |
| `rsend.mail` | CNAME | `rsend-euw1.forge.rmta.net` |
| `send.mail` | CNAME | `send.forge.rmta.net` |
| `_dmarc.mail` | TXT | `v=DMARC1; p=none;` |

DKIM 内容为公开 DNS 公钥，不是 API key 或私钥：

```text
p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCldVyQJ/jX9JSomk69lAjabTSKpmNFcuio5B9AY4G3uqDF2hAHvzw30AKvGzwEIWZ1FwNeAuOgHCdyGNfoIFa7QcXVC3qwG8r4x86kl7hnsbMKbEFUG6dKeKlfEJZydj1zI08SOYANaJh8aBO4u4jFgJ3eEt41E0J7FzCl2/sTmwIDAQAB
```

实际 Resend 账户 SPF/Return-Path 区域生成两条 CNAME，未额外添加旧文档示例中的 MX/SPF TXT。DMARC 限定在 `_dmarc.mail.notavue.io`，未配置根域 DMARC；`p=none` 暂不强制隔离/拒收，也未添加未验证的 `rua` 报告邮箱，不声称已有报告监控。

## 实际验证

全部外部操作使用浏览器可见控制台。重新读取 Cloudflare 记录表，核对六条内容、DNS only 与 Pending。另用 `dig` 只读查询：

- 查询 `@gannon.ns.cloudflare.com` 下的 DKIM TXT、两条 CNAME、DMARC TXT：均返回 `NOERROR`、`aa`，值与 Resend/本次表单一致。
- 查询同一服务器的 `notavue.io A`：返回原两个 IP，TTL 300。
- 查询 `@1.1.1.1 notavue.io NS`：仍返回两个 Spaceship NS。
- 查询 `@1.1.1.1 notavue.io DS`：旧 DS 仍存在，key tag 64580、算法 13、摘要类型 2，TTL 3600。
- 前置查询根域 MX/TXT/AAAA/CAA 无答案，`www` CNAME 与根域 `_dmarc` 为 NXDOMAIN。这些是有限名字查询，不是完整 DNS 区导出；Cloudflare 快速扫描也不能证明所有旧子域都已导入。

沙箱首次阻止 `dig` socket 与 `curl` 网络读取；获准仅网络只读后，以上 DNS 查询退出 0。agent-reach 网页代理超时后直接读取 Resend 官方 `https://resend.com/docs/knowledge-base/cloudflare.md` 成功；Cloudflare DNSSEC 迁移网页两次解析失败/超时，未取得正文。控制台明确提示迁移前确保旧 DNSSEC 关闭，未据此擅自关闭。

查询 Cloudflare 新服务器成功只证明区域已准备，不能证明委派已迁移、DNSSEC 对齐、Resend Verified、SPF/DKIM/DMARC 的真实邮件认证或三家邮箱送达。未运行无关代码/音乐测试，未勾选 MAIL-01 或生产验收。

独立 `code-reviewer` 只读核对本批记录映射、需求/授权边界与 DNSSEC 后续条件，未发现 P0–P2；指出计划里一条当前待办仍写“未修改 DNS”，本轮已改为区域已准备/委派未迁移。审查的 15 个本地链接、DKIM 公钥解析和差异检查通过；审查者未重新操作控制台、独立联网查询或读取真实凭据，外部状态依据上述实际主 Agent 证据。

## 下一步与回退边界

1. 在 Spaceship 核对/备份完整旧 DNS 清单、DNSSEC 设置和 DS，补齐自动扫描遗漏的记录。当前两条 A 不是网站部署验收，迁移不把它们换成未验证的应用地址。
2. 经具体确认后按 DNSSEC 迁移流程处理旧签名/DS，等待父区和验证解析器不再使用旧 DS，再将 NS 改为本次分配的 Cloudflare 两个值；不能带着旧 DS 直接切 NS，也不能只凭过去固定等待时间认定传播完成。
3. 核对父区/公开 NS、解析状态和保留的记录，再在 Cloudflare 启用新 DNSSEC、将匹配的新 DS 配回注册商并复验。不得把旧 DS 直接复制到新区域，回退时同样核对实际签名/DS 对应关系。
4. 公共邮件 DNS 生效后触发并确认 Resend Verified，复核关闭邮件跟踪；准备最小发信 key、签名 Hook/API 与退信投诉回调。
5. `support@notavue.io` 仍需真实收信服务/转发及目标邮箱，配置完成并测试后才显示为客服地址。Gmail/Outlook/Yahoo 投递、回复、8 位登录和过期/复用仍未测试。

本轮保留旧 NS/DS，现有权威解析未被更换；只准备新区域可恢复的记录。后续迁移或权限/安全设置变更须在可审查的具体操作前确认，密钥不进入聊天、仓库或普通日志。
