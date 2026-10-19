# 2026-10-14 Google OAuth 真实联调

**指定测试环境的 Google → Supabase PKCE → Next.js BFF → FastAPI 验签/会话查询 → 账户页 → 退出撤销闭环已通过。** 本轮完成 Google Cloud/OAuth 配置与真实浏览器验证，本机测试服务已关闭；Google provider 和测试客户端保留供后续 Creem Test 使用。

## 实际配置

| 项目 | 已保存的配置 |
|---|---|
| Google Cloud | Notavue Auth Test；project ID `notavue-auth-test`；No organization |
| OAuth 应用 | Notavue；External / Testing |
| 支持/开发联系 | Google 支持邮箱为当前已验证 Google 账户；开发通知为 hello@notavue.io |
| 测试用户 | 当前测试 Google 账户，测试用户表仅 1 行 |
| Data Access | openid、userinfo.email、userinfo.profile，共三项非敏感身份 scope；敏感和受限 scope 表均为空 |
| Web OAuth 客户端 | Notavue Web Test；Web application |
| JavaScript origin | `http://127.0.0.1:3002` |
| 唯一 Google redirect URI | `https://amnsavenqfmmvnauyqzi.supabase.co/auth/v1/callback` |
| Supabase | songdance-test / amnsavenqfmmvnauyqzi；Google provider 已从 Disabled 保存为 Enabled |
| 安全选项 | Skip nonce checks=off；Allow users without an email=off |
| 应用回跳 | `/api/auth/callback`，由现有 BFF 校验 flow、交换 PKCE code，再返回 `/zh/account` |

Client ID/Secret 由 Google 生成，在已授权的界面中受控填写到该 Supabase provider。Secret 未写入本地配置、源码、报告或聊天；保存后已清除临时变量，并将剪贴板替换为普通文字。没有关联计费试用或部署 Google 计算资源。

## 真实验证证据

1. Supabase provider 页面实际显示 `Google ENABLED`；使用已有 publishable key 只读请求 `/auth/v1/settings`，返回 200 且 external.google=true；未回显 key 或完整配置。
2. 本机 API 8002 `/health` 200，Web 3002 `/zh/login` 200，页面显示 Notavue 与 Google 登录按钮。
3. 在正常 Chrome 的实际 Notavue 登录页点击 Google 登录，经过真实 BFF/Supabase，进入 accounts.google.com 的账户选择页。选择已登记的测试 Google 账户并完成授权后，自动回到 `http://127.0.0.1:3002/zh/account`。
4. 主 Agent 通过实际可见页面和截图核对账户页显示该 Google 账户邮箱、Notavue 品牌及退出按钮。该页面由真实 FastAPI JWT 验签和专用会话查询取得账户数据，没有注入协议替身或伪造账户。
5. 通过原 9 字段专用角色读取最近 10 分钟唯一的新会话；TLS in use=true，应用 `SupabaseVerifier.session_active` 在退出前为 true。会话 ID 仅暂存本机 0600 文件，不输出到记录。
6. 点击账户页“退出登录”后，浏览器回到 `/zh/login`；再访问 `/zh/account`，显示“登录已过期，请重新登录”与登录入口。
7. 使用同一个真实 session_id 查询：session_active=false，session row exists=false，`revocation_lookup_passed=true`。脱敏布尔结果保留在 `/tmp/notavue-google-logout-result.json`，临时 ID 文件已删除。

没有导出原 JWT 并对 API 直接重放；本轮撤销证据是同一真实会话的前后状态和真实浏览器退出拒绝。Google 取消授权分支、跨设备/后台撤销、正式 HTTPS Cookie 等完整 BA 条款继续另验，没有整体勾选 BA-02/11/13 或 Phase 38。

## 独立审查

fresh `code-reviewer` 已独立复核 Google/Supabase 配置及现有认证调用链，范围内未发现可行动问题。审查者报告 API 定向测试 47 项、隔离副本 BFF 测试 39 项通过，覆盖 Origin、恶意回跳、OAuth flow 不匹配及退出失败路径。审查者未重新执行真实登录或独立复核 Supabase 回跳白名单；完整结论和验证边界见 [独立审查记录](2026-10-14-google-oauth-review.md)。

## 品牌呈现的实际边界

Google Auth Platform 应用名已保存为 Notavue；实际 Google 账户选择页的目标仍显示 `amnsavenqfmmvnauyqzi.supabase.co`，是当前 Supabase 默认认证域名。Google 品牌审核及正式 Auth 域名/品牌呈现未在本轮完成，不把控制台应用命名等同于公开品牌验证。Creem 产品/结账页名称继续待对应 Test 实测。

## 授权和操作记录

用户在 Google Cloud 首次使用页亲自选择国家/地区并接受条款。自动审批曾拒绝“创建 Google Cloud 项目”，原因是持久外部项目资源未获明确授权；随后用户明确批准创建上述项目/Web 客户端、三项身份权限、受控转存凭据并启用 Supabase Google 测试接入。OAuth 初始化页另要求接受 Google API Services User Data Policy，用户作即时确认后完成初始化。未绕过上述拒绝或代选国家/地区。

## 本地运行与收尾

- 沿用已验证、0600 且受忽略的 `.env.auth-mail-test.local`，专用角色只读取 `songdance_auth` 私有视图的 9 个字段；本轮没有改数据库权限、密码、业务 schema 或认证源码。
- 离线 `scripts.check_auth_config --env-file ../.env.auth-mail-test.local` 实际退出 0；这项检查本身仍只代表格式有效，真实成功依据是上面的浏览器与会话证据。
- 仅本次本机进程开启 AUTH；Web 使用 `.next/notavue-google-test-20261014` 与独立 TS config，API 使用原隔离测试 SQLite/存储。Web 进程不接收数据库 DSN，邮件、收费、用量及账户删除功能继续关闭。
- OAuth callback query 可能含一次性 code；本次 Web 开发进程输出丢弃，浏览器观察输出隐藏 URL query。未主动将 code、state、flow 或完整 callback URL 写入请求日志、报告或文件；浏览器本身的导航历史不在这项保证内。API 使用现有可信 CA/代理及安全日志配置。
- 先完成退出并关闭本轮 Chrome 测试标签，再对逐个核对的本任务 3002 Web、8002 API 进程发送 TERM；实际复查 3002/8002/8024/8027 无监听，没有处理其它服务。
- 执行 `NEXT_PUBLIC_AUTH_ENABLED=false SONGDANCE_AUTH_ENABLED=false pnpm exec next typegen`，退出 0，恢复标准生成类型引用。本轮没有新增代码逻辑，不重复运行上一批已通过的全量代码回归。
- Google project、OAuth client、Testing 受众与 Supabase Google provider 配置保留；本机私密文件的默认开关继续 false。没有提交、推送、正式部署或启用付费服务。
- 归档收尾检查：`git diff --check` 退出 0；本地脚本核对 5 份相关文档的 21 个本地链接，缺失 0。只输出文件模式/布尔结果的配置检查确认两份私密文件均为 0600、被 Git 忽略，现有 9 个功能开关全部关闭；`lsof -nP -iTCP:3002 -iTCP:8002 -iTCP:8024 -iTCP:8027 -sTCP:LISTEN` 无输出（退出 1，即无监听）。浏览器自动化内存会话已重置。

## 下一步

后续 Creem Test 一笔付款、额度到账、转谱与导出、取消及退款已完成，见 [Creem 联调记录](2026-10-14-creem-test-integration.md)。该批为兼容 Creem 的返回 URL 校验，按用户授权将 Supabase Site URL 改为 localhost:3002，并增加 localhost 的精确 callback；本记录上文是 Google 批次当时的 127.0.0.1 事实。Google 品牌/生产配置、完整 MAIL/BA、法律政策、容量和专业音乐质量门槛保留在既有发布计划。

官方依据：https://supabase.com/docs/guides/auth/social-login/auth-google （经 agent-reach 网页读取路径核对）。
