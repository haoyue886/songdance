# Development Plan — SongDance AI Piano Transcriber

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
```

依赖原则：Phase 2 和 Phase 3 都依赖 Phase 1，可并行开发但不能同时修改共享配置；Phase 4 依赖 Phase 3；Phase 5 依赖 Phase 2 和 Phase 4；Phase 6–8 依次收紧生产能力。

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
- 使用 Tone.js 播放 MIDI，支持暂停、定位、0.5×–1.5× 变速和循环。
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
| 乐谱后处理 | music21 | 10.5.0 | MIDI 量化、分手和 MusicXML |
| 媒体处理 | FFmpeg | 7.x 或部署平台稳定版 | 解码、裁剪和规范化；镜像内固定小版本 |
| 数据库 | PostgreSQL | 17.x | 任务和产物元数据 |
| 队列 | Redis + RQ | Redis 7.x | Worker 排队、重试和限流 |
| 对象存储 | S3 兼容存储 | 服务端版本 | 私有临时音频和产物 |
| 包管理 | pnpm / uv | pnpm 10.x / uv 当前稳定版 | Web 与 Python 依赖管理 |

版本说明：以上前端和核心 Python 包版本于 2026-07-28 通过 npm/PyPI 查询。开发时必须先跑兼容性安装；若 Next.js 对 TypeScript 7 或 Basic Pitch 对 Python 3.11 存在实际冲突，锁定到最新兼容小版本并在本文件记录，不得硬凑版本。

## 数据库表

| 表名 | 所属 Phase | 用途 |
|---|---|---|
| `transcription_jobs` | Phase 3 | 任务状态、阶段、区间、过期和错误码 |
| `source_assets` | Phase 3 | 输入文件元数据和对象键 |
| `transcription_results` | Phase 4 | 模型版本、速度、拍号、音符数和质量标记 |
| `artifacts` | Phase 4 | MIDI、MusicXML、JSON、PDF 产物元数据 |
| `analytics_events` | Phase 6 | 白名单产品事件和阶段耗时 |

## 开发规则

- 每完成一个 Phase 必须执行：Code Review → 测试完整性 → 编译验证 → 功能测试。
- 四步全部通过后才能把 Phase 标为完成；失败必须修复并重验。
- 功能开发完成后必须 spawn code-reviewer，按 code-review skill 进行两阶段审查。
- Commit message 使用 feat、fix、refactor、test、docs、chore 前缀。
- Web 包管理器使用 pnpm；Python 使用 uv；生产依赖必须锁定。
- 先实现本地可重复环境，再接生产托管服务；生产服务通过适配层注入，业务代码不得写死供应商。
- P1 YouTube 功能必须受环境变量开关控制，不能阻塞 P0 发布。
- 所有上传文件、任务 ID、对象键和外部命令参数必须按 Product-Spec 的安全约束实现。
