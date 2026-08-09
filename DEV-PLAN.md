# Development Plan — SongDance AI Music Transcriber

> 本文件记录项目开发阶段、依赖顺序、当前进度和验收标准。
> Product-Spec.md 是需求事实来源；本计划只决定如何实现。
> 当前没有 Design-Brief.md 或设计稿，UI 依据 Product-Spec 的工作台结构与竞品调研中的轻量音乐 SaaS 原则实现，不复制竞品品牌或像素级界面。

## 当前进度

| Phase | 状态 | 说明 |
|---|---|---|
| Phase 1 | 已完成 | 工程骨架与产品外壳；代码审查 Stage 1/2 PASS |
| Phase 2 | 已完成 | 上传、波形和截取；代码审查 Stage 1/2 PASS |
| Phase 3 | 已完成 | 任务 API、存储和队列 |
| Phase 4 | 已完成 | AI 转录与乐谱产物；真人质量门禁 10/10；代码审查 Stage 1/2 PASS |
| Phase 5 | 已完成 | 结果工作台与导出；代码审查 Stage 1/2 PASS |
| Phase 6 | 已完成 | 匿名安全、生命周期和可观测性；代码审查 Stage 1/2 PASS |
| Phase 7 | 已完成 | YouTube P1、公共领域示例与临时分享；代码审查 Stage 1/2 PASS |
| Phase 8 | 已完成 | Vercel 部署配置与生产验收手册；代码审查 Stage 1/2 PASS |
| Phase 9 | 进行中 | 转录召回率修复、阈值版本化与乐谱默认规则透明化 |
| Phase 10 | 已完成 | Canvas 下落式钢琴卷帘与键盘同步；单测、构建、示例 E2E 与桌面/窄屏验收通过 |
| Phase 11 | 已完成 | 转录质量评测契约与原始/清洗产物追踪；失败基线已固化，人工门禁 4/10 未通过，进入 Phase 12/15 改进 |
| Phase 12 | 暂缓（许可阻塞） | 三个专用钢琴候选均未通过生产许可前置审计；继续使用 Basic Pitch，保留门禁与审计记录，不阻塞 Phase 13 |
| Phase 13 | 已完成 | 音符清洗 v3；自动召回差值 0.0；人工门禁 7/10；代码审查 Stage 1/2 PASS |
| Phase 14 | 已完成 | 结构分析 v2；16 段回归门禁通过；代码审查 Stage 1/2 PASS |
| Phase 15 | 已完成 | 和弦、多声部与左右手谱面重建；结构与解析门禁 16/16，人工可读 13/16，代码审查 Stage 1/2 PASS |
| Phase 16 | 已完成 | 五线谱质量展示、产物版本、结果页降级与 OSMD 小节交互；代码审查 Stage 1/2 PASS |
| Phase 17 | 计划中 | 多乐器领域模型、乐器选择与向后兼容 API |
| Phase 18 | 计划中 | 贝斯、弦乐、管乐和人声旋律单音家族 |
| Phase 19 | 计划中 | 吉他复音转录与标准记谱 |
| Phase 20 | 计划中 | 鼓转录、General MIDI 与打击乐谱 |
| Phase 21 | 计划中 | 完整混音分轨与直接多乐器 AMT 技术门禁 |
| Phase 22 | 计划中 | 多轨结果工作台、部分成功与生命周期 |
| Phase 23 | 已完成 | 固定乐谱工作台、精准谱面定位、跨系统区间选择与共享播放边界；代码审查 Stage 1/2 PASS |

## 功能依赖图

```text
工程骨架
  ├─ 上传与波形截取
  └─ 任务 API + 数据库 + 对象存储 + 队列
          └─ 音频预处理 + AI 转录 + MusicXML 产物
                  └─ 五线谱/钢琴卷帘工作台 + MIDI/MusicXML/PDF 导出
                          ├─ 匿名限流 + 删除 + 日志 + 埋点
                          └─ YouTube P1 + 示例音频
                          └─ 公网部署 + 生产端到端验收

Phase 9 基线
  └─ Phase 11 质量评测契约
          ├─ Phase 12 专用钢琴模型 A/B（许可合格候选出现后恢复）
          └─ Phase 13 音符清洗
                  └─ Phase 14 Beat / 调性 / 拍号与量化
                          └─ Phase 15 和弦 / 多声部 / 左右手
                                  └─ Phase 16 五线谱质量展示与产物版本
                                          └─ Phase 17 多乐器领域模型与路由
                                                  └─ Phase 18 单音家族
                                                          └─ Phase 19 吉他
                                                                  └─ Phase 20 鼓
                                                                          └─ Phase 21 混音技术门禁
                                                                                  └─ Phase 22 多轨产品化
```

依赖原则：Phase 2 和 Phase 3 都依赖 Phase 1，可并行开发但不能同时修改共享配置；Phase 4 依赖 Phase 3；Phase 5 依赖 Phase 2 和 Phase 4；Phase 6–8 依次收紧生产能力。Phase 13–16 按顺序消费 Phase 11 的质量基线；Phase 12 是许可合格候选出现后才恢复的并行模型门禁，不阻塞确定性后处理。Phase 17–20 按“共享领域模型 → 单音家族 → 吉他 → 鼓”顺序扩展单乐器能力；每个乐器独立过门禁。Phase 21 只有在 Phase 18–20 具备可复用单乐器路由后才评估完整混音，Phase 22 只消费 Phase 21 已批准的轨道来源，不在 UI 层猜乐器。

---

## Phase 1：工程骨架与公开产品外壳

**目标：** 建立能独立编译、测试和容器化的前后端工程，用户能打开完整首页并理解产品价值与限制。

**交付内容：**

- 搭建 Next.js Web、FastAPI API/Worker 和 Docker Compose 本地环境。
- 实现首页、导航、产品说明、隐私保存期限和版权提示。
- 建立共享视觉变量、响应式布局、错误边界和基础无障碍结构。
- 配置前后端单元测试、类型检查、lint 和环境变量校验。

**关键文件：**

- `songdance/web/src/app/page.tsx` — 首页入口与上传区外壳。
- `songdance/web/src/app/layout.tsx` — 全局布局、元数据和字体。
- `songdance/web/src/app/globals.css` — 设计变量、基础排版和响应式规则。
- `songdance/web/src/components/site-header.tsx` — 产品导航。
- `songdance/web/src/components/hero-transcriber.tsx` — 首屏核心操作容器。
- `songdance/api/app/main.py` — FastAPI 应用入口与健康检查。
- `songdance/api/app/settings.py` — 类型化环境变量和运行模式。
- `songdance/docker-compose.yml` — Web、API、Worker、PostgreSQL、Redis 和本地对象存储编排。

**验收标准：**

- Web 与 API 能在本地启动，首页和 `/health` 可访问。
- Web 通过 TypeScript、lint 和单元测试；API 通过 pytest 和静态检查。
- 375 px 与桌面宽度无页面级横向滚动。
- 首页明确标注“仅支持钢琴”“最长 90 秒”“文件 24 小时删除”。

---

## Phase 2：音频上传、波形预览与片段截取

**目标：** 用户能在浏览器选择合法音频、预听并截取最长 90 秒的片段。

**交付内容：**

- 实现拖放和文件选择，校验 MP3、WAV、M4A、25 MB 上限和可解码性。
- 使用 WaveSurfer.js 显示波形、播放选区并同步开始/结束时间输入。
- 默认选择前 30 秒，限制选区为 1–90 秒。
- 加入版权确认、上传空态、解析加载态和可恢复错误态。

**关键文件：**

- `songdance/web/src/components/audio/audio-dropzone.tsx` — 文件选择和前端校验。
- `songdance/web/src/components/audio/waveform-trimmer.tsx` — 波形、选区与播放。
- `songdance/web/src/components/audio/rights-confirmation.tsx` — 权利确认。
- `songdance/web/src/lib/audio/validation.ts` — 文件类型、大小和时长规则。
- `songdance/web/src/lib/audio/clip.ts` — 选区数据和提交载荷。
- `songdance/web/src/app/transcribe/page.tsx` — 转录提交页面。

**验收标准：**

- 合法音频能显示时长和波形，选区无法超过 90 秒。
- 非法格式、超大文件和不可解码文件不会创建任务。
- 未勾选权利确认时无法提交。
- 组件测试覆盖默认选区、边界值和错误文案。

---

## Phase 3：异步任务 API、数据库、对象存储与队列

**目标：** 用户提交片段后获得可恢复的匿名任务 URL，系统能可靠地排队、查询和删除任务。

**交付内容：**

- 创建 PostgreSQL 数据模型和迁移，保存任务、输入、结果及产物元数据。
- 实现 multipart 上传、服务端 MIME 校验、随机对象键和私有对象存储。
- 使用 Redis Queue 建立 Worker 队列、阶段状态、超时和最多两次重试。
- 实现创建、查询、重试和立即删除 API，使用高熵任务 ID。
- 提供本地 S3 兼容存储适配和生产 S3/Supabase Storage 适配。

**关键文件：**

- `songdance/api/app/models/job.py` — 任务、输入、结果和产物模型。
- `songdance/api/app/migrations/versions/001_create_jobs.py` — 初始数据库结构。
- `songdance/api/app/routes/jobs.py` — 创建、查询、重试和删除接口。
- `songdance/api/app/services/storage.py` — 私有对象存储适配层。
- `songdance/api/app/services/queue.py` — Redis Queue 入队和任务配置。
- `songdance/api/app/worker.py` — Worker 入口和阶段状态更新。
- `songdance/web/src/lib/api/jobs.ts` — 类型化任务 API 客户端。
- `songdance/web/src/app/jobs/[jobId]/page.tsx` — 可刷新恢复的任务页。

**验收标准：**

- 合法片段能创建任务并返回至少 128 bit 随机 ID。
- 刷新任务页不会重新上传或重复执行任务。
- 删除接口会删除数据库记录和所有对象；删除后统一返回不可用状态。
- API 集成测试覆盖创建、查询、非法文件、重试、删除和不存在任务。

---

## Phase 4：音频预处理、AI 钢琴转录与乐谱产物

**目标：** Worker 能把音频片段真实转换成 MIDI、MusicXML 和前端预览数据，并输出可诊断的失败原因。

**交付内容：**

- 使用 FFmpeg 裁剪、解码、单声道化、重采样和响度规范化。
- 集成 Basic Pitch 0.4.x，生成原始模型 MIDI 和音符事件。
- 使用 music21 完成基础量化、4/4 小节、速度推断和中央 C 基线左右手分配。
- 生成标准 MIDI、MusicXML 和统一 JSON 音符时间轴，逐产物记录成功或失败。
- 建立 10 段固定音频回归集、结果摘要和模型版本追踪。

**关键文件：**

- `songdance/api/app/pipeline/audio.py` — FFmpeg 预处理。
- `songdance/api/app/pipeline/transcribe.py` — Basic Pitch 调用与模型结果转换。
- `songdance/api/app/pipeline/score.py` — 量化、分手和 MusicXML 生成。
- `songdance/api/app/pipeline/artifacts.py` — MIDI、MusicXML、JSON 产物编排。
- `songdance/api/app/pipeline/errors.py` — 结构化错误码。
- `songdance/api/app/services/transcription.py` — 完整阶段管线和状态更新。
- `songdance/api/tests/fixtures/audio/manifest.json` — 固定回归集清单与授权来源。
- `songdance/api/scripts/evaluate_transcription.py` — 批量回归和结果摘要。

**验收标准：**

- 至少一段真实钢琴音频可端到端生成可解析 MIDI 和 MusicXML。
- 无音符、FFmpeg 错误、模型异常和超时返回不同错误码。
- MusicXML 能被 OSMD 加载并显示至少一个小节。
- 固定 10 段回归集至少 7 段达到“直接使用或少量修改可用”；若未达到，Phase 不算完成并记录模型风险。

---

## Phase 5：五线谱、钢琴卷帘工作台与格式导出

**目标：** 用户能判断结果质量、对比原音与 MIDI，并下载可用于后续工作的文件。

**交付内容：**

- 使用 OSMD 渲染 MusicXML 五线谱，使用 Canvas/SVG 实现同步钢琴卷帘。
- 使用 Tone.js 和本地托管的真实钢琴采样播放 MIDI，支持暂停、定位、0.5×–1.5× 变速和循环；采样加载失败时明确提示基础合成音降级。
- 支持整体 ±12 半音预览，并确保预览与下载使用同一偏移。
- 实现 MIDI、MusicXML 下载和基于当前五线谱的客户端 PDF 导出。
- 完成加载、空、部分产物失败、成功、过期和移动端状态。

**关键文件：**

- `songdance/web/src/app/jobs/[jobId]/result-client.tsx` — 结果工作台状态编排。
- `songdance/web/src/components/result/score-viewer.tsx` — OSMD 五线谱。
- `songdance/web/src/components/result/piano-roll.tsx` — 钢琴卷帘与播放位置。
- `songdance/web/src/components/result/transport.tsx` — 播放、速度、循环和转调。
- `songdance/web/src/components/result/artifact-downloads.tsx` — 产物状态和下载。
- `songdance/web/src/lib/midi/player.ts` — Tone.js MIDI 播放。
- `songdance/web/src/lib/export/pdf.ts` — 五线谱 PDF 导出。
- `songdance/web/src/lib/export/transpose.ts` — 统一转调逻辑。

**验收标准：**

- 五线谱和钢琴卷帘使用相同音符时间轴并同步播放位置。
- 速度、循环和转调对播放有效；转调后的下载文件与预览一致。
- 转录演奏默认使用真实钢琴采样，采样加载失败的降级路径有明确提示和自动化测试。
- MIDI、MusicXML、PDF 均通过真实打开或解析验证。
- PDF 至少一页、有标题和完整乐谱主体，无明显裁切。

---

## Phase 6：匿名安全、生命周期、埋点与生产可靠性

**目标：** 公网匿名服务具备最低限度的成本控制、隐私保护和故障定位能力。

**交付内容：**

- 实现每 IP 每小时 3 次、同时最多 1 个运行任务的限流和全局并发熔断。
- 实现 24 小时定时清理、立即删除和短期签名下载 URL。
- 加固 MIME 嗅探、文件名、CORS、请求体大小、命令调用和日志脱敏。
- 记录阶段耗时、模型版本、错误码和不含音频内容的产品事件。
- 增加隐私说明、服务限制、版权确认和错误恢复文案。

**关键文件：**

- `songdance/api/app/middleware/rate_limit.py` — 匿名限流。
- `songdance/api/app/jobs/cleanup.py` — 过期任务清理。
- `songdance/api/app/services/analytics.py` — 隐私安全的产品事件。
- `songdance/api/app/observability.py` — request_id、结构化日志和阶段耗时。
- `songdance/web/src/app/privacy/page.tsx` — 隐私和保存期限说明。
- `songdance/web/src/app/terms/page.tsx` — 使用权利和服务限制。
- `songdance/web/src/lib/analytics/events.ts` — 前端事件名和属性白名单。

**验收标准：**

- 超过限额的用户获得明确 429 和重试时间，不创建新任务。
- 过期清理能删除数据库记录和对象存储文件；立即删除路径通过集成测试。
- 日志、埋点和错误响应不包含原始音频、完整对象键或敏感 URL。
- Worker 崩溃后任务最多重试两次，超过后进入明确失败态。

---

## Phase 7：YouTube P1 与示例体验

**目标：** 在不影响 P0 上传流程的前提下，提供受开关控制的 YouTube 输入和无需上传的示例结果。

**交付内容：**

- 实现只接受 youtube.com/youtu.be 的 URL 校验、权利确认和功能开关。
- 在平台允许时使用 yt-dlp 获取用户指定的最长 90 秒音频，不绕过登录、地区、私密或付费限制。
- 对平台拒绝、不可用和超时统一降级到本地上传。
- 提供至少一个自有或公共领域示例音频及固定结果，展示真实工作台。

**关键文件：**

- `songdance/web/src/components/audio/youtube-input.tsx` — URL 输入和降级提示。
- `songdance/api/app/routes/youtube.py` — URL 校验和任务创建。
- `songdance/api/app/pipeline/youtube.py` — 受限音频获取和错误映射。
- `songdance/web/src/app/examples/page.tsx` — 示例入口。
- `songdance/api/app/fixtures/examples.py` — 示例结果元数据。

**验收标准：**

- 功能开关关闭或 yt-dlp 不可用时，本地上传流程完全不受影响。
- 不支持的域名、私密、地区限制和登录限制不会尝试绕过。
- 成功输入只保存用户选择片段，不长期保存完整视频。
- 示例结果可直接访问并完成播放、切换视图和格式下载。

---

## Phase 8：Vercel 部署交付与生产验收手册

**目标：** 交付可直接部署的 Vercel Web 与容器后端配置、生产环境契约和可执行验收手册；本阶段不代用户创建云资源或产生费用。

**交付内容：**

- 提供 Vercel Web 配置，以及 Railway API、Worker、清理 Cron 的容器部署声明。
- 提供 PostgreSQL、Redis、私有 S3 存储、TLS、CORS、代理信任和密钥的生产环境契约。
- 在本地验证生产镜像、数据库迁移、健康检查、清理任务和全局任务熔断配置。
- 编写用户上线后执行的生产冒烟、文件清理、移动端和固定音频回归清单。
- 编写部署、回滚、故障排查和成本保护说明，不将未执行的线上测试标成通过。

**关键文件：**

- `songdance/web/vercel.json` — Web 部署与安全头。
- `songdance/api/Dockerfile` — API/Worker 生产镜像。
- `songdance/infra/railway.toml` — API 服务部署配置。
- `songdance/infra/railway-worker.toml` — RQ Worker 部署配置。
- `songdance/infra/railway-cleanup.toml` — 15 分钟清理 Cron 配置。
- `songdance/infra/env.production.example` — 生产环境变量契约。
- `songdance/docs/deployment.md` — 部署和回滚步骤。
- `songdance/docs/runbook.md` — 任务积压、模型失败、存储和限流排障。

**验收标准：**

- Vercel 配置能完成 Web 生产构建，容器配置能构建并启动 API、Worker 和单次清理任务。
- 生产环境变量示例不含真实密钥，并覆盖 HTTPS、私有对象、限流、任务恢复、立即删除和 24 小时清理所需配置。
- 部署手册逐步说明 Vercel Web、Railway 后端和私有对象存储的创建、连接、迁移与回滚，不要求读者猜缺失命令。
- 上线后验收清单覆盖匿名上传、MIDI/MusicXML/PDF 下载、任务恢复、立即删除、限流、清理、375 px 和固定 10 段回归集。
- YouTube 默认关闭；每日任务上限和全局并发上限有明确默认值，部署失败不会产生无限资源消耗。
- 实际生产 URL 与线上验收结果由用户部署后填写；当前交付不得伪造为已验证。

**交付证据（2026-08-01）：**

- 代码提交：Phase 1 `e32168a`、Phase 2 `512876d`、Phase 3 `264f882`、Phase 4 `3573f2d`、Phase 5 `e730f3c`、Phase 6 `b92d2ab`、Phase 7 `4d9689e`、Phase 8 `bef6227`。
- 架构：Vercel Web + Railway API/RQ Worker/Cleanup Cron + Railway PostgreSQL/Redis + 私有 S3 兼容存储；生产变量契约见 `infra/env.production.example`。
- 门禁：API Ruff PASS、pytest 93 passed/6 skipped；Web lint/typecheck PASS、Vitest 52/52、Playwright 9/9、Next production build PASS。
- 镜像：API `sha256:fa2bd3485056...e0dd7`，Web `sha256:0c4fbaf26c61...0905`；镜像隐私审计未发现真实 `.env`、密钥、测试文件、`.pyc` 或开发者绝对路径。
- 运行验证：API 生产配置拒绝 `/0` 代理网段；受限代理网段下 Alembic、`tini` PID 1、`/health` 200、YouTube 默认关闭和单次清理循环通过。
- 回滚与排障：执行步骤见 `docs/deployment.md` 和 `docs/runbook.md`；初始上限为全局同时 2 个任务、每日 25 个任务。
- 已知限制：完整开发依赖审计仍报告 ESLint 工具链的 `brace-expansion` High；生产依赖审计为 0，不进入运行镜像。
- 生产 URL：未创建。用户明确要求只交付 Vercel 部署方法，不代为创建云资源；线上端到端和生产 10 段回归必须在用户部署后按清单执行。

---

## Phase 9：转录质量校准与结果可信度

**目标：** 消除当前 Basic Pitch 配置造成的快速复调系统性漏音，并让乐谱默认规则不再被误认为原曲结构识别结果。

**交付内容：**

- 将检测阈值纳入类型化配置，采用 Basic Pitch 默认阈值作为召回基线，并将生效配置写入模型版本。
- 为转录调用补充单元测试，防止高阈值配置再次悄悄进入生产。
- 增加可重复的真实 Bach 样本 A/B 评估，记录原始 MIDI 音符数、阈值与产物可解析性。
- 在结果元数据中标记 4/4 拍号与中央 C 分手为基础排版默认规则，避免将其描述成可靠识别。

**关键文件：**

- `songdance/api/app/settings.py` — 检测阈值与模型版本配置。
- `songdance/api/app/pipeline/transcribe.py` — Basic Pitch 推理与模型版本标识。
- `songdance/api/app/pipeline/score.py` — 乐谱默认规则和质量标记。
- `songdance/api/tests/test_transcribe.py` — 推理参数与模型版本单元测试。
- `songdance/api/tests/test_score.py` — 乐谱默认规则和质量标记测试。
- `songdance/api/scripts/evaluate_transcription.py` — 固定样本 A/B 评估输出。

**验收标准：**

- Bach 基准在召回基线下输出的原始 MIDI 音符数不少于当前确认的 275，且 MIDI、MusicXML 与时间线均可解析。
- 检测阈值来自类型化设置，默认值与 Basic Pitch 0.4.0 的默认参数一致；模型版本包含实际阈值。
- 乐谱质量标记明确包含拍号与手部分配的默认规则，不冒充原曲结构识别。
- API 静态检查、测试与固定真实钢琴集回归均通过；人工质量评审不低于变更前等级。

---

## Phase 10：Canvas 下落式钢琴卷帘

**目标：** 以更接近钢琴演奏的下落式视图替换横向 SVG 网格，同时保持现有转录、播放和定位语义。

**交付内容：**

- 使用 Canvas 2D 绘制纵向下落音符、固定击键线和底部钢琴键盘。
- 将 `TimelineNote` 的音高、起止时间、力度和左右手信息映射为可见音符、键盘高亮和颜色。
- 保持点击相对时间定位、左右方向键定位和转调后时间线同步。
- 支持高 DPI、窗口尺寸变化、移动端窄屏和减少动态效果偏好。

**关键文件：**

- `songdance/web/src/components/result/piano-roll.tsx` — Canvas 容器与交互。
- `songdance/web/src/components/result/piano-roll-canvas.ts` — 下落卷帘布局和绘制。
- `songdance/web/src/components/result/piano-roll-drawing.ts` — Canvas 场景绘制与键盘高亮。
- `songdance/web/src/components/result/piano-roll.test.tsx` — 时间定位、键盘可访问性和画布契约测试。

**验收标准：**

- 视图中显示底部钢琴键盘，播放中的音符在固定击键线处高亮对应琴键。
- 左右手音符有稳定且可区分的颜色；无手部信息时使用中性色。
- 375 px 宽度下画布不产生页面横向滚动，键盘方向键和点击定位保持可用。

---

## Phase 11：转录质量评测契约与产物追踪

**目标：** 先建立可重复的质量证据，再修改清洗和谱面算法；开发 Agent 不得凭单张截图判断改进有效。

**交付内容：**

- 建立至少 16 段的结构回归集，覆盖单音、和弦、快速复调、踏板、左右手交叉、3/4 或 6/8、调性变化和噪声场景，并保存人工校对真值。
- 对每次运行保存模型版本、阈值、依赖版本、原始/清洗音符数、置信度分布、重叠数和结构错误数。
- 固定兼容产物契约：`raw_midi` 保留 Basic Pitch 原始 MIDI；新增 `raw_timeline` 保存原始事件；现有 `midi` 和 `timeline` 继续作为清洗后的默认产物，避免破坏前端与下载 API；MusicXML/PDF 从清洗时间线派生。
- 输出机器指标与人工三级评级报告，并固定可供 Phase 12 消费的基线快照与比较契约；候选模型的实际 A/B、召回和谱面可读性差异结论由 Phase 12 交付。

**关键文件：**

- `songdance/api/app/pipeline/quality.py` — 质量统计、事件摘要和结构错误码。
- `songdance/api/app/pipeline/artifacts.py` — 原始/清洗产物类型和版本关系。
- `songdance/api/app/services/transcription_persistence.py` — 保存质量摘要和后处理版本。
- `songdance/api/app/models/job.py` — 结果质量字段与迁移映射。
- `songdance/api/app/migrations/versions/004_transcription_quality_reports.py` — 新建质量报告表并扩展结果字段，迁移保持旧任务可读。
- `songdance/api/app/schemas/job.py` — 向后兼容地返回质量摘要和产物版本。
- `songdance/api/tests/fixtures/score-quality/manifest.json` — 固定样本、来源、人工真值和评级入口。
- `songdance/api/scripts/evaluate_transcription.py` — 固定回归集报告。
- `songdance/api/tests/test_quality.py` — 指标、版本和产物追踪测试。

**验收标准：**

- 相同音频、模型和配置重复运行，质量摘要和事件排序一致。
- 基线报告包含 precision/recall、起音误差、原始音符数、置信度分布、重叠统计、MusicXML 解析结果和人工评级；缺少真值的样本明确显示 `not_evaluated`，不得伪造 0 分。
- 基线报告带稳定 `evaluation_id`；候选报告缺失时比较状态必须是 `not_evaluated`，不得在 Phase 11 伪造候选改进结论。
- 清洗版失败时原始 MIDI 和时间线仍可下载，数据库不丢失原始证据。
- 旧任务响应和既有 `midi`、`timeline` 下载 URL 保持兼容；迁移升级与降级测试均通过。
- API 静态检查和测试通过，已有 Phase 4/9 回归结果不下降。
- Phase 11 允许基线质量门禁为失败，但必须如实保存并由独立校验命令返回非零；AC-025 的至少 13/16 人工可读最终门禁在 Phase 15 完成结构重建后签收。

---

## Phase 12：专用钢琴转录模型隔离 A/B 与选择门禁

**目标：** 先用生产许可前置门禁排除不可上线的模型，再判断质量差异主要来自 Basic Pitch 的音符候选还是后处理；没有许可合格候选胜出时继续使用 Basic Pitch。

**交付内容：**

- 抽象统一模型适配层，把不同模型输出归一为稳定排序的 `NoteEvent`、原始 MIDI、模型版本、置信度语义和运行指标。
- 在任何 GPU 或人工评测投入前审计候选代码、模型权重和训练数据是否允许目标生产用途；不兼容的候选标为 `research_only`，保留来源与淘汰证据，但不进入固定集 A/B。
- 只在独立容器/依赖环境评估许可先通过的 `piano_transcription_inference`、Omnizart 或其他专用钢琴候选；候选环境不得污染主 Worker 的 `uv.lock`。Aria-AMT 代码固定为 `EleutherAI/aria-amt@a1ab73fc901d1759ec3bc173c146b3c6a3040261`，其 `piano-medium-double-1.0.safetensors` 权重固定为 CC-BY-NC-SA-4.0，仅保留审计镜像和 manifest，不申请 CUDA、不运行固定集或人工盲评。`amt-apc` 只作为自动钢琴改编研究参考，`songscription-catalogue` 只作为 UI 参考。
- 对许可通过的候选在固定 10 段转录集和至少 16 段结构集运行盲评 A/B，记录音符 precision/recall、起音误差、踏板、人工可用率、P95 时延、峰值内存和失败率。
- 生成可审计选择报告并加模型版本开关；只有达到 AC-028 才允许灰度替换，加载或推理失败自动回退 Basic Pitch。

**关键文件：**

- `songdance/api/app/pipeline/model_adapter.py` — 统一模型输入、输出和运行指标契约。
- `songdance/api/app/pipeline/transcribe.py` — Basic Pitch 基线适配与可回滚模型路由。
- `songdance/api/experiments/models/` — 候选模型隔离依赖、固定提交、权重校验和许可记录。
- `songdance/api/experiments/models/aria_amt/` — Aria-AMT 固定 commit、隔离依赖、权重 revision/SHA-256、许可审计和运行说明。
- `songdance/api/experiments/models/manifest.json` — 所有候选（含 Aria-AMT）的代码 commit、权重 revision、校验和、运行环境与审计状态。
- `songdance/api/scripts/evaluate_models.py` — 同一数据集的模型 A/B 与报告生成。
- `songdance/api/tests/test_model_adapter.py` — 事件归一化、稳定排序、开关和回退测试。

**验收标准：**

- 许可审计报告覆盖所有候选，并证明不兼容候选在质量评测投入前已标为 `research_only`；质量报告包含 Basic Pitch 与至少一个生产许可通过的专用钢琴候选，且使用同一音频、真值、事件容差和人工评级方法。
- 候选只有在至少 8/10 片段可用、快速复调关键样本不降级、P95 时延/峰值内存在部署预算内且许可通过时，才可进入灰度；否则明确保留 Basic Pitch。
- 候选关闭或故障时产物与 Phase 9 Basic Pitch 基线一致，主 Worker 不安装未选中的候选依赖或权重。
- API 静态检查、适配器测试、许可合格候选的隔离容器构建与固定集 A/B 均通过；仅研究参考不要求构建推理环境或运行质量 A/B。

---

## Phase 13：音符清洗、去重与可解释合并

**目标：** 把 Basic Pitch 的碎片化候选变成稳定的清洗时间线，同时不牺牲已确认的复调召回基线。

**交付内容：**

- 增加可配置的置信度、最短时长、同起音重复和异常延音规则，所有删除、裁剪和保留动作输出 reason code。
- 只执行不依赖节拍网格的事件级清洗；保留原始起音证据，缺少独立重触键证据时相邻同音只记录候选但不自动合并，节拍量化留给 Phase 14。
- 对同音同起点候选做去重；异常超长延音按配置裁剪；不同起音的延音、短促重复音和重叠事件保留并记录可解释原因。
- 明确 `raw_timeline`、清洗后的 `timeline` 和默认预览的版本关系，提供失败回退。

**关键文件：**

- `songdance/api/app/pipeline/cleanup.py` — 音符清洗与合并规则。
- `songdance/api/app/pipeline/transcribe.py` — 清洗配置和事件接口。
- `songdance/api/app/pipeline/artifacts.py` — 清洗时间线/MIDI 产物。
- `songdance/api/app/settings.py` — 类型化清洗参数。
- `songdance/api/tests/test_cleanup.py` — 去重、合并、边界和回退测试。

**验收标准：**

- 固定回归集的原始音符召回不下降超过 5%，人工可用段数不低于基线。
- 重复事件、极短碎片、合并事件的数量和原因可查询。
- 清洗规则可通过配置复现，禁止在代码中散落魔法阈值。
- 清洗异常只使清洗产物失败，不阻塞原始 MIDI、时间线和钢琴卷帘。

---

## Phase 14：Beat、BPM、调性与拍号分析

**目标：** 用音频结构分析替换“所有结果固定 4/4”的默认路径；低置信度时仍可安全回退。

**交付内容：**

- 将当前由 Basic Pitch 间接锁定的 `librosa` 0.11.0 提升为显式依赖，作为节拍、起音和调性分析基线，生成 beat grid、BPM、调性候选和置信度。
- 对 `madmom`、Essentia 或专用和弦/节拍模型只做隔离的离线对比，不同时引入多个生产依赖；madmom 模型数据和 Essentia AGPL 许可未审计通过前不得进入生产镜像。
- 实现 4/4、3/4、6/8 等候选拍号的选择与回退，记录推断来源和置信度。
- 将结构分析结果传给量化、分小节和 MusicXML 生成，不改变原始时间线。

**关键文件：**

- `songdance/api/app/pipeline/analysis.py` — BPM、beat、调性和拍号适配器。
- `songdance/api/app/pipeline/quantize.py` — 基于 beat grid 的量化接口。
- `songdance/api/app/settings.py` — 分析开关、超时和置信度阈值。
- `songdance/api/pyproject.toml` — 锁定经过兼容性验证的分析依赖。
- `songdance/api/tests/test_analysis.py` — 结构分析和回退测试。
- `songdance/api/scripts/evaluate_structure.py` — 结构回归对比脚本。

**验收标准：**

- 结构回归集保存 BPM 误差、beat 对齐误差、拍号候选和调性置信度。
- 分析服务失败或低置信度时，任务仍可生成明确标注默认拍号的 MIDI/时间线。
- 同一分析版本与配置产生稳定 beat grid；不会静默改变原始事件时间。
- P95 分析耗时不超过 30 秒音频端到端预算中的 15 秒。

**完成记录：**

- 分析版本 `structure-analysis-v2/8d2475ced611`；16 段结构回归集稳定性 `16/16`，P95 `3.467095s`。
- BPM 误差不超过 5 的比例 `0.8125`，中位 BPM 误差 `2.546165`；拍号准确率 `0.9375`，平均 downbeat 误差 `203.95565ms`，门禁通过。
- 分析使用可终止子进程硬超时；失败或低置信度显式回退 4/4 与 C major，原始 MIDI 和 raw timeline 不变。
- API `187 passed, 6 skipped`，Web `62 passed`、typecheck 与生产构建通过；代码审查 Stage 1/2 PASS。

---

## Phase 15：和弦、多声部与左右手谱面重建

**目标：** 解决截图中最严重的重叠、休止符堆叠和错误分手问题，生成真正可读的基础 MusicXML。

**交付内容：**

- 按时间容差和持续时间将同时音符合并为 Chord，保留独立起音的旋律线。
- 使用 voice assignment 将跨越同一拍的旋律、内声和低音分开；同一 voice 内禁止非法重叠。
- 结合音高、连续性、低音线和和弦上下文计算左右手分配与置信度，允许 `unknown`。
- 设置调号、拍号、连音、休止符和小节边界的可读排版策略，避免无意义的临时升降号和碎片休止符。
- 生成结构校验报告，失败时回退到基础 MusicXML，并在质量标记中说明原因。

**关键文件：**

- `songdance/api/app/pipeline/voicing.py` — 多声部与左右手分配。
- `songdance/api/app/pipeline/harmony.py` — 和弦候选和同起音聚合。
- `songdance/api/app/pipeline/score.py` — music21 Part/Voice/Chord 构建。
- `songdance/api/app/pipeline/score_validation.py` — 小节、声部和 MusicXML 结构校验。
- `songdance/api/tests/test_voicing.py` — 和弦、交叉、持续音和未知分手测试。
- `songdance/api/tests/test_score_validation.py` — 非法重叠、时值守恒和回退测试。

**验收标准：**

- 同起音的两到四音事件生成 Chord 或合法多声部，不再全部写入 voice 0。
- 所有成功标记的 MusicXML 通过 music21、OSMD 和至少一个外部解析器验证。
- 至少 16 段的结构回归集中，至少 80%（首版至少 13/16）片段无严重音符重叠、异常休止符或小节时值错误，并被人工评为“谱面可读”。
- 左右手交叉和中央 C 附近音符不会被固定阈值直接判定；低置信度结果明确显示未知或假设。

**完成记录：**

- 同起音和弦、多声部 voice assignment、带置信度的左右手分配与 `unknown` 排版回退已接入生产流水线。
- 16 段结构回归集的结构错误、解析失败和重建回退均为 `0`；music21、OSMD 与 xmllint 全部通过。
- 人工谱面可读性门禁 `13/16`，达到首版最低标准；其余 3 段评为需要重做。
- API `200 passed, 6 skipped`；Web `64 passed`，lint、typecheck 与生产构建通过；代码审查 Stage 1/2 PASS。

---

## Phase 16：五线谱质量展示、产物版本与结果页降级

**目标：** 让用户看懂结果的可信边界，并在谱面失败时仍能使用 MIDI 和钢琴卷帘。

**交付内容：**

- 在结果摘要中显示原始/清洗音符数、清洗动作数、BPM/调性/拍号置信度和质量警告。
- 区分“清洗后预览”“原始 MIDI 下载”和“排版假设”，不把默认 4/4 或中央 C 分手显示为识别结论。
- MusicXML/PDF 失败时保持 MIDI、原始时间线和钢琴卷帘可用；成功时标明产物版本。
- 增加质量摘要空态、低置信度警告、结构校验失败、产物部分成功和移动端布局。
- 基于 OSMD 公开 Cursor、GraphicSheet 和坐标转换 API 增加当前小节高亮、点击小节定位及上一/下一小节控制，不依赖渲染器内部 CSS class。

**关键文件：**

- `songdance/web/src/components/result/result-workspace.tsx` — 质量摘要和产物版本展示。
- `songdance/web/src/components/result/score-viewer.tsx` — MusicXML 错误和质量警告。
- `songdance/web/src/components/result/score-viewer.test.tsx` — 小节高亮、点击定位、导航边界和映射降级测试。
- `songdance/web/src/components/result/artifact-downloads.tsx` — raw/clean 产物状态。
- `songdance/web/src/lib/api/jobs.ts` — 质量摘要类型和 API 客户端。
- `songdance/web/src/lib/result/timeline.ts` — 保留结构分析节拍与下拍网格，提供乐谱时间换算输入。
- `songdance/web/src/app/jobs/[jobId]/result-client.tsx` — 结果数据装配与降级。
- `songdance/web/e2e/quality-result.spec.ts` — 质量摘要、部分失败和窄屏 E2E。
- `songdance/web/e2e/result.spec.ts` — 真实 MusicXML 小节点击、高亮、前后导航和播放同步 E2E。

**验收标准：**

- 用户能在结果页看到质量警告和各项置信度，且默认文案不承诺人工谱面级准确率。
- MusicXML 失败时 MIDI、钢琴卷帘和原始音频播放仍可用。
- 375 px 下质量摘要不造成页面横向滚动，核心播放和下载仍可用。
- E2E 覆盖高质量、低置信度、MusicXML 失败和清洗回退四种状态。
- 播放或拖动跨越小节边界时 OSMD 高亮对应小节；点击小节及上一/下一控制定位到共享时间线中的小节起点，首尾边界正确禁用。
- 小节映射不可用时控制禁用且不影响五线谱、播放和下载；375 px 下导航无页面级横向滚动。

**完成记录：**

- 结果页已接入持久化质量报告，显示原始/清洗音符、清洗动作、BPM/拍号/调性置信度、平均音符置信度及模型/后处理/报告/时间线版本；旧任务或异常报告降级为明确空态。
- 清洗回退会真实读取 `raw_timeline`，并禁用不一致的五线谱、MusicXML 和 PDF；MusicXML 单独失败时钢琴卷帘、原始/清洗 MIDI 与原音保持可用。
- 高质量、低置信度、MusicXML 失败、清洗回退四类 E2E 全部通过，375 px 无横向滚动；真实转录、播放、MIDI/MusicXML/PDF 导出主流程通过。
- OSMD 已接入 CurrentArea 当前小节高亮、共享时间线同步、点击小节定位、前后小节导航和首尾禁用；映射不可用时保留乐谱、播放和下载，导航明确降级。
- Web `21 files / 85 tests`、lint、typecheck、生产构建和 Playwright `14/14` 通过；真实 Cursor 位移、小节点击、合法 MusicXML 映射降级及 375 px 布局均有浏览器级证据。
- 代码审查 Stage 1/2 PASS，`0 HIGH / 0 MEDIUM / 0 LOW`。

---

## Phase 23：固定乐谱工作台、谱面区间选择与播放同步

**目标：** 借鉴 Pianofi 的固定播放器与高亮跟随、Songscription 截图体现的谱面区间选择，将结果页从页面滚动式预览改为固定高度的可操作乐谱工作台，不更换 OSMD 渲染器、不破坏原音与 MIDI 的共享播放时间线。

**交付内容：**

- 增加可版本兼容的乐谱时间映射：优先使用 MusicXML/OSMD 的乐谱时间与现有 beat/downbeat 网格映射到真实秒数；旧任务或映射不一致时明确禁用谱面定位和选区。
- 重构 OSMD 交互：关闭 `followCursor` 自动滚动，使用公开 `GraphicSheet`、`GraphicalMeasure.PositionAndShape`、`tryGetTimeStampFromPosition` 和 `Drawer.calculatePixelDistance` 实现当前小节高亮、点击定位、拖动区间选择、SVG 选区遮罩及用户主动定位。
- 将结果中央预览改为固定高度工作区：播放器固定在工作区顶部，谱面在独立 `overflow` 容器内滚动，375 px 下无页面级横向滚动。
- 扩展播放状态以支持选区边界：原音和转录演奏共享选区起止；一次播放到终点停止，循环开启时回到选区起点；清除选区后恢复整曲播放。

**关键文件：**

- `songdance/web/src/components/result/result-workspace.tsx` — 固定高度工作区、播放器与谱面容器布局。
- `songdance/web/src/components/result/score-viewer.tsx` — OSMD 光标、点击/拖动选区、公开几何 API 绘制覆盖层和主动定位。
- `songdance/web/src/components/result/transport.tsx` — 固定播放器、选区摘要、清除选区与循环状态。
- `songdance/web/src/hooks/use-result-playback.ts` — 选区播放边界、停止/循环和共享播放头。
- `songdance/web/src/lib/result/score-time-map.ts` — 乐谱时间、beat/downbeat 和秒数映射及降级判断。
- `songdance/web/src/lib/result/timeline.ts` — 可选映射字段解析和旧任务兼容。
- `songdance/web/src/components/result/score-viewer.test.tsx` — 点击、拖动、跨系统覆盖层与禁止自动滚动测试。
- `songdance/web/src/hooks/use-result-playback.test.tsx` — 选区播放、终点停止、循环和双播放源一致性测试。
- `songdance/web/e2e/phase7.spec.ts` — 真实 MusicXML 点击定位、区间选择、播放器固定和窄屏回归。

**验收标准：**

- 播放跨越至少 3 个小节时，页面 `window.scrollY` 和谱面 `scrollTop` 都不自动变化；当前小节高亮正确切换。
- 点击谱面可映射位置后，原音、转录演奏和钢琴卷帘定位到同一秒数；播放中继续、暂停时不自动播放。
- 拖动选区跨越同一行和多行谱面时，选区边界、选区外淡化和起止秒数一致。
- 选区播放从起点开始，在终点停止；循环开启时只在选区内循环；清除后整曲播放恢复。
- 播放器在谱面内部滚动前后位置不变；仅用户点击主动定位后才滚动谱面内部容器。
- 375 px 与桌面视口均无页面级横向滚动，播放器控件有可访问名称且不被谱面内容遮挡。
- MusicXML/时间映射失败时，五线谱、播放和下载仍可用，谱面定位与区间选择被禁用并给出明确状态。
- Web 单测、lint、typecheck、生产构建和 Playwright 核心流程全部通过，代码审查 Stage 1/2 PASS。

**依赖与风险：**

- 依赖 Phase 14 的 beat/downbeat 网格、Phase 15 的 MusicXML 重建和 Phase 16 的 OSMD 公共 API 接入。
- 不依赖新数据库表；时间线字段向后兼容，旧任务无法建立映射时降级。
- OSMD 的坐标与渲染缩放、跨系统矩形覆盖层和触摸拖动是主要风险，必须用真实 MusicXML E2E 验证，不以 mock 坐标测试代替。

**完成记录（2026-08-09）：**

- OSMD 已关闭自动滚动跟随；播放器固定在谱面工作区顶部，谱面使用独立 520 px 滚动视口，只有用户主动点击定位按钮才滚动谱面。
- 点击与拖选使用 OSMD 乐谱时间戳；OSMD 小节时间与 downbeat 网格缺失、数量不一致或超出容差时，定位和选区明确禁用，五线谱、播放与下载保持可用。
- 跨系统选区按 `PositionAndShape` 和 Drawer 公共像素换算生成独立 SVG 遮罩；原音与 MIDI 共享选区起止，非循环在终点停止，循环回到选区起点。
- Web `24 files / 103 tests`、Playwright `14/14`、lint、typecheck、生产构建通过；代码审查 Stage 1/2 PASS，`0 HIGH / 0 MEDIUM / 0 LOW`。

---

## Phase 17：多乐器领域模型、乐器选择与兼容 API

**目标：** 在不破坏现有钢琴任务和下载接口的前提下，把单结果钢琴管线升级为按乐器配置、可容纳多轨的稳定领域模型。

**交付内容：**

- 建立版本化 `InstrumentProfile` 注册表，固定乐器 ID、谱表、响音域、移调、复音能力、General MIDI program 和已批准模型路由。
- 扩展任务创建接口，增加 `source_mode=single_instrument|full_mix` 与白名单 `requested_instrument`，单乐器未选择时拒绝提交。
- 新增 `TranscriptionTrack` 与可空 `track_id` 产物/质量报告关系；把旧钢琴结果迁移为单轨兼容视图，保留现有 `midi`、`timeline` 和下载 URL。
- 在上传页增加输入模式和乐器选择器；结果页先按 profile 决定乐谱/时间线类型，不在组件内散落乐器判断。

**关键文件：**

- `songdance/api/app/pipeline/instruments.py` — InstrumentProfile 注册表、白名单和版本。
- `songdance/api/app/models/job.py` — source_mode、requested_instrument 和 TranscriptionTrack 关系。
- `songdance/api/app/migrations/versions/005_multi_instrument_tracks.py` — 新增轨道表和兼容迁移。
- `songdance/api/app/schemas/job.py` — 单轨/多轨兼容响应契约。
- `songdance/api/app/services/transcription.py` — 按乐器 profile 路由已批准模型。
- `songdance/web/src/components/audio/instrument-selector.tsx` — 输入模式和乐器选择。
- `songdance/web/src/lib/api/jobs.ts` — 乐器、轨道和兼容响应类型。

**验收标准：**

- 单乐器任务未选择乐器时前后端都拒绝提交；任意模型名或未知乐器 ID 不能进入 Worker。
- 旧数据库升级后，旧钢琴任务、结果页、`midi`/`timeline` 下载和现有 E2E 保持可用。
- 每条轨道保存 instrument/profile/model/postprocess 版本，且 MIDI 内部统一使用响音高。
- API Ruff、pytest、Web lint/typecheck、组件测试和生产构建通过。

---

## Phase 18：贝斯、弦乐、管乐和人声旋律单音家族

**目标：** 复用统一单音管线，按独立质量门禁上线贝斯、小提琴、长笛、降 B 小号、中音/次中音萨克斯和人声主旋律。

**交付内容：**

- 实现 Basic Pitch 与 librosa pYIN/CREPE 候选的单音适配器，统一 voicing、音高曲线、note segmentation、置信度与失败语义。
- 为六类输入建立独立固定集和 A/B；每个乐器单独决定已批准模型，不允许整组一次性放行。
- 生成正确的低音/高音谱表、响音高 MIDI 和移调 MusicXML；小号与萨克斯验证 concert pitch/written pitch 一致性。
- 将结果页改为通用有音高 note roll；非钢琴结果不显示左右手，人声明确不含歌词。

**关键文件：**

- `songdance/api/app/pipeline/monophonic.py` — 单音音高跟踪与 note segmentation。
- `songdance/api/app/pipeline/model_adapter.py` — Basic Pitch、pYIN/CREPE 输出归一化。
- `songdance/api/app/pipeline/score_profiles.py` — 谱表、移调与 MusicXML instrument metadata。
- `songdance/api/scripts/evaluate_instruments.py` — 逐乐器机器指标、人工评级和资源报告。
- `songdance/web/src/components/result/note-roll.tsx` — 非钢琴有音高时间线。
- `songdance/web/src/components/result/result-workspace.tsx` — 乐器名称、范围警告和产物展示。

**验收标准：**

- 每个显示“已支持”的乐器独立满足至少 10 段、note F1 ≥ 0.70、至少 7/10 人工可用及许可/资源门禁。
- 小号与两类萨克斯的 MIDI 播放为响音高，MusicXML 带正确移调元数据并显示记谱音高。
- 人声结果只有主旋律 MIDI/谱面；和声、说唱或低置信度片段显示范围警告，不出现歌词占位。
- 钢琴固定集、双手谱面、钢琴卷帘和旧 API 回归不下降。

---

## Phase 19：吉他复音转录与标准记谱

**目标：** 支持独奏吉他的复音 MIDI 与标准五线谱，同时明确不生成没有弦位推断依据的 TAB。

**交付内容：**

- 对 Basic Pitch 与通过许可审计的复音吉他候选做固定集 A/B，覆盖单音、和弦、扫弦、延音、推弦和噪声。
- 增加吉他音域、八度移调、和弦聚合与奏法不确定性质量标记，不伪造弦号、把位或指法。
- 在结果页使用通用 note roll、标准记谱和明确的“暂不提供 TAB/Guitar Pro”输出边界。

**关键文件：**

- `songdance/api/app/pipeline/guitar.py` — 吉他事件清洗、和弦与质量标记。
- `songdance/api/app/pipeline/score_profiles.py` — 吉他八度移调和标准记谱配置。
- `songdance/api/scripts/evaluate_guitar.py` — 吉他固定集 A/B 与人工评级。
- `songdance/api/tests/test_guitar.py` — 复音、音域、八度和回退测试。
- `songdance/web/src/components/result/result-workspace.tsx` — 吉他输出边界和下载状态。

**验收标准：**

- 吉他固定集满足 note F1 ≥ 0.70、至少 7/10 人工可用，和弦关键样本不出现系统性漏音。
- MIDI、MusicXML 和 PDF 可解析；谱面按吉他标准八度记谱，MIDI 播放音高不被错误抬高八度。
- UI/API 不出现 TAB、弦号、把位、指法或 Guitar Pro 已支持的暗示。
- 其他已上线乐器固定集和 E2E 不下降。

---

## Phase 20：鼓转录、General MIDI 与打击乐谱

**目标：** 建立与有音高音符完全分离的鼓事件、播放、可视化和记谱管线。

**交付内容：**

- 在隔离环境比较 Omnizart drum 与其他经许可审计的鼓模型，输出标准鼓件类别、onset、velocity 和置信度。
- 建立 General MIDI 人类编号 Channel 10（代码零基索引 9）映射、`unknown_percussion` 回退和 MusicXML unpitched/percussion staff 生成。
- 增加鼓件 lane 时间线、鼓音色播放和轨道下载；禁止复用钢琴键盘或有音高转调控件。

**关键文件：**

- `songdance/api/app/pipeline/drums.py` — 鼓模型适配、事件归一和 GM 映射。
- `songdance/api/app/pipeline/score_drums.py` — MusicXML 打击乐谱生成与校验。
- `songdance/api/scripts/evaluate_drums.py` — 逐鼓件 onset F1 与人工评级。
- `songdance/web/src/components/result/drum-roll.tsx` — 固定鼓件 lane 可视化。
- `songdance/web/src/lib/midi/player.ts` — Channel 10（零基索引 9）鼓音色播放分支。

**验收标准：**

- 鼓固定集在 50 ms onset 容差下 macro F1 ≥ 0.70，至少 7/10 人工可用。
- MIDI 使用人类编号 Channel 10（代码零基索引 9）和标准鼓件 note，MusicXML 使用打击乐谱且通过 music21/OSMD 解析。
- 未知鼓件保留为 unknown 或低置信度，不强行映射为军鼓/底鼓。
- 结果页无钢琴键盘、左右手和移调控件，375 px 下轨道选择、播放和下载可用。

---

## Phase 21：完整混音分轨与直接多乐器 AMT 技术门禁

**目标：** 用固定混音真值集决定哪些轨道来源值得生产化，不把 Demucs 的 `other` 或全局平均分包装成逐乐器支持。

**交付内容：**

- 通过独立 Worker 适配 Demucs 固定提交/维护分支，验证四轨与实验六轨的分轨质量、串音、时延、内存和许可。
- 隔离评估 MT3 类直接多乐器 AMT，逐 instrument program 比较“直接多轨”与“分轨后单乐器模型”的音符质量。
- 建立至少 10 段带 stem/音符真值的混音固定集；对 vocals/drums/bass/guitar/piano/other 分别出报告。
- 形成已批准轨道来源白名单；小提琴、长笛、小号、萨克斯留在 `other` 时不得生成具体乐器轨。

**关键文件：**

- `songdance/api/app/pipeline/separation.py` — Demucs 适配与 stem 元数据。
- `songdance/api/app/pipeline/multitrack.py` — 直接多乐器 AMT 适配和 program 归一化。
- `songdance/api/app/pipeline/audio_quality.py` — 分轨串音与输入质量摘要。
- `songdance/api/experiments/multitrack/` — 固定依赖、checkpoint 校验和许可记录。
- `songdance/api/scripts/evaluate_multitrack.py` — 分轨与直接 AMT 的逐乐器 A/B 报告。

**验收标准：**

- 每个批准轨道来源都达到对应单乐器质量门槛，且 30 秒 P95 ≤ 360 秒、90 秒 P95 ≤ 720 秒。
- Demucs 四/六轨和 MT3 类候选的代码、权重、数据许可、固定提交及资源成本有书面审计。
- `other` 不被拆成未经门禁的小提琴、长笛、小号或萨克斯，直接多乐器模型也按逐 program 门禁而非全局分数放行。
- P1 开关关闭时不加载重模型、不增加单乐器时延、不改变任何已上线乐器结果。

---

## Phase 22：多轨结果工作台、部分成功与生命周期

**目标：** 把已批准的混音轨道变成可用产品流程，并保证轨道级失败、重试、下载和删除不会互相拖垮。

**交付内容：**

- 新增 `StemAsset` 持久化和轨道状态机，支持 `partial_success`、单轨重试、任务级删除与 24 小时级联清理。
- 编排已批准的分轨/直接 AMT 路由，为每轨生成独立原音、MIDI、时间线、MusicXML/PDF 和质量摘要。
- 构建多轨结果工作台，支持轨道选择、独听、原音/转录演奏切换、失败说明和逐轨下载。
- 增加完整混音高成本 feature flag、并发配额、超时熔断和旧钢琴/单乐器回归门禁。

**关键文件：**

- `songdance/api/app/models/job.py` — StemAsset、轨道状态和父子关系。
- `songdance/api/app/migrations/versions/006_stem_assets_and_track_status.py` — stem 与部分成功迁移。
- `songdance/api/app/services/transcription.py` — 多轨编排、单轨重试和状态聚合。
- `songdance/api/app/services/lifecycle.py` — 原音、stem、轨道产物和报告级联删除。
- `songdance/web/src/components/result/track-selector.tsx` — 多轨选择、状态和独听控制。
- `songdance/web/src/app/jobs/[jobId]/result-client.tsx` — 多轨结果装配和部分成功 UI。
- `songdance/web/e2e/multitrack-result.spec.ts` — 多轨、部分失败、重试、删除和窄屏 E2E。

**验收标准：**

- 每轨分别返回乐器、来源、两级置信度、模型版本、状态和产物；一个轨失败不阻塞其他轨播放下载。
- 删除或过期任务后，原始混音、全部 stem、轨道产物和质量报告均不存在。
- 完整混音开关关闭或技术门禁失败时，UI 引导改用单乐器模式，不生成伪造多轨。
- API/Web 全套检查、四种部分成功 E2E、375 px 窄屏和全部旧钢琴/单乐器回归通过。

---

## Phase 11–23 需求追踪

| Product Spec | 开发阶段 | 必须交付的证据 |
|---|---|---|
| AC-021 原始证据、清洗计数与原因 | Phase 11、13 | 产物关系、reason code 汇总、清洗回归报告 |
| AC-022 Beat/BPM/拍号/调性与置信度 | Phase 14 | 结构真值对比、低置信度回退、耗时报告 |
| AC-023 Chord 与合法多声部 | Phase 15 | music21 结构断言、OSMD 渲染和外部解析器结果 |
| AC-024 左右手分配与 `unknown` | Phase 15–16 | 交叉手样本、分手置信度、结果页假设标记 |
| AC-025 可读谱面门禁 | Phase 11、15 | 至少 16 段固定集、机器校验、至少 13/16 人工可读 |
| AC-026 分层失败与可用产物 | Phase 11、16 | API 部分成功状态和四种结果页 E2E |
| AC-027 可重复性 | Phase 11–15 | 相同版本/配置双跑摘要一致性报告 |
| AC-028 专用钢琴模型选择门禁 | Phase 12 | 同集 A/B、人工盲评、运行预算、许可与回退报告 |
| AC-045–AC-051 结果页谱面定位、选区播放与固定工作台 | Phase 23 | 真实 MusicXML 交互 E2E、播放边界测试、页面/谱面滚动位置证据 |
| AC-029–AC-030 乐器选择与安全路由 | Phase 17 | Profile 注册表、API 白名单、未知模型拒绝和旧任务兼容 |
| AC-031–AC-032 移调乐器与单音谱面 | Phase 18 | 响音/记谱音高测试、单行谱表和无左右手 UI |
| AC-033 吉他标准记谱 | Phase 19 | 复音固定集、八度一致性和无 TAB/Guitar Pro 边界 |
| AC-034 鼓事件与打击乐谱 | Phase 20 | Channel 10（零基索引 9）、GM 映射、鼓件 lane 和解析结果 |
| AC-035 人声旋律边界 | Phase 18 | 主旋律固定集、无歌词输出和范围警告 |
| AC-036–AC-037 逐乐器门禁与钢琴保护 | Phase 18–20 | 每乐器独立报告和完整钢琴回归 |
| AC-038–AC-039 轨道来源与未知乐器边界 | Phase 21–22 | 分轨/AMT A/B、逐轨元数据和 `other` 保护 |
| AC-040–AC-041 部分成功与级联删除 | Phase 22 | 单轨失败/重试 E2E 和对象存储清理证据 |
| AC-042 完整混音生产门禁 | Phase 21 | 逐 program 质量、许可、时延和内存报告 |
| SCOPE-016 混音分离适配器 | Phase 21–22 | 技术门禁、隔离 Worker、多轨编排和回退报告 |
| SCOPE-018 单乐器模式与路由 | Phase 17 | InstrumentProfile、选择器、兼容 API 和白名单路由 |
| SCOPE-019 单音家族 | Phase 18 | 六类输入逐乐器固定集、模型 A/B 和谱面合同 |
| SCOPE-020 吉他标准记谱 | Phase 19 | 复音转录、八度记谱和无 TAB 边界 |
| SCOPE-021 鼓转录 | Phase 20 | 鼓事件、GM MIDI、鼓件 lane 和打击乐谱 |
| SCOPE-022 完整混音多轨 | Phase 21–22 | 分轨/直接 AMT 门禁、多轨 UI、部分成功和删除 |

**交接顺序：** 后续开发 Agent 先完成 Phase 9 和 Phase 11–16 的钢琴质量闭环，再完成结果工作台 Phase 23，之后严格按 Phase 17 → 18 → 19 → 20 → 21 → 22 推进多乐器。每个乐器过门禁后才能在选择器中启用；不得为了等完整混音而阻塞已通过的单乐器能力。每个 Phase 单独提交，不允许把模型切换、数据库迁移、谱面算法和 UI 改动混进一个不可归因的提交。

**停止条件：** 任一候选算法未达到对应乐器数值门槛、结构严重错误增加、固定集人工评级下降、许可不明确、超出资源预算，或破坏旧钢琴任务/下载 API，即停止该乐器晋级并保留上一版本。一个乐器失败只阻塞该乐器；完整混音失败不回滚已上线单乐器能力。生产默认值只能来自固定回归报告，不得凭示例页截图调整。

---

## 技术栈

| 层级 | 技术 | 版本 | 说明 |
|---|---|---|---|
| Web 框架 | Next.js / React | 16.2.12 / 19.2.8 | App Router、SSR 和 Vercel 部署 |
| 语言 | TypeScript | 5.9.3 | Next.js 16.2.12 脚手架当前安装的兼容版本；未采用尚未验证兼容性的 7.0.2 |
| 样式 | Tailwind CSS | 4.3.3 | 设计变量和响应式 UI |
| 波形 | WaveSurfer.js | 7.12.11 | 音频播放和选区 |
| 乐谱 | OpenSheetMusicDisplay | 2.1.0 | MusicXML 渲染 |
| MIDI | Tone.js / @tonejs/midi | 15.1.22 / 2.0.28 | MIDI 解析与播放 |
| PDF | jsPDF | 4.2.1 | 客户端乐谱 PDF 导出 |
| Web 测试 | Vitest / Playwright | 4.1.10 / 1.62.0 | 单元、组件与端到端测试 |
| API 框架 | FastAPI | 0.140.7 | 上传、任务和产物接口 |
| Python | CPython | 3.11 | Basic Pitch 与 music21 兼容基线 |
| 转录模型 | Basic Pitch | 0.4.0 | 开源 Audio-to-MIDI 基线 |
| 钢琴模型候选 / 研究参考 | piano_transcription_inference / Aria-AMT | `piano_transcription_inference` 固定提交与生产许可待审计；Aria-AMT `EleutherAI/aria-amt@a1ab73fc901d1759ec3bc173c146b3c6a3040261`，权重 revision `8cc4cf5c83b47f2689ac256a947b2a57c17a4c8b`、SHA-256 `089d3129dbe93246aeda55efe668c8a48af08afaf9dd15c64cef0a07c0fb30a4` | Phase 12 只评测生产许可先通过的候选；Aria-AMT 权重 CC-BY-NC-SA-4.0，固定为 `research_only` 审计参考，取消 CUDA 与固定集 A/B，线上继续使用 Basic Pitch |
| 单音候选 | librosa pYIN / CREPE | librosa 0.11.0 / CREPE 固定提交待验证 | Phase 18 与 Basic Pitch 按乐器 A/B；CREPE MIT 但维护与 TensorFlow 兼容需验证 |
| 任务模型候选 | Omnizart | 固定提交/checkpoint 待审计 | Phase 18 人声与 Phase 20 鼓；代码 MIT，权重和 ARM/Python 兼容需验证 |
| 直接多轨候选 | MT3 | 固定提交/checkpoint 待审计 | Phase 21 多 instrument program A/B；代码 Apache-2.0、非官方支持产品、T5X/GPU 依赖隔离 |
| 音频分析 | librosa | 0.11.0 | 当前已由 Basic Pitch 间接锁定；Phase 14 提升为显式依赖并验证 BPM、beat、起音和调性基线 |
| 乐谱后处理 | music21 | 10.5.0 | MIDI 量化、分手和 MusicXML |
| 可选分轨 | Demucs/维护分支 | P1 实验，固定提交待审计 | Meta 上游仓库已归档；四轨/六轨在独立 Worker 评估，不进入主 API 镜像 |
| 媒体处理 | FFmpeg | 7.x 或部署平台稳定版 | 解码、裁剪和规范化；镜像内固定小版本 |
| 数据库 | PostgreSQL | 17.x | 任务和产物元数据 |
| 队列 | Redis + RQ | Redis 7.x | Worker 排队、重试和限流 |
| 对象存储 | S3 兼容存储 | 服务端版本 | 私有临时音频和产物 |
| 包管理 | pnpm / uv | pnpm 10.x / uv 当前稳定版 | Web 与 Python 依赖管理 |

版本说明：前端和核心 Python 包版本于 2026-07-28 通过 npm/PyPI 查询；2026-08-05 复核当前锁文件与官方仓库，确认 librosa 0.11.0 已锁定、Basic Pitch 明确支持跨乐器复音但建议一次一个乐器、Demucs 上游已归档且六轨钢琴质量有限、MT3 提供多乐器 checkpoint 但不属于官方支持产品、Omnizart 存在 ARM 兼容限制。开发时先在隔离环境验证固定提交、checkpoint 哈希、许可和资源预算；未选中的模型不得进入主 Worker。Essentia 为 AGPL-3.0，madmom 的源代码与模型数据许可不同，二者未完成审计前只允许离线评估。

## 数据库表

| 表名 | 所属 Phase | 用途 |
|---|---|---|
| `transcription_jobs` | Phase 3 | 任务状态、阶段、区间、过期和错误码 |
| `source_assets` | Phase 3 | 输入文件元数据和对象键 |
| `transcription_results` | Phase 4 | 模型版本、速度、拍号、音符数和质量标记 |
| `artifacts` | Phase 4 | MIDI、MusicXML、JSON、PDF 产物元数据 |
| `transcription_quality_reports` | Phase 11 | 原始/清洗音符统计、结构错误、置信度、模型和后处理版本 |
| `transcription_tracks` | Phase 17 | 乐器 profile、模型路由、轨道状态、两级置信度和版本 |
| `stem_assets` | Phase 22 | 完整混音内部 stem、来源模型、对象键和过期时间 |
| `analytics_events` | Phase 6 | 白名单产品事件和阶段耗时 |

## 开发规则

- 每完成一个 Phase 必须执行：Code Review → 测试完整性 → 编译验证 → 功能测试。
- 四步全部通过后才能把 Phase 标为完成；失败必须修复并重验。
- 功能开发完成后必须 spawn code-reviewer，按 code-review skill 进行两阶段审查。
- Commit message 使用 feat、fix、refactor、test、docs、chore 前缀。
- Web 包管理器使用 pnpm；Python 使用 uv；生产依赖必须锁定。
- 先实现本地可重复环境，再接生产托管服务；生产服务通过适配层注入，业务代码不得写死供应商。
- P1 YouTube 功能必须受环境变量开关控制，不能阻塞 P0 发布。
- 每个乐器和完整混音必须使用独立 feature flag；未通过固定集门禁的选项不得在生产选择器中启用。
- 模型依赖按 Worker/实验镜像隔离；不得为一个候选模型把未选中的 Torch、TensorFlow、T5X 或权重塞进主 API 镜像。
- 所有 MIDI 与内部有音高时间线保存响音高；移调只发生在 MusicXML/谱面层，并由回归测试验证播放与记谱的固定音程关系。
- 所有上传文件、任务 ID、对象键和外部命令参数必须按 Product-Spec 的安全约束实现。
