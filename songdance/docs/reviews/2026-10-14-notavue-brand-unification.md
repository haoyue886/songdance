# 2026-10-14 Notavue 对外品牌统一

用户确认将 SongDance 的对外品牌改为 Notavue，并在 Google 登录、Creem Test 实测前完成应用内统一。本批次已完成本地代码、当前文档、实际页面与导出验证；Google/Creem 外部展示名仍排在各自真实联调阶段。

## 已实施

- 品牌组件和无障碍标签、八语言文案、页面标题、SEO/Open Graph/结构化数据及 404 使用 Notavue。
- 登录、账户、套餐、隐私、条款、退款和客服文案及邮件咨询主题使用新名。
- 验证码 subject、HTML 和纯文本使用 Notavue；发信地址继续为 auth@mail.notavue.io，客服继续为 support@notavue.io。
- 新下载文件名前缀为 notavue-；PDF 标题为 Notavue Piano Transcription、Creator 为 Notavue。MusicXML 保留上传文件名作为谱面标题，缺失/空名时回退 Notavue Transcription。
- 当前 Product-Spec、Billing-Auth-Spec、README、认证与部署说明已同步；开发计划区分应用改名完成与外部展示名待办。

## 兼容边界

工程目录、包/服务机器标识、SONGDANCE_ 配置、Cookie/localStorage、前端事件、Redis/队列、数据库角色/schema、邮件 tag/幂等键、供应商 ID 保持原值。历史审查记录、评审包、固定集和冻结示例未重写。原用户文件名和第三方软件署名保留，未修改音符处理逻辑或质量门槛。

本轮没有改私密配置、启用真实发信、修改 Google/Creem 控制台、提交、推送或部署。上轮真实 OTP 证据仍对应当时品牌；本轮邮件新名验证为合成模板预览，不冒充新的真实收件证据。

## 实际验证

在 `songdance/web` 执行：

```sh
pnpm lint
pnpm typecheck
pnpm test
NEXT_TELEMETRY_DISABLED=1 NEXT_PUBLIC_AUTH_ENABLED=false SONGDANCE_AUTH_ENABLED=false NEXT_PUBLIC_SITE_URL=https://notavue.io SONGDANCE_NEXT_DIST_DIR=.next/notavue-brand-build-20261014 SONGDANCE_TSCONFIG_PATH=.next/notavue-brand-config/tsconfig.json pnpm build --webpack
PLAYWRIGHT_WEB_PORT=3003 PLAYWRIGHT_INFRASTRUCTURE_TIMEOUT=120000 NEXT_PUBLIC_AUTH_ENABLED=false SONGDANCE_AUTH_ENABLED=false pnpm exec playwright test e2e/result.spec.ts e2e/i18n.spec.ts --grep 'renders, plays|serves the additional|keeps shared public'
```

- lint、类型检查和 Webpack 生产构建通过，93 个页面生成完成。
- Vitest：41 个文件、313 项通过。
- 浏览器回归：3 项通过，包含新增语言页面、18 条公共路径的 375px/1440px 布局与实际上传→转录→播放/转调→MIDI/MusicXML/PDF 导出→删除测试任务。
- 主 Agent 查看了桌面/移动端首页截图与实际 PDF 渲染，Notavue 名称清晰、没有横向溢出；PDF 为可读 A4 单页，`pdfinfo` 实际显示 Title=Notavue Piano Transcription、Creator=Notavue。
- E2E 的数据库、存储、构建与队列命名空间隔离；测试自行结束服务。测试后执行 `pnpm exec next typegen` 恢复默认生成类型引用，避免 next-env 继续指向已清理的临时 E2E 目录。

首次 `pnpm lint` 扫到了上轮遗留的 `web/dist/auth-mail-test-20261014` 生成代码，报 520 errors / 5788 warnings。将该已停止服务的构建缓存完整归档到系统临时目录后，按原命令重跑通过；此次新构建使用默认被忽略的 `.next/` 子目录。

在 `songdance/api` 执行：

```sh
.venv/bin/pytest tests/test_mail.py tests/test_mail_hook_listener.py tests/test_score_titles.py tests/test_health.py tests/test_settings.py -q --tb=short
.venv/bin/ruff check app/settings.py app/mail_hook.py app/jobs/cleanup.py app/jobs/account_deletion.py app/pipeline/score.py app/services/mail_contract.py app/services/transcription_source.py tests/test_score_titles.py
```

结果为 118 passed，Ruff 通过。保留 5 条依赖弃用警告。标题测试实际生成 MusicXML，覆盖原文件名、旧任务缺文件名和扩展名空标题；health 的原机器服务标识继续通过兼容断言。

直接调用 `otp_message` 生成合成邮件，断言 subject/html/text 含 Notavue、无 SongDance，关联 tag 仍为 songdance_delivery。通过仅本机 8029 的临时页面查看了 HTML/纯文本排版与固定链接，未调用供应商；预览页与服务随后关闭。

## 独立审查

fresh code-reviewer 在本批次品牌范围内未发现可行动问题；独立 API 85 项、Web 17 项定向检查通过，与主 Agent 用例重叠，不合计数量。其具体边界、命令和未覆盖项见 [独立审查原文](2026-10-14-notavue-brand-review.md)。

主 Agent 另以改名前工作区快照检查增量，保留前序邮件和只读会话接入改动；没有将这些已有修改当成本轮品牌变更重新覆盖。

## 后续

下一步是以 Notavue 名称接入并验证 Google 同意屏幕/登录，再进行 Creem Test 的产品/结账展示名、付款、额度、转谱导出、取消与退款实测。当前目录和外部资源的旧内部名称符合兼容边界，不需要为此次品牌统一迁移数据库或重新做 DNS 验证。生产配置、完整邮件认证头/送达、法律、容量和专业音乐质量验收仍按既有计划推进。
