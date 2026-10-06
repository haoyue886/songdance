# 商业页面与用量展示

日期：2026-10-06，基线 `7e03473`。本批完成默认关闭的本地商业 UI 与相关 API 合同，未开放真实收费。

## 实现

- `/pricing`、`/account`、`/billing/return`、`/refund`、`/contact` 接入套餐配置和身份；中英文实际翻译，另六种语言商业文案明确英文回退，99 个 billing key/占位参数对齐。
- `/billing/config` 的价格、额度、时长、保存期由 API 提供，并与创建 checkout 共用 Test 套餐常量。当前 Pro 单次实际仍为 90 秒；未承诺 5/10 分钟或不同质量模型。默认未开启模式明确显示提案与不可购买。
- 账户展示当前计划、预占/消费/剩余、带时区的周期结束时间与 Portal；用量读取失败或 owner 变化清空旧信息。购买/Portal 先用同一短期 JWT 查 `/me` 核对 owner，再发写请求。Browser 不传 product/customer/余额，不持久保存身份凭据。
- 支付回跳仅看服务端状态，URL 不授额，自动等待最多 60 秒；未知/超时状态提供刷新/支持，不自动再创建付款。pending/uncertain 保留对应幂等键，终态仅清除匹配账号与 checkout key；旧响应不清除新意图。
- 上传前显示 Free 次数或 Pro 秒数预估、实际单次上限及 MIDI/其他格式部分失败规则；余额不足/冻结/状态未就绪禁止提交。选区没有因为刷新自动截短，提交错误保留本地文件/选区并刷新用量。游客文字仅说明当前执行的时长，成功体验次数/IP 日额仍待实现。
- 新多语言路由与登录回跳白名单同步；公开商业页面加入 sitemap，account/login/return noindex。顶部摘要在付款确认/账户刷新后同步更新。新增联系人配置 `SONGDANCE_SUPPORT_EMAIL`，未配置时明确显示不可联系，不造客服入口。隐私/限流事实文字同步账户、用量及 Test 账务记录独立保留。

## 实际验证

Web 目录执行 `pnpm lint`、`pnpm typecheck`、`pnpm test`：38 个文件、217 个测试通过。范围包括 API key 生命周期/URL 校验、60 秒轮询、无凭证与身份变化、失败清空旧余额、八语言参数、路由和上传旧流程。默认 `pnpm build`（Turbopack）最终成功，93 个页面；使用独立 dist/tsconfig，首次沙箱拒绝其本地监听，经受控权限重跑成功。

API 在仓库根运行：

```text
songdance/api/.venv/bin/pytest -q songdance/api/tests/test_billing_ui_contract.py songdance/api/tests/test_creem_billing.py songdance/api/tests/test_creem_failures.py songdance/api/tests/test_entitlements.py songdance/api/tests/test_settings.py
```

90 passed，5 条既有依赖弃用警告，19.81 秒。覆盖公共配置与 checkout 同值、旧期不冒充新 checkout 确认、邮件注入拒绝及既有计费/用量行为。专项 Ruff、编译、`git diff --check` 通过。

`pnpm test:billing:ui` 对真实 Next 页面和本地 Auth/Billing/Hosted Creem 协议替身运行 11 组浏览器检查通过，API 86 次、checkout 4 次、Portal 1 次、外部请求 0 次。覆盖 8 语言 375px/1280px、HTTP 200、Google/OTP 登录回价格页、pending→confirmed、伪造回跳、超时/未知恢复、幂等键、账户隔离、Pro 耗尽、Portal、刷新和关闭状态。截图 `web/test-results/songdance-billing-ui-7wvKvV`（37 张，忽略生成文件）；主 Agent 实际查看价格页、账户手机页和付款桌面页，未见溢出/重叠，主按钮白字及顶部 Pro 摘要可读。协议替身的 Portal 跳转不算真实取消成功。

另运行 `pnpm test:auth:ui`：OTP 错误/成功、HttpOnly/无 refresh JSON、登出、Google PKCE/locale 与刷新桥接通过；截图 `test-results/songdance-auth-ui-CgVbry`。测试独占进程/端口/临时输出并已释放。未连接真实 Supabase、Google、SMTP 或 Creem。

独立 code-reviewer 修复后定向 Web 83、政策/SEO 15、API 39 通过；无遗留 P1/P2。已关闭旧余额、终态 key 阻止重订、跨标签身份混淆和未知付款错误文案问题；另保留 P3：直接进入六种语言隐私/条款页的英文法律回退声明仍可完善。

## 交付边界

38.4 与 BA-15/17 仍未整体勾选：账户周期成功/失败任务摘要、真实购买→提交→导出→取消、客服有效性与运营/适用法律、退款先停止续费、完整供应商/Live 验收仍待完成。长音频、音乐人工质量、游客成功账本、可靠 outbox/提交幂等和全历史对账保留既有门禁，本批不重跑或改写旧音乐指纹。

本地只读页面预览在 `http://127.0.0.1:3001/pricing`，API 在 8010；认证/收费开关关闭，独立临时库/存储 `/private/tmp/songdance-commercial-preview.vmItPI`。原 3000/8000 服务未改动，当前预览任务队列未连接。这不是部署或可真实付费环境。未推送或创建远端产品。
