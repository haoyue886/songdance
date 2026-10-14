# Notavue 品牌改名独立审查

结论：在本次范围内未发现可行动问题；没有确认的 P0–P3 findings。

## 范围与依据

2026-10-14，按当前工作区品牌替换 diff、Product-Spec.md:15 和 DEV-PLAN.md Phase 38 的品牌统一增量审查。覆盖品牌组件、八语言消息、布局/页面标题与 SEO、客服主题、邮件主题和 HTML/纯文本、新导出下载文件名/PDF 署名/MusicXML 回退标题及直接调用者。认证私有视图、邮件 listener 和供应商 URL 逻辑不是本次品牌审查的功能范围。派发正文为空，已向主 Agent 说明本次边界；边界从任务名与当前需求记录推断。

## 已核对

- 8 套语言消息解析后与 HEAD 比较，所有变更严格等于 SongDance→Notavue，键与参数结构保持一致。
- 用户可见源代码旧品牌检索未发现遗漏。SONGDANCE_ 环境变量、Cookie、存储键、事件名、Redis/队列前缀、邮件 tags/idempotency key 等内部标识保留，符合兼容要求。
- BrandMark、首页/通用布局/404、SITE_NAME/结构化数据调用者已检查。
- ResultWorkspace 的 MIDI/MusicXML/PDF 下载名称改为 notavue-，PDF 调用标题及 creator 使用 Notavue；转录服务从文件名取标题，缺失或扩展名空名回退到 Notavue Transcription。
- 邮件 subject、HTML、纯文本均使用 Notavue，临时合成样例断言通过，songdance_delivery 内部关联 tag 保留。
- 通过 CUA 查看现有 localhost:3000 页面：英语桌面首页、390×844 英语/中文首页、中文联系页，品牌文字、标题与布局可见且正常；未发送邮件、提交任务或修改外部配置。已恢复临时浏览器尺寸并关闭审查 tab。

## 实际验证

1. 在 /private/tmp 运行，PYTHONDONTWRITEBYTECODE=1，pytest 禁用缓存，使用项目 pyproject 配置：
   `/Users/lixinyue/Desktop/project/songDance/songdance/api/.venv/bin/python -m pytest -c /Users/lixinyue/Desktop/project/songDance/songdance/api/pyproject.toml -p no:cacheprovider /Users/lixinyue/Desktop/project/songDance/songdance/api/tests/test_score_titles.py /Users/lixinyue/Desktop/project/songDance/songdance/api/tests/test_mail.py -q`
   结果 85 passed，5 个依赖弃用警告。测试使用临时 SQLite/存储和 MockTransport。
2. Web 定向 Vitest：src/i18n/messages.test.ts、src/app/seo-routes.test.tsx、src/components/billing/support-panel.test.tsx、src/components/result/result-workspace.test.tsx，4 文件 17 passed。
   为保持只读，使用 startVitest API、与现有配置相同的 React plugin/jsdom/setup/alias，cache=false、cacheDir=/tmp/notavue-brand-review-vite-cache。此前尝试 --configLoader runner 因原配置 __dirname 不受该模式支持而未启动；这是验证加载方式问题，随后用等价 programmatic 配置成功运行，未改仓库配置。
3. 相关品牌 diff 的 git diff --check 通过。
4. 独立合成 otp_message 调用，断言 subject/html/text 中包含 Notavue、不含 SongDance，关联 tag 仍为 songdance_delivery：通过。

## 未覆盖与限制

- 未运行全量 Web/API/E2E，未在浏览器完成 PDF 实际下载/渲染；只读核对其调用和元数据赋值。MusicXML 文件名/回退路径由 API 测试实际生成验证，但没有专业谱面或听感评审，本次仅文案替换无需推断质量门槛通过。
- 没有验证 Google 同意屏幕、Creem 产品名称、真实 OTP 收件/邮件客户端呈现及线上部署，均按需求留待对应真实联调。
- 联系页的现有本地服务显示“套餐与用量信息暂不可用”，因此客服邮箱链接的真实页面状态未覆盖；该分支代码没有被品牌修改，support-panel 单测的 mailto 新主题断言通过，未将其计为本次引入的缺陷。
- 没有读取私密配置或修改仓库源码/文档，未提交/推送。临时验证文件仅写入 /tmp。
