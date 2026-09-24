# Development Plan — SongDance AI Music Transcriber

> 本文件记录项目开发阶段、依赖顺序、当前进度和验收标准。
> Product-Spec.md 是需求事实来源；本计划只决定如何实现。
> 当前没有 Design-Brief.md 或设计稿，UI 依据 Product-Spec 的工作台结构与竞品调研中的轻量音乐 SaaS 原则实现，不复制竞品品牌或像素级界面。

## 当前进度

2026-09-11 总回归核对：API 487 passed、7 failed、6 skipped，其中 6 项为待统一重生成的固定集指纹失效，1 项为 08 改动重新引入按置信度删音导致 09 无证据保留回归。已移除 `_select_fixture_melody`，只在合法 single_staff 分支分配右手，任何提示均不得据置信度丢事件。Web 140 tests 和 TypeScript 通过。08 仅有上下文传递，未证明八分音符/BPM 等价转换完成；10 的 130 ms 匹配是指标口径变更，不得据此宣称量化算法已修复；06 尚余多余事件。当前不能生成或签收“全部修复完成”的最终包。

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
| Phase 12 | 已取消 | 用户确认不做专用钢琴模型 A/B；历史许可审计保留，生产固定使用 Basic Pitch |
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
| Phase 24 | 已完成 | 实时谱面拖选预览、连续事件命中、反向/跨系统手势与边缘自动滚动；代码审查 Stage 1/2 PASS |
| Phase 25 | 已完成 | 已提交谱面选区的 `↔` 边界命中、实时端点调整与稳定 pointer capture；代码审查 Stage 1/2 PASS |
| Phase 26 | 已完成 | 双击清除正式谱面选区、边界点击隔离与无选区即时定位；代码审查 Stage 1/2 PASS |
| Phase 27 | 已完成 | 海外 SEO 技术基线、核心 Audio-to-MIDI 页面与索引门禁；代码审查 Stage 1/2 PASS |
| Phase 28 | 已完成 | 英语默认的中英文国际化、语言切换与核心 SEO 首页合并；代码审查 Stage 1/2 PASS |
| Phase 29 | 开发中 | Basic Pitch 完整 90 秒结构分析与双手共享边界的 MusicXML 弱起优化 |
| Phase 30 | 复评中 | 专业评审驱动的琶音结构修复；自动门禁已完成，等待 `04-arpeggios` 专业复评通过 |
| Phase 31 | 已完成（国际化范围） | 八语言入口、工具页核心文案、切换、SEO 与物理消息基线；代码审查 Stage 1/2 PASS |
| Phase 32 | 开发中 | 公开示例撤回与初级曲目准入、调号语义、快速音型量化和分手密度门禁 |
| Phase 33 | 计划中 | 局部调性真值集、终止式/和弦证据、主音化与转调判定及候选校准 |
| Phase 34 | 计划中 | 保守调号、小调临时变音、最多两个候选和单谱表/大谱表语义输出 |
| Phase 35 | 计划中（P1） | 中国五声、日本都节与布鲁斯调式家族研究门禁 |
| Phase 36 | 已完成 | `07-soft` 三项专业缺陷修复；人工复评 `minor_edits`，自动门禁通过 |
| Phase 37 | 开发中 | `14-hand-crossing` 60 BPM 均匀八分音符与交汇同音保留；不生成最终评审包 |

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
                                  └─ Phase 27 技术 SEO 基线
                                          └─ Phase 28 英语默认国际化与核心首页合并

Phase 9 基线
  └─ Phase 11 质量评测契约
          ├─ Phase 12 专用钢琴模型 A/B（已取消，保留历史审计）
          └─ Phase 13 音符清洗
                  └─ Phase 14 Beat / 调性 / 拍号与量化
                          └─ Phase 15 和弦 / 多声部 / 左右手
                                  └─ Phase 16 五线谱质量展示与产物版本
                                          └─ Phase 29/30 结构与琶音修复
                                                  └─ Phase 32 初级示例与快速音型质量门禁
                                                          └─ Phase 33 局部调性证据与候选校准
                                                                  └─ Phase 34 保守调号与语义谱表输出
                                                                          └─ Phase 35 非西洋调式家族 P1 门禁
                                                                                  └─ Phase 36 `07-soft` 三项失败修复与复评
                                                                                          └─ Phase 37 `14-hand-crossing` 均匀八分记谱
                                          └─ Phase 23 固定谱面工作台与区间播放
                                                  └─ Phase 24 实时谱面拖选反馈
                                                          └─ Phase 25 选区边界二次调整
                                                                  └─ Phase 17 多乐器领域模型与路由
                                                                  └─ Phase 18 单音家族
                                                                          └─ Phase 19 吉他
                                                                                  └─ Phase 20 鼓
                                                                                          └─ Phase 21 混音技术门禁
                                                                                                  └─ Phase 22 多轨产品化
```

依赖原则：Phase 2 和 Phase 3 都依赖 Phase 1，可并行开发但不能同时修改共享配置；Phase 4 依赖 Phase 3；Phase 5 依赖 Phase 2 和 Phase 4；Phase 6–8 依次收紧生产能力。Phase 13–16 按顺序消费 Phase 11 的质量基线；Phase 12 已取消，不再恢复候选模型路线。Phase 24 只消费 Phase 23 已稳定的乐谱时间映射、跨页几何和播放选区合同；Phase 25 在 Phase 24 的命中缓存、RAF draft 与稳定覆盖层上增加已提交选区的端点调整，在进入多乐器结果页扩展前完成。Phase 28 消费 Phase 27 已完成的 metadata、sitemap 和结构化数据基线，只替换语言路由与核心页面信息架构，不重做 SEO 基础设施。Phase 29 消费 Phase 11、13–16 的原始证据和结构基线，只优化 Basic Pitch 确定性后处理。Phase 32 消费 Phase 29/30 的结构产物与当前公开示例发布器：先撤回已被新评审判为 `needs_redo` 的莫扎特示例，再引入带参考谱的初级真实演奏；快速量化、半速推理和织体分手必须各自过固定真值门禁，不与示例替换绑成一次不可归因的上线。Phase 33 消费已完成的 Phase 14–16 与 Phase 32 Task 32.3 调号语义，只新增版本化局部调性证据，不改写 Basic Pitch 原始事件；开始编码前必须冻结当前 Phase 32 共享流水线与固定集指纹，避免同时修改 `analysis.py`、`score.py`。Phase 34 只消费 Phase 33 已校准候选，负责记谱与 UI，不在展示层重新猜调性；Phase 35 为 P1，必须在 Phase 33 的证据合同稳定后隔离开发，失败不能阻塞 major/minor P0。Phase 17–20 按“共享领域模型 → 单音家族 → 吉他 → 鼓”顺序扩展单乐器能力；每个乐器独立过门禁。Phase 21 只有在 Phase 18–20 具备可复用单乐器路由后才评估完整混音，Phase 22 只消费 Phase 21 已批准的轨道来源，不在 UI 层猜乐器。

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

## Phase 24：实时谱面拖选反馈与连续区间命中

**目标：** 在 Phase 23 已稳定的 OSMD 时间映射、跨页坐标和选区播放合同上，将谱面选择从“松手后一次生成”升级为拖动中的逐帧预览；实现反向、跨系统和边缘滚动手势，同时不触发 OSMD 重新排版、不提前修改正式播放边界。

**交付内容：**

- 建立 OSMD 排版后的只读命中缓存，按页面、系统、小节和乐谱事件索引坐标与时间；在相邻事件间连续插值，并在横向距离事件不超过 8 CSS px 时磁吸，避免拖动边界按整小节或稀疏音符跳动。
- 实现基于 Pointer Events 和 `requestAnimationFrame` 的临时拖选状态机：超过 4 px 后进入拖选、每帧最多更新一次、支持越过锚点反向选择，并在释放前保持正式播放选区不变。
- 重构谱面覆盖层，把同一系统内相邻小节合并为稳定的连续选区段；拖动中实时更新选区外遮罩、选区内原始黑色和绿色边界，不产生逐小节接缝或 DOM 闪烁。
- 完成取消与滚动边界：`Escape`、`pointercancel`、失去 pointer capture 或触屏滚动接管时恢复旧选区；靠近谱面视口上下 36 px 时只按每帧 4–18 CSS px 自动滚动谱面内部容器。

**关键文件：**

- `songdance/web/src/lib/result/score-hit-map.ts` — OSMD 页面/系统/事件命中缓存、连续时间插值和事件磁吸。
- `songdance/web/src/hooks/use-score-range-drag.ts` — Pointer Events、临时选区、RAF 合帧、反向拖动、取消和边缘自动滚动。
- `songdance/web/src/components/result/score-selection-overlay.tsx` — 稳定 SVG 遮罩、跨系统连续轮廓和临时/正式选区呈现。
- `songdance/web/src/components/result/score-viewer.tsx` — 组装 OSMD、命中缓存、拖选 Hook 与覆盖层，保留点击定位和当前小节高亮。
- `songdance/web/src/lib/result/score-selection.ts` — 复用 Phase 23 时间/几何换算并输出按系统合并的选区段。
- `songdance/web/src/components/result/score-viewer.test.tsx` — 拖动中预览、短点击、反向、跨系统、取消和失去捕获回归。
- `songdance/web/e2e/phase7.spec.ts` — 真实 MusicXML 拖动中间帧、边缘滚动、播放边界和桌面/窄屏视觉回归。

**验收标准：**

- 鼠标移动超过 4 px 后，在释放前即可看到临时选区；边界、遮罩和黑色选中内容在下一动画帧内跟随指针，连续快速往返 2 秒无可见滞后或闪烁。
- 指针越过锚点、跨小节、跨系统和跨页移动时，选区按阅读顺序正确缩放或扩展；同一系统只生成一个连续轮廓，没有逐小节内部接缝。
- 拖动期间正式播放选区和播放边界保持不变；释放后一次性提交新选区，原音与转录演奏继续按 Phase 23 合同停止或循环。
- `Escape`、`pointercancel`、失去 pointer capture 和触屏纵向滚动均取消临时选区并恢复旧选区；位移不足 4 px 仍执行单击定位。
- 指针进入谱面视口上下 36 px 时谱面内部按边缘距离以每帧 4–18 CSS px 自动滚动，页面 `window.scrollY` 不变；离开边缘或结束拖动后立即停止自动滚动。
- 拖动期间每个动画帧最多提交一次覆盖层更新，不调用 `osmd.render()`；真实 18 小节示例在 60 Hz 浏览器中视觉边界不落后指针超过一帧。
- 375 px 下无页面级横向滚动且触屏纵向浏览不被误识别为选区；映射不可用时仍保持 Phase 23 的明确禁用状态。
- Web 单测、lint、typecheck、生产构建、真实 MusicXML Playwright 中间帧截图和像素检查全部通过；代码审查 Stage 1/2 PASS。

**依赖与风险：**

- 依赖 Phase 23 的 `score-time-map.ts`、页感知坐标转换、选区播放边界和固定谱面视口；不增加数据库、API、OSMD 版本或第三方动画库。
- `score-viewer.tsx` 当前已接近 300 行上限，本 Phase 必须把命中、手势和覆盖层拆到独立模块，不允许继续堆入组件。
- OSMD 事件横向间距不是线性节拍网格，连续时间必须在相邻事件锚点间插值并保留事件磁吸；不得用整小节平均比例冒充精确命中。
- 触屏拖选与纵向滚动存在手势冲突，浏览器发出取消或接管滚动时必须以浏览为先，不得留下半成品选区。

**完成记录（2026-08-10）：**

- OSMD 排版后建立按页面、系统、小节和事件索引的只读命中缓存；点击与拖选在事件之间连续插值，8 CSS px 内磁吸，并用同一事件 anchors 逆向计算覆盖层几何。
- Pointer Events 状态机以 4 CSS px 为阈值并按 RAF 合帧；拖动中只更新 draft，释放后才提交正式播放边界，支持反向、跨系统、跨页、四种取消路径和谱面内部边缘自动滚动。
- 同一系统的选区合并为稳定 SVG segment；真实 18 小节 MusicXML 连续快速往返至少 2 秒后，边界与指针像素误差不超过 10 px，拖动期间不重新调用 `osmd.render()`。
- 修复 375 px 下 OSMD backend wrapper 缩放坐标换算，真实质量结果页点击第 2 小节可正确定位；触摸纵向滚动接管通过 `pointercancel` 清除临时选区。
- Web `27 files / 118 tests`、Playwright `14/14`、lint、typecheck、生产构建通过；代码审查 Stage 1/2 PASS，`0 HIGH / 0 MEDIUM / 0 LOW`。

---

## Phase 25：已提交谱面选区的边界调整

**目标：** 在不增加常驻手柄或整体平移模式的前提下，让用户通过选区起止边界的 `↔` 光标重新调整已提交区间；继续复用 Phase 24 的事件级命中、逐帧 draft、跨页几何、取消恢复和播放边界合同。

**交付内容：**

- 为正式选区首段左边界和末段右边界增加 16 CSS px 透明命中带；只有 hover 命中时显示系统原生 `ew-resize` 光标，视觉层不增加常驻按钮或手柄。
- 扩展谱面拖选状态机，加入基于原选区固定另一端的边界调整模式；超过 4 CSS px 后逐帧更新 draft，允许跨系统、跨页和越过固定端，松手后一次性提交。
- 让边界短点击不触发谱面 seek；`Escape`、`pointercancel`、失去 pointer capture、触屏滚动接管和清除选区均安全结束调整并恢复原正式选区。

**关键文件：**

- `songdance/web/src/components/result/score-selection-overlay.tsx` — 首尾边界透明命中线、`ew-resize` 光标和边界 pointer 入口。
- `songdance/web/src/hooks/use-score-range-drag.ts` — create/resize 双模式状态、固定端点、角色交换、RAF draft、提交和取消。
- `songdance/web/src/components/result/score-viewer.tsx` — 正式选区与边界调整接线、点击定位隔离。
- `songdance/web/src/components/result/score-selection-overlay.test.tsx` — 命中带数量、位置、光标和稳定节点测试。
- `songdance/web/src/hooks/use-score-range-drag.test.tsx` — 左右端调整、阈值、越界交换、取消和正式边界隔离测试。
- `songdance/web/e2e/phase7.spec.ts` — 真实 MusicXML `↔` hover、边界二次调整、跨系统与播放边界回归。

**验收标准：**

- 正式选区存在时，仅首尾竖向边界各有一个 16 CSS px 命中带；hover 计算光标为 `ew-resize`，选区其他边框和谱面正文保持既有光标与点击行为。
- 从起点或终点边界按下移动不超过 4 CSS px 时，选区、循环起止和播放头均不变化；超过阈值后下一动画帧显示基于原选区的 draft，另一端保持固定。
- 边界可跨小节、系统和页面移动并越过固定端；同一事件 anchors 同时用于命中与覆盖层逆向几何，边界与指针误差不超过 10 CSS px。
- 松手后正式播放区间只提交一次；`Escape`、`pointercancel` 和失去 capture 后旧选区完整恢复，边界点击不会额外触发 seek。
- 调整期间继续复用 36 px 边缘区和 4–18 CSS px/帧内部滚动，`window.scrollY` 不变化，也不调用 `osmd.render()`。
- 375 px 与桌面视口无页面级横向滚动；时间映射不可用或无正式选区时不显示边界命中入口。
- Web 单测、lint、typecheck、生产构建和真实 MusicXML Playwright 全部通过；代码审查 Stage 1/2 PASS。

**依赖与风险：**

- 依赖 Phase 24 的 `ScoreSelectionSegment` 稳定 key、事件时间双向几何、Pointer capture 和自动滚动状态机，不新增数据库、API、OSMD 版本或动画库。
- 覆盖层位于谱面上方，只有透明命中线允许 pointer events；遮罩、绿色高亮和边框继续 `pointer-events: none`，避免大面积截断谱面点击。
- 跨系统选区只允许首段左边界和末段右边界调整；中间系统矩形边缘不是独立端点，不得显示 `↔` 或开始调整。

**完成记录（2026-08-11）：**

- 正式选区首尾边界各提供 16 CSS px 透明命中带，真实 Chrome 通过 `elementFromPoint` 命中并计算为系统原生 `ew-resize`；短点击不修改选区、循环边界或播放头。
- create/resize 共用 4 CSS px 阈值、RAF draft、事件磁吸、36 px 边缘区和 4–18 CSS px/帧内部滚动；拖动起点或终点时另一端固定，松手后只提交一次正式区间。
- resize pointer capture 绑定稳定谱面视口，零宽 draft 即使临时卸载边界线也能继续越过固定端并交换角色；`Escape`、`pointercancel`、lost capture 和外部清除均恢复正式选区。
- 真实 18 小节 MusicXML 覆盖同系统越过固定端、跨页终点从第 2 页拖回第 1 页、边缘自动滚动、页面滚动不变、OSMD 不重排和二次调整截图。
- Web `27 files / 128 tests`、Playwright `14/14`、lint、typecheck、生产构建通过；代码审查 Stage 1/2 PASS，`0 HIGH / 0 MEDIUM / 0 LOW`。

---

## Phase 26：双击清除谱面选区

**目标：** 保持无选区时的单击定位、拖选和边界调整手势，让存在正式选区的用户可双击谱面工作区直接清除选区，并确保浏览器的两次 click 不产生额外定位。

**交付内容：**

- 无选区谱面点击继续即时定位；正式选区存在时单击不定位，双击直接清除选区，避免不可读取的系统双击阈值造成播放头竞态。
- 让 SVG 选区边界与普通谱面正文都能冒泡到统一的工作区双击入口，既不干扰 pointer drag，也不改变播放头或滚动位置。
- 覆盖双击清除、无选区双击定位、拖选后的点击抑制及真实 MusicXML 播放边界回归。

**关键文件：**

- `songdance/web/src/components/result/score-viewer.tsx` — 可取消单击定位与工作区双击清除入口。
- `songdance/web/src/components/result/score-viewer-double-click.test.tsx` — 单击/双击时序、选区清除和播放头隔离测试。
- `songdance/web/e2e/phase7.spec.ts` — 真实 MusicXML 双击清除与播放边界回归。

**验收标准：**

- 正式选区存在时，单击谱面正文或选区边界不改变播放头；双击后选区遮罩、绿色边界和循环起止输入均消失，播放头、`window.scrollY` 与谱面 `scrollTop` 均不变。
- 正式选区双击不产生任何 `onSeek`；无正式选区时沿用普通单击定位语义。
- 已有拖选、边界调整、短点击和 `Escape` 取消行为不回归；Web 单测、lint、typecheck、生产构建、真实 MusicXML E2E 与代码审查 Stage 1/2 全部通过。

**依赖与风险：**

- 浏览器双击由两次 `click` 后接一个 `dblclick` 组成；正式选区存在时必须在 `click` 阶段抑制定位，不能仅在 `dblclick` 中调用清除。
- 不新增播放器状态、API、依赖或常驻 UI 控件。

**完成记录（2026-08-11）：**

- 谱面视口统一处理双击：正式选区存在时正文与端点单击均不定位，双击只清除选区；端点单击单独停止冒泡，而 `dblclick` 继续冒泡到清除入口。
- 无正式选区继续即时采用原有单击定位，不引入不可读取系统双击阈值的延迟计时器；清除选区后恢复该语义。
- 组件测试覆盖正文单击隔离、端点双击清除、端点短点击不定位和清除后的普通定位；真实 18 小节 MusicXML E2E 验证选区、循环边界、播放头和两级滚动边界。
- Web `28 files / 129 tests`、Playwright `14/14`、lint、typecheck、生产构建通过；代码审查 Stage 1/2 PASS，`0 HIGH / 0 MEDIUM / 0 LOW`。

---

## Phase 27：海外 SEO 技术基线与核心页面

**目标：** 先让稳定公开页面可被正确发现、理解和索引，再用一个高意图英语核心页面验证海外自然搜索需求；临时任务与未经验证的批量页面不得进入索引。

**交付内容：**

- 建立统一站点 origin、metadata template、canonical、Open Graph/Twitter、GSC verification、`robots.ts` 与 `sitemap.ts`。
- 为匿名 `/jobs/*` 输出 `noindex, nofollow`，并用 sitemap 测试保证随机任务 URL 永不进入公开索引资产。
- 新增 `/audio-to-midi` 服务端可抓取页面，包含工具入口、真实示例、输出/限制、FAQ、内部链接和与可见内容一致的 JSON-LD。
- 优化首页与示例页元数据、站内链接和 WebApplication 结构化数据；补充生产 `NEXT_PUBLIC_SITE_URL` 配置说明。
- 产出 `SEO-PLAN.md`，将首批 10 页、3 份 Brief、发布检查和 30 天 GSC 循环作为扩展门禁。

**关键文件：**

- `SEO-PLAN.md` — 关键词、页面资产、Brief、发布与迭代计划。
- `songdance/web/src/lib/seo/site.ts` — 站点 origin 与绝对 URL。
- `songdance/web/src/app/layout.tsx` — 全局 metadata 和验证标记。
- `songdance/web/src/app/robots.ts`、`sitemap.ts` — 抓取与索引入口。
- `songdance/web/src/app/audio-to-midi/page.tsx` — 英语核心工具页与结构化数据。
- `songdance/web/src/app/jobs/[jobId]/page.tsx` — 临时任务 noindex。

**验收标准：**

- 生产域名配置后，稳定公开页面 canonical、Open Graph 和 sitemap 同源且不含 localhost；本地构建使用明确的开发 fallback。
- robots、sitemap 与核心页静态响应为 200；sitemap 无 `/jobs/`，任务页 metadata 明确 `noindex, nofollow`。
- `/audio-to-midi` 服务端 HTML 含唯一 H1、真实 CTA、限制、FAQ、站内链接和可解析 JSON-LD；不依赖客户端渲染才出现关键词正文。
- Web 单测、lint、typecheck、生产构建与 Playwright 页面抓取通过；代码审查 Stage 1/2 PASS。

**依赖与风险：**

- 当前没有真实搜索量、KD、SERP 或 GSC 数据，关键词优先级全部标为假设；不得把计划数字写成已验证市场事实。
- `NEXT_PUBLIC_SITE_URL` 在生产必须设置为最终 HTTPS 域名；未设置时本地构建只能生成 localhost fallback，不可直接作为生产 SEO 验收证据。
- 不新增分析脚本或第三方 cookie；GSC 验证仅在配置 token 后输出。

**完成记录（2026-08-11）：**

- 建立统一生产 origin、页面级 canonical/OG/Twitter、GSC verification、robots 与 sitemap；生产构建的 6 个稳定 URL 全部使用同一 HTTPS origin，任务 URL 不进入 sitemap。
- 新增服务端 `/audio-to-midi` 英语核心页，提供真实转录入口、公共示例、输入/输出边界、FAQ、内部链接和 WebApplication + FAQPage JSON-LD；结构化数据不声明未经页面证明的价格、评分或准确率。
- `/jobs/*` 输出 `noindex, nofollow, nocache` 且不输出分享 metadata；自定义 404 保持唯一 title、唯一框架 noindex，并移除错误的首页 OG/Twitter 继承。
- 原始响应 E2E 不执行客户端 JavaScript 即解析 H1、正文和 JSON-LD；桌面与 375 px 截图无横向溢出。
- Web `29 files / 131 tests`、Playwright `15/15`、lint、typecheck、生产构建和 `git diff --check` 通过；代码审查 Stage 1/2 PASS，`0 HIGH / 0 MEDIUM / 2 LOW`。剩余 LOW 为上线后的自然搜索漏斗归因和原始 DOM 断言加固，不阻断 AC-059–AC-063。
- 本节记录 Phase 27 当时已完成的历史实现；后续确认的英语默认国际化、首页内容合并和旧路由重定向由 Phase 28 替代，不回写或伪造 Phase 27 的原始验收结果。

---

## Phase 28：英语默认的中英文国际化与核心首页合并

**目标：** 使用一套页面组件向海外用户默认提供英语，并通过 `/zh` locale URL 提供完整简体中文体验；合并重复 SEO 落地页，同时保持上传、任务、结果和导出行为一致。

**交付内容：**

- 接入 `next-intl` 4.13.6，建立 `en` 与 `zh-CN` 消息目录和 as-needed locale 路由；无前缀 URL 固定输出英语，中文使用 `/zh`，不按浏览器语言自动改写根 URL。
- 将首页、上传、示例、任务/结果、法律页、错误边界和公共导航迁入共享 locale 页面树；在桌面与移动导航提供语言切换，保持逻辑路径、任务 ID、查询参数和 hash。
- 将用户可见状态、校验和 API 错误统一映射为 locale 消息；FastAPI 继续返回稳定 `error_code` 和结构化数据，不复制 Web UI 翻译文案。
- 把 `/audio-to-midi` 的核心说明、限制、FAQ、内部链接和 JSON-LD 合并到英语首页，并将旧地址永久重定向到 `/`；为两种语言生成自引用 canonical、双向 hreflang、英语 x-default 和 sitemap 项。
- 增加消息 key 对齐、无 JavaScript 服务端 HTML、语言切换、动态任务路径、旧地址重定向、metadata、375 px 和既有核心流程回归测试。

**关键文件：**

- `songdance/web/next.config.ts` — next-intl 插件与旧地址永久重定向。
- `songdance/web/src/proxy.ts` — locale 路由匹配与默认英语策略。
- `songdance/web/src/i18n/routing.ts`、`request.ts` — locale、前缀和服务端消息加载。
- `songdance/web/messages/en.json`、`zh-CN.json` — 对齐的共享消息目录。
- `songdance/web/src/app/[locale]/layout.tsx` 与各页面入口 — 动态 `lang`、共享页面和本地化 metadata。
- `songdance/web/src/components/language-switcher.tsx` — 保持当前逻辑页面的语言切换控件。
- `songdance/web/src/lib/i18n/errors.ts` — API `error_code` 到本地化消息 key 的稳定映射。
- `songdance/web/src/app/sitemap.ts`、`src/lib/seo/site.ts` — 语言 alternates、canonical 与 sitemap。
- `songdance/web/e2e/i18n.spec.ts` — 原始 HTML、切换、任务路径、SEO 和窄屏 E2E。

**验收标准：**

- 不执行客户端 JavaScript 请求 `/` 与 `/zh` 时，两者共享结构但分别完整输出英语和简体中文，且 `<html lang>`、title、description、canonical、JSON-LD 与可见内容一致。
- 从任一稳定页或 `/jobs/{id}` 切换语言后，逻辑路径、任务 ID、查询参数和 hash 保持；刷新后语言不回跳，375 px 无页面级横向滚动。
- `en` 与 `zh-CN` 消息 key 完全一致；首页、上传、处理、成功、失败、结果、示例、法律页、404 和 API 错误均不出现 key、错误语言或原始技术错误。
- 所有稳定语言 URL 自引用 canonical、互相声明 `en`/`zh-CN` 和英语 x-default；sitemap 包含两种语言且不含任务 URL。
- `/audio-to-midi` 返回指向 `/` 的永久重定向，导航、sitemap、canonical 无旧地址；英语首页承接原核心页内容且不存在关键词意图重复页面。
- Web 单测、lint、typecheck、生产构建、Playwright 全量回归与代码审查 Stage 1/2 全部通过。

**完成证据（2026-08-12）：**

- `pnpm test`：31 个测试文件、135 条测试全部通过；`pnpm lint`、`pnpm typecheck` 与 `git diff --check` 均零错误。
- `pnpm build`：Next.js 16.2.12 生产构建通过，TypeScript 通过并生成 15 个静态页面单元。
- `pnpm test:e2e`：24 条 Playwright 全量回归通过，覆盖英语上传拒绝、失败任务、成功结果、产物失败、中文真实上传/任务/结果、SSR SEO、308 重定向、双语 404、语言切换和 375 px 布局。
- 桌面与 375 px 的英语/中文首页、上传页和示例结果截图已人工复核，无 Loading 残留、页面级横向溢出或控件重叠。
- 修复后由 fresh `code-reviewer` 从 Stage 1 重审：Stage 1/2 PASS，0 HIGH、0 MEDIUM；剩余 locale 分析属性和未使用中文 helper 为非阻断 LOW。

**依赖与风险：**

- App Router 页面迁入 `[locale]` 会同时触及静态页、动态任务页和 metadata；必须一次迁移完整路由矩阵，不能留下只支持单语言的旁路页面。
- locale cookie 只记录用户显式选择并服务站内导航；直接请求无前缀 URL 永远输出英语，避免缓存、canonical 和爬虫结果随请求头变化。
- 临时任务的两个语言 URL 都保持 `noindex`，语言切换不得把高熵任务 ID 写入 sitemap、analytics 文本或公开 alternates。

---

## Phase 29：Basic Pitch 钢琴谱面可读性优化

**目标：** 不替换 Basic Pitch、不改原始模型事件，先消除结构分析只覆盖前 30 秒和弱起被排成空第一小节的问题；其他量化、和弦与声部算法不在缺少固定集证据时混入本轮。

**交付内容：**

- 保留 Basic Pitch 模型、阈值、原始 MIDI 与原始时间线指纹；只升级结构分析配置和 MusicXML 弱起表示。
- 让节拍、拍号与调性分析覆盖产品允许的最长 90 秒输入，继续保存现有 BPM、beat/downbeat grid、拍号/调性候选和置信度。
- 使用 music21 anacrusis 表示首个 downbeat 之前的弱起；左右手即使进入时刻不同或一手为空，也必须共享相同 `paddingLeft` 和小节线，不能制造整小节前置休止。
- 对 16 段固定结构集重新生成产物并运行 music21、OSMD 和 xmllint；新产物必须重置人工评级，禁止沿用旧 13/16 评级冒充签收。

**关键文件：**

- `songdance/api/app/pipeline/analysis.py` — 最长 90 秒音频结构分析窗口。
- `songdance/api/app/pipeline/score.py` — 弱起记谱、版本化重建与 MusicXML 输出。
- `songdance/api/app/pipeline/score_validation.py` — 将 `paddingLeft` 纳入小节时值守恒。
- `songdance/api/tests/test_analysis.py`、`test_score_validation.py` — 90 秒配置、弱起、一手为空、双手错位和解析回归。

**验收标准：**

- 同一音频优化前后 Basic Pitch 模型版本、阈值、原始事件与原始 MIDI 指纹一致；结构分析输入上限从 30 秒提升到 90 秒。
- 弱起样本第一系统不出现只有整小节休止和末端孤立音符的人为空白小节；左右手的 `paddingLeft`、首小节长度和小节线一致。
- 固定结构集的 MusicXML 全部通过 music21、OSMD 与独立 XML 解析，至少 13/16 人工评为“谱面可读”；未完成人工签收时不得把 Phase 29 标为完成。
- API Ruff、pytest、固定结构回归和 `git diff --check` 全部通过；代码审查 Stage 1/2 无 HIGH 或 MEDIUM。Mypy 仅在项目依赖安装后执行，不把缺失工具伪报为通过。

---

## Phase 30：专业评审驱动的琶音结构修复

**目标：** 以专业评审判定为 `needs_redo` 的 `04-arpeggios` 为阻塞样本，先修复假弱起造成的全曲小节线错位，再分别处理延音伪多声部、简单琶音分手与泛音误音；每项独立改动、独立回归，Basic Pitch 原始事件和原始 MIDI 保持不变。

**Task 30.1 · 假弱起否决与小节线重建：**

- 在谱面重建前对候选弱起执行反证：组合起音/重音位置、首段时值占用、拍号网格与后续 8 格周期；完整 4/4 八分音符循环优先解释为完整首小节。
- `04-arpeggios` 第一小节从首个强拍开始，`paddingLeft=0`；按每小节 8 个八分音符重建所有未被音频尾部截断的完整小节，不允许整体错后一音。
- 保留确定性弱起固定用例，防止修复退化为“永远禁用弱起”；版本号和质量报告记录弱起判定结果及证据。真实录音弱起样本仍是后续补充项，不用合成/内存用例冒充真实音频证据。

**Task 30.2 · 延音与声部压缩：**

- 使用独立起音、同音重触与时间重叠证据区分踏板延长和真实复音；没有独立声部证据时压缩为可读主声部，避免为伪声部填充密集休止符。
- 仅在至少 8 个连续密集起音之间均存在未释放尾部能量的音频级踏板证据，或 MIDI CC64 存在时输出踏板标记；孤立重叠和零散共振不生成踏板。
- 增加谱表数量校验：标准钢琴 MusicXML 必须恰好包含一个 Piano `score-part`、一个 `<part>` 和其中两个编号 staff；禁止把左右手各声明成 Piano part，避免 Sibelius 将两个 part 各展开为大谱表而得到四行。简单重复琶音每个 staff 默认一个主声部，只有连续起音、音高分离和持续重叠同时达到阈值时才允许保留额外 voice，真实持续低音或内声部不得被压平。
- 同音高且时间重叠的相邻事件优先视为同一声部延续，禁止用跨声部休止符补齐延音造成的空档。

**Task 30.3 · 简单琶音分手：**

- 对音区明确、周期稳定且无交叉手证据的简单琶音应用稳定音区策略；验证 C3/G3/C4 为左手，E4/G4/C5/G4/E4 为右手。
- 对连续至少 3 次稳定重复的目标音型，按八分音符槽位保留 `C3-G3-C4-E4-G4-C5-G4-E4`，删除同音在错误槽位出现的踏板衰减重识别；该过滤只作用于目标音型音高，独立持续低音、内声部和非目标琶音继续保留。
- 交叉手和中央音区歧义样本继续输出置信度或 `unknown`，不得把简单样本规则扩散为所有钢琴输入的硬切。

**Task 30.4 · 音频感知泛音抑制：**

- 在仍可访问音频频谱的阶段计算整数倍频关系、相对能量和独立起音证据；只有三项同时满足才删除泛音候选，并记录可审计原因。
- 使用真实独立八度音反例保证不会把正常八度和弦删除；不得在只有 MIDI 音高和 velocity 的后处理层声称完成泛音识别。

**关键文件：**

- `songdance/api/app/pipeline/quantize.py` — 弱起反证、周期与小节完整性判定。
- `songdance/api/app/pipeline/pickup.py`、`score.py` — 应用双手共享的弱起小节边界，并记录重建版本和判定证据。
- `songdance/api/app/pipeline/cleanup.py`、音频特征模块 — 延音/泛音的证据化清洗，按 Task 分步实施。
- `songdance/api/app/pipeline/voicing.py` — 简单琶音稳定分手与交叉手保护。
- `songdance/api/tests/test_pickup_decision.py`、`test_score_validation.py`、`test_analysis.py`、`test_voicing.py`、`test_cleanup.py` — 每项独立正反例。
- `songdance/api/tests/fixtures/audio/structure-review.json` — 保存专业评审原文、当前评级和复评状态。

**验收标准：**

- Task 30.1 完成时，`04-arpeggios` 第一小节无弱起、每小节恰为 4/4 的 8 个八分音符格，后续小节线不偏移；现有三个确定性弱起回归继续通过，并明确不将其计作真实录音证据。
- Task 30.2–30.4 各自具备正例与反例；`04-arpeggios` MusicXML 为一个 Piano part 内的高低音两个 staff、每个 staff 一个主声部，完整循环严格为八个目标音且起音格对齐，冗余休止符显著减少；不能用 MIDI velocity 代替音频能量，不能用八度关系单独删除音符，不能给所有钢琴输入硬套中央 C 分手。
- 每个 Task 后重跑 16 段固定结构集并重置受影响产物的人工评级；离线包只负责播放和展示评级表，评审者以截图回传，项目维护者录入正式评级；`04-arpeggios` 必须由专业评审复评到至少“少量修改可用”，否则 Phase 30 不完成。
- API Ruff、pytest、music21/OSMD/xmllint、原始事件与 raw MIDI 指纹、`git diff --check` 和代码审查 Stage 1/2 全部通过；任一已通过样本退化即停止并回滚该 Task 的生产启用。

**依赖与风险：**

- 当前 `04-arpeggios` 为合成固定集，原始生成器明确从 0 秒开始循环 8 个八分音符；这为 Task 30.1 提供确定性真值，但不能单凭该样本泛化到自由速度或真实弱起录音。
- 延音踏板和泛音判断需要音频或 CC64 证据，现有 `NoteEvent` 不包含这些特征；Task 30.2/30.4 必须先扩展证据数据流，不接受纯 MusicXML 层启发式删除。
- Phase 29 的总体 13/16 门槛仍保留，但已知专业 `needs_redo` 样本成为额外阻塞项。

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

## Phase 11–35 需求追踪

| Product Spec | 开发阶段 | 必须交付的证据 |
|---|---|---|
| AC-021 原始证据、清洗计数与原因 | Phase 11、13 | 产物关系、reason code 汇总、清洗回归报告 |
| AC-022 Beat/BPM/拍号/局部调性与证据 | Phase 14、33–34 | 结构真值对比、top-2 候选、终止式/和弦/导音证据、保守调号和耗时报告 |
| AC-023 Chord 与合法多声部 | Phase 15 | music21 结构断言、OSMD 渲染和外部解析器结果 |
| AC-024 左右手分配与 `unknown` | Phase 15–16 | 交叉手样本、分手置信度、结果页假设标记 |
| AC-025 可读谱面门禁 | Phase 11、15 | 至少 16 段固定集、机器校验、至少 13/16 人工可读 |
| AC-026 分层失败与可用产物 | Phase 11、16 | API 部分成功状态和四种结果页 E2E |
| AC-027 可重复性 | Phase 11–15 | 相同版本/配置双跑摘要一致性报告 |
| AC-028 Basic Pitch 谱面可读性优化 | Phase 29 | 原始事件指纹、弱起/量化/和弦/声部回归、解析与人工可读报告 |
| AC-045–AC-047、AC-049–AC-051 结果页谱面定位、选区播放与固定工作台 | Phase 23 | 真实 MusicXML 交互 E2E、播放边界测试、页面/谱面滚动位置证据 |
| AC-048、AC-052–AC-055 实时谱面拖选、取消恢复与边缘滚动 | Phase 24 | RAF 更新计数、真实 MusicXML 拖动中间帧、跨系统/跨页截图与滚动位置证据 |
| AC-056–AC-057 已提交选区的 `↔` 边界调整 | Phase 25 | 首尾命中带组件测试、create/resize 状态机测试、真实 MusicXML 二次调整与取消恢复 E2E |
| AC-029–AC-030 乐器选择与安全路由 | Phase 17 | Profile 注册表、API 白名单、未知模型拒绝和旧任务兼容 |
| AC-031–AC-032 移调乐器与单音谱面 | Phase 18 | 响音/记谱音高测试、单行谱表和无左右手 UI |
| AC-033 吉他标准记谱 | Phase 19 | 复音固定集、八度一致性和无 TAB/Guitar Pro 边界 |
| AC-034 鼓事件与打击乐谱 | Phase 20 | Channel 10（零基索引 9）、GM 映射、鼓件 lane 和解析结果 |
| AC-035 人声旋律边界 | Phase 18 | 主旋律固定集、无歌词输出和范围警告 |
| AC-036–AC-037 逐乐器门禁与钢琴保护 | Phase 18–20 | 每乐器独立报告和完整钢琴回归 |
| AC-038–AC-039 轨道来源与未知乐器边界 | Phase 21–22 | 分轨/AMT A/B、逐轨元数据和 `other` 保护 |
| AC-040–AC-041 部分成功与级联删除 | Phase 22 | 单轨失败/重试 E2E 和对象存储清理证据 |
| AC-042 完整混音生产门禁 | Phase 21 | 逐 program 质量、许可、时延和内存报告 |
| AC-095 结尾音/色度不得单独决定调性 | Phase 33 | G 结尾无 F♯/终止式反例、候选与证据审计 |
| AC-096 完整终止式、候选与保守调号 | Phase 33–34 | 乐句边界终止式、独立证据、top-2 UI、无确定调号 MusicXML |
| AC-097 五声音集合与调式家族分离 | Phase 35 | 成对对抗样本、家族标签、`mode_variant=unknown` 和主音证据 |
| AC-098 单高音谱表与大谱表语义 | Phase 34 | 单旋律/稀疏真实低音正反例、MusicXML staff 数和 OSMD/PDF 渲染 |
| AC-099 小调形态与临时变音 | Phase 34 | A minor 自然/和声/旋律形态混合 fixture、固定调号和逐音 accidental |
| AC-100 主音化与转调分离 | Phase 33 | `V/x→x` 回原调反例、持续新调正例和候选升级审计 |
| AC-101 `07-soft` 四分音符假弱起 | Phase 36 | 首拍完整小节、四分音符周期、后移一拍的小节线和 `paddingLeft=0` |
| AC-102 `07-soft` 导音缺失调号反证 | Phase 36 | 无 F♯ 的 C 大调反例、`leading_tone_absent` 审计和无一升号 MusicXML |
| AC-103 `07-soft` 残响时值隔离 | Phase 36 | 独立起音/beat 时值为四分音符，残响只在 sustain evidence，禁止二分/附点污染 |
| SCOPE-016 混音分离适配器 | Phase 21–22 | 技术门禁、隔离 Worker、多轨编排和回退报告 |
| SCOPE-018 单乐器模式与路由 | Phase 17 | InstrumentProfile、选择器、兼容 API 和白名单路由 |
| SCOPE-019 单音家族 | Phase 18 | 六类输入逐乐器固定集、模型 A/B 和谱面合同 |
| SCOPE-020 吉他标准记谱 | Phase 19 | 复音转录、八度记谱和无 TAB 边界 |
| SCOPE-021 鼓转录 | Phase 20 | 鼓事件、GM MIDI、鼓件 lane 和打击乐谱 |
| SCOPE-022 完整混音多轨 | Phase 21–22 | 分轨/直接 AMT 门禁、多轨 UI、部分成功和删除 |

**交接顺序：** 当前共享流水线先冻结 Phase 32 已完成的调号/量化/织体实现和固定集指纹，完成 Phase 36 对 `07-soft` 的三项失败复现与自动回归，再按 Phase 33 → 34 完成 P0 局部调性与记谱修订；Phase 35 是独立 P1，不阻塞后续多乐器。Phase 36 与 Phase 33–34 不并行修改 `analysis.py`、`quantize.py`、`score.py`；修复后的 `07-soft` 必须重新生成人工评审包，专业复评至少达到 `minor_edits` 才能解除该样本阻塞。随后严格按 Phase 17 → 18 → 19 → 20 → 21 → 22 推进多乐器。每个乐器过门禁后才能在选择器中启用；不得为了等完整混音而阻塞已通过的单乐器能力。每个 Phase 单独提交，不允许把真值集、调性算法、谱表结构和非西洋模式混进一个不可归因的提交。

**停止条件：** 任一候选算法未达到对应乐器数值门槛、结构严重错误增加、固定集人工评级下降、许可不明确、超出资源预算，或破坏旧钢琴任务/下载 API，即停止该乐器晋级并保留上一版本。一个乐器失败只阻塞该乐器；完整混音失败不回滚已上线单乐器能力。生产默认值只能来自固定回归报告，不得凭示例页截图调整。

---

---

## Phase 31：八种语言国际化扩展

**目标：** 在保留英语无前缀 URL 与简体中文 `/zh` 兼容路径的前提下，增加日语、韩语、西班牙语、巴西葡萄牙语、法语和德语，所有语言共享页面组件、业务行为和 API 错误码映射；首批完成入口核心文案，其他 namespace 以独立英语基线交付。

**交付内容：**

- 将公开 route locale 固定为与 URL 段一致的 `en`、`zh`、`ja`、`ko`、`es`、`pt-br`、`fr`、`de`，服务端消息与 LanguageTag 再映射为 `en`、`zh-CN`、`ja`、`ko`、`es`、`pt-BR`、`fr`、`de`，避免大小写不同的内部 rewrite 重复进入 proxy。
- 为八种语言提供物理且 key 完全对齐的消息目录；新增语言先覆盖入口核心文案，其余 namespace 使用可审计的英语基线；语言切换器显示本地化语言名称，切换时保留逻辑路径、任务 ID、查询参数和 hash。
- 扩展稳定公开页面的 canonical、`hreflang` alternates、英语 `x-default` 和 sitemap；任务 URL 继续 `noindex` 且不进入 sitemap。
- 保持 API 只返回稳定结构化状态和 `error_code`，所有用户可见错误由当前 locale 的 Web 消息目录渲染。
- 增加消息 key 对齐、八语言 SSR HTML、动态任务路径切换、SEO metadata/sitemap 和 375 px 语言选择器回归测试。

**关键文件：**

- `songdance/web/src/i18n/routing.ts`、`request.ts`、`messages.ts`
- `songdance/web/messages/*.json`
- `songdance/web/src/components/language-switcher.tsx`
- `songdance/web/src/lib/seo/locale.ts`、`src/app/sitemap.ts`
- `songdance/web/e2e/i18n.spec.ts`、`src/i18n/messages.test.ts`

**验收标准：**

- 八种 locale 的首页和工具入口在不执行客户端 JavaScript 时输出核心对应语言 HTML；上传、处理中、成功、失败、结果、示例、法律页和 404 使用物理基线目录且消息 key 完全对齐，未审校 namespace 的英语状态在交付记录中明确。
- 任意稳定页和 `/jobs/{id}` 在八种语言间切换后保留逻辑路径、任务 ID、查询参数和 hash；375 px 无页面级横向溢出。
- 稳定页面 metadata 与 sitemap 为八种语言生成互相完整的 alternates、正确 canonical 和唯一英语 `x-default`；临时任务 URL 不被索引。
- `pnpm test`、`pnpm lint`、`pnpm typecheck`、`pnpm build` 和 `pnpm test:e2e` 全部通过，且无回归英语/中文现有路径。

**依赖与风险：**

- 八套消息目录必须在 CI 中做叶子 key 对齐和空值检查；缺少物理目录或 key 时阻塞发布。英语基线必须显式存在，不能由运行时缺 key 静默生成。
- 新 locale 的 URL 前缀与 BCP 47 `lang` 值必须固定，避免 sitemap、cookie 和 metadata 产生别名 URL。
- 本 Phase 不改 API、任务数据模型或音频处理逻辑；翻译质量由上线前人工抽检负责。

**完成证据（2026-08-17）：**

- `pnpm test`：31 个测试文件、135 条测试通过；`pnpm lint`、`pnpm typecheck`、`git diff --check` 通过。
- `pnpm build`：Next.js 16.2.12 生产构建通过，45 个静态页面单元生成。
- `pnpm exec playwright test e2e/i18n.spec.ts`：4/4 通过，覆盖六个新增 locale 的首页、工具入口和 375 px 布局。
- `pnpm exec playwright test e2e/seo.spec.ts`：4/4 通过，覆盖八语言 SEO 基线、sitemap、任务 noindex 和 404 状态。
- fresh `code-reviewer`：Stage 1/2 PASS，0 HIGH、0 MEDIUM；locale 埋点为既有 SHOULD 级 LOW 建议。
- 完整 E2E 仍有既有谱面小节定位用例的渲染失败（`phase7`、`quality-result`），不涉及本 Phase 文件；已单独记录，不以国际化测试通过冒充全套回归通过。
- 路由回归修复：新增 locale 的 route id 与公开 URL 段保持一致，`/pt-br` 不再经 `/pt-BR` 内部 rewrite；国际化 E2E 对六个新增 locale 的首页和工具页显式断言 HTTP 200，SEO E2E 对八个 locale 的 404 状态逐项断言。

---

## Phase 32：初级公开示例与快速音型质量门禁

**目标：** 将已被新评审判为 `needs_redo` 的莫扎特复杂片段保留为失败对照并按参考谱继续修复，同时准备带真实演奏、明确授权和参考谱的初级钢琴默认示例；把调号、短时值、密集起音和双谱表分配拆成独立可测问题，不用换曲或单个专家的口头建议绕过算法缺陷。

**Task 32.1 · 当前示例降级与持续修复：**

- 将 `03-mozart-sonata` 当前产物正式记录为 `needs_redo`；当前评审覆盖 2026-08-06 的历史 `minor_edits`。
- 发布器接受 `needs_redo` 作为有效评审记录；示例页显示醒目的失败警告，同时继续加载原音、MusicXML、钢琴卷帘和下载产物供对照，不把它渲染为产品质量证明。
- 发布门禁增加调号、短时值分布和 staff 密度摘要，失败原因可审计。
- 当前 K.545 以本地参考谱为真值继续保留调号、十六分音型与左右手织体修复任务；人工复评暂时暂停，状态明确记录为 `review_paused`，不视为通过。恢复评审后仍须达到至少 `minor_edits`；新初级示例的上线不能替代该复评。

**Task 32.2 · 初级曲目候选准入：**

- 只评估哈农、车尔尼、拜厄或同等难度的真实钢琴演奏；候选必须有可验证授权、可下载参考谱和稳定单一拍号/记谱调号。
- 为候选建立逐小节参考真值和当前流水线产物，先过解析与结构门禁，再由人工评为至少 `minor_edits`；未过门禁时保持网站示例不可用，不用合成音频顶替。
- 网络检索、下载和授权核验单独留痕；来源不清的录音不进入仓库。
- 当前候选固定为 Freesound `522868` 的 Hanon Exercise No.1 `piano7_ex1_good_good.wav`（真人钢琴演奏，单条页面标记 CC0）；使用 Zenodo `10.5281/zenodo.3898631` 的 CC BY 4.0 数据集交叉核验原始 WAV、起音/色度标注和 LilyPond 真值，并绑定 IMSLP/Mutopia 可下载参考谱。入库前必须固定具体文件哈希与许可快照，实际转录和人工评级达到 `minor_edits` 前保持 `candidate_pending`。

**Task 32.3 · 调性与记谱调号分离：**

- 数据结构区分 `local_tonal_center`、`notation_key_signature` 和各自来源/置信度。
- 普通上传只凭片段音频时，UI 表述为推断调性；固定示例有参考谱时，MusicXML 的记谱调号必须匹配参考谱。
- 为“作品 C 大调、片段局部 G 大调”的用例增加回归，禁止局部调性感静默覆盖参考谱调号。

**Task 32.4 · 短时值与半速推理实验：**

- 建立分别含十六分、三十二分、六十四分音型的参考真值集，先证明现有固定十六分网格的失败边界。
- 实现可版本化的自适应量化候选，按起音间隔、拍点相位和小节守恒选择分辨率；K.545 参考谱中的十六分音型必须保持十六分。
- 在隔离实验中加入保持音高的 0.5 倍速 Basic Pitch 路径，输出时间缩回原轴，与原速路径比较 note precision/recall/F1、人工可读性、P95 时延和峰值内存；门禁未通过时不接入生产 Worker。

**Task 32.5 · 双谱表织体校验：**

- 统计每小节左右 staff 的起音数、低音域覆盖、音高中心和连续性，发现低音独立起音存在但 bass staff 近乎为空时输出 `STAFF_DISTRIBUTION_SUSPECT`。
- 织体修正候选结合音高层、相邻起音连续性、持续低音与分解和弦模式；保护跨手、内声部和真实延音，不按全曲比例硬搬音符。
- 公开示例必须通过 staff 分布门禁；普通上传触发怀疑标记时保留原始 MIDI 和质量警告，不伪装成已正确分手。

**实施记录（截至 2026-08-27）：**

- Task 32.3 已完成代码与自动门禁；Task 32.5 已完成 AC-078/082 的自动结构验收，Phase 30 只剩 AC-074 的专业人工复评门禁。Task 32.1 已完成失败对照状态与当前结构修复但仍等待完整参考谱逐小节映射：K.545 保持 321 个原始模型音符、321 个清理后音符，左右手/未知事件为 102/218/1；`STAFF_DISTRIBUTION_SUSPECT` 通过，低音分配、低音小节覆盖和高音分配均为 1.0。MusicXML 使用 C 大调、局部调性感继续记录 G 大调、无假弱起。
- 延音伪多声部限制将 K.545 每谱表记谱层数从 3/4 层压到每小节最多 2 层，同时保护跨越至少 3 个独立起音的持续低音；冗余休止符从旧评审文件的 172 个降到 70 个，休止符密集小节从 15/17 降到 10/17，并删除 18 个纯静默 voice。发布门禁固定为总休止符不超过 80、任一谱表任一小节 voice 不超过 2。
- K.545 新产物继续以 `pending` 发布为失败对照，最近完成评级保留 `needs_redo`，人工复评当前为 `review_paused`；原音、双谱表、钢琴卷帘和下载产物继续可见，重新人工评为至少 `minor_edits` 前不得标为可用。
- Task 32.4 已完成三类短时值真值集、自适应量化和隔离半速 A/B。原速 precision/recall/F1 为 0.7991/0.6554/0.7059，半速为 0.7680/0.8216/0.7756，但 precision 下降 0.0311、P95 时延由 52.7ms 增至 172.7ms，因此 `production_eligible=false`，生产模型路径保持原速；K.545 继续按参考谱锁定十六分量化。
- 10 段真人钢琴集与 16 段结构集已按当前流水线重生成并绑定对应指纹：真人集指纹 `d90e769356c22642b8f89f7c2f8794d6bf9159d0f0c809352b34af6e7c58f3e4`，结构集指纹 `ec38a2b251b25fa6a433623bc5e6499778fc5db6fdd5a137f4ab071d9d532fcf`。两套人工评级保持 `pending`（`07-soft` 历史 `needs_redo` 保留）。离线包为 `songdance/api/dist/songdance-structure-review-ec38a2b251b2.zip`，包含 16 份由 OSMD 渲染的 `score.pdf`，SHA-256 `6d3ba577842968d8c4a51515124af528c5af6fa28f01c1ca7be545c920bdafcf`，完整性检查和 PDF 解析通过；OSMD、Redis、本地 HTTP 在正常环境复跑通过。API 全量回归 `410 passed, 6 skipped`。
- 当前 `04-arpeggios` 证据：117 BPM、4/4、清理前 326/清理后 282、通用谐波候选移除 44，14 个稳定八音循环、119 个匹配槽位；`simple-arpeggio-filter-v8` 在记谱层删除 163 个证据化别名，其中稳定跨周期泛音 86、无独立能量增长的周期尾音 74、尾音可测 harmonic pair 3，最终记谱音严格为 119。稳定泛音必须跨至少 3 个完整周期并形成至少 3 个槽位的整体音色轮廓，尾部不完整周期不能增加 recurrence count；删除还要求候选不构成能量/力度一致的独立音，或候选结束后的高频/基音倍频跟踪比不低于 0.30，证明高频继续随基音存在。真实短八度跟踪比为 `0.0056–0.0096`，自然三次泛音约 `1.01`，04 的 G3→G4 自然泛音为 `0.316–0.696`；基音尾部不可测时返回 `None` 并保留。连续 3 槽真实平行八度线、单槽高/低置信度真实八度、跨手音、持续低音与稳定平行声部均受保护。周期尾音必须来自最近 3 槽内的目标音型真实起音，频带增长不超过 1.35、力度比不超过 1.1、时长比不超过 3.1；每条删除保存跨周期次数或距上次起音槽数以及能量/力度/时长/倍频跟踪证据。产物为单 Piano part、双谱表、两个 staff 每小节最大 voice 均为 1；前 14 个完整小节逐音严格等于目标八音循环，右手每小节开头为 1 拍四分休止，左手第一拍由 C3/G3 两个八分音符填满后使用从 offset 1.0 开始的 3 拍整拍边界休止；1 个 `mp`、1 个踏板区间（2 个 XML 端点），无未知声部。AC-078/082 自动验收已通过，AC-074 仍必须等待专业评审至少评为 `minor_edits`，不能用自动门禁替代人工结论。K.545 公共示例 provenance 保持 `review_status=pending`、`review_state=review_paused`、恢复条件 `reference_aligned_transcription_ready`，最近完成评级 `needs_redo`。
- Petzold BWV Anh.114 曾完成来源固定、产物生成与评审包，但 2026-08-22 人工评审确认装饰音占用正拍并引发节奏偏移，且低音自然泛音形成多余高音；候选已改为 `candidate_rejected + needs_redo`，旧评审包撤出有效产物目录，保留 fixture 作为阻塞回归，不得重置为待发布候选。
- Petzold 清理仅在 `human_review` 明确证据下删除两处误识别泛音，并保存起止时间、起音差、速度比、时长比和判定来源；通用低音基频优先删除默认关闭，音频证据不可用时不得按八度或泛音列机械删音。装饰音缺少逐音真值时输出 `ORNAMENT_REVIEW_REQUIRED` 并阻塞发布，不自动猜测 grace note。
- 下一候选改为 Freesound `522868` 的 Hanon Exercise No.1 `piano7_ex1_good_good.wav`：预览音频 12.919 秒，SHA-256 `20dd58a626fcf928981df6a363f59669d6755290fa0c52001182629add71d860`，已检测 32 个起音组；后续仍须下载并固定原始 WAV、许可快照、Zenodo 标注真值和 IMSLP/Mutopia 参考谱，再运行当前生产流水线并生成人工评审包。
- Petzold 修正使既有固定集指纹按预期失效；重生成时发现 `04-arpeggios` 因通用泛音保护收紧而每周期多出一个 MIDI 79 假高音。`simple-arpeggio-filter-v7` 只在稳定重复周期、踏板覆盖与同一音符的起音/STFT 泛音对证据同时成立时删除候选，禁止跨周期复用同 velocity 证据；无音频证据时保留，并使用原始起音能量/力度一致性下界、时长归一化一致性区间与候选结束后的短窗频带尾音共同区分自然泛音和真实独立攻击。`harmonic-evidence-v4` 让通用 `extract→clean` 与简单琶音过滤共用同一保护逻辑，并为每个起音保存探测窗前后频带能量；真实短八度或十二度结束后高频能量应明显下降，自然泛音则继续随尚未结束的低音存在。尾音比先扣除起音前稳定噪声底，相邻同音占用探测窗、尾音不可测或同音没有实际重叠时保守保留；普通和弦音程不会进入整数泛音候选。由此保护强真实八度、带独立攻击的弱同时八度/十二度/和弦（包括时值短于同时低音的独立音）、弱但有独立起音的跨手音、单槽和弦、稳定平行声部与持续独立声部，同时删除证据完整的自然泛音。fresh Stage 1 审查先后发现的事件数量分叉、尾音不可测删除、删除无审计、同音历史误删，以及通用清理未强制力度比/时长比均已修复；等力度中音区强奏八度即使频带能量较弱也必须保留。`arpeggio_audit.py` 已加入固定集流水线哈希，任意审计逻辑变化都会使评审指纹失效。
- K.545 参考真值新增独立合同文件，固定当前音频指纹、IMSLP 公版 MIDI 的来源 URL、文件 SHA-256、73 小节完整覆盖、C 大调、十六分最短时值和当前 17 个产物小节到参考小节的有序映射；发布 provenance 保存合同指纹与验证摘要，G 大调、32 分量化、staff `suspect/not_evaluated`、参考文件缺失或映射缺项/乱序/越界的反例全部阻塞。普通上传结果页同时标明自动分析为“推断调性”，并把 `STAFF_DISTRIBUTION_SUSPECT` 显示为可见校对警告。
- 上一轮发布门禁已能核对 timeline 顶层、`notation`、`reconstruction` 语义副本和最终 MusicXML 的实际 `<fifths>`/`<type>`；当时 music21 参考谱仅含第 1–12 小节，第三次 fresh `code-reviewer` 因缺少完整参考谱逐小节映射判定 Stage 1 FAIL。该历史缺口不再作为当前真值来源，也从未用于撤下或替换 K.545。
- 已将用户下载的 IMSLP `PMLP1855-sonata-in-c.mid` 固定为仓库 fixture（format 1、2 个声部、73 小节、4/4、C 大调、SHA-256 `e3ec5b0110ff11ff7ee0f39c8cf9aa80a8d05a7d1fd9b43f9ce5a579061641ea`）；合同记录固定音频起点到参考第 1–17 小节的 17 项顺序映射，并校验 17 个 downbeat、68 个四分音符窗口与音高类别比对摘要。发布器改为离线解析该 MIDI，拒绝旧 music21 12 小节 corpus 和任何缺项/乱序/越界映射。
- 上一轮 K.545 最终回归：API 全量为 354 passed/6 skipped，沙箱内失败的 Redis、本地 HTTP 与无头 OSMD 3 个环境用例在沙箱外单独复跑全部通过；公开示例定向测试 49 passed。Web 单测 140 passed，TypeScript、ESLint、Next.js 45 页面生产构建、Ruff 与 `git diff --check` 通过；发布器 fresh `music21`、`xmllint`、OSMD 均通过并更新 provenance。Web E2E 恢复为 26 passed：Playwright API/Worker 使用每次运行独立的临时 SQLite/storage/temp、唯一 RQ 队列和 Alembic `upgrade head`，公开失败示例保留 `pending / needs_redo` 与 mapping unavailable 对照；可映射 MusicXML 浏览器回归保留真实 K.545 音符事件，仅用可审计的 17 小节 score-time 合同网格覆盖小节导航、选区和循环回绕。

**关键文件：**

- `songdance/api/scripts/publish_public_example.py`、`tests/test_public_example.py`
- `songdance/api/app/pipeline/analysis.py`、`analysis_features.py`、`quantize.py`
- `songdance/api/app/pipeline/voicing.py`、`score_validation.py`、`score_io.py`
- `songdance/web/src/app/examples/example-client.tsx`、`example-job.ts`
- `songdance/api/tests/fixtures/audio/` 下新增初级真实演奏与短时值真值清单

**验收标准：**

- 当前 `needs_redo` 莫扎特产物以失败对照继续可见，历史评级不能覆盖新评审；修复任务保持打开，人工复评可暂时暂停但恢复后仍须按参考谱复评通过。
- 新示例同时通过来源授权、参考谱、当前人工评级、music21/xmllint/OSMD、调号/拍号、短时值和 staff 分布门禁。
- 自适应量化与半速候选分别有正反例；没有 note F1、可读性和时延证据时生产路径保持不变。
- API/Web 全量测试、类型检查、lint、编译、OSMD 与 PDF 视觉复核通过；完成后 spawn `code-reviewer` 从 Stage 1 开始独立审查。

**依赖与风险：**

- 仅凭 30 秒音频无法可靠恢复整部作品的原谱调号；参考谱覆盖只适用于来源已知的固定示例，不能伪装成通用模型能力。
- 时间拉伸可能改善起音分离，也可能产生瞬态伪影并把推理成本翻倍；未过 A/B 不进入生产。
- Hanon No.1 已完成来源级候选核验，但尚未固定原始 WAV、参考真值、当前转录产物和人工评级；在这些证据齐全前 Task 32.2 仍处于开发中，不得标为可用示例，也不阻塞 K.545 的独立修复与失败对照展示。

---

## Phase 33：局部调性证据、主音化判定与候选校准

**目标：** 用带真值的乐句、终止式、和弦、低音、导音和特征音证据替代“色度模板第一名等于调性”的旧路径；先生成可审计、可弃权的局部调性候选，不在本阶段直接改变用户谱面的调号。

**Task 33.1 · 独立局部调性真值集：**

- 建立至少 20 段局部调性固定集：至少 12 段来自带许可、音频指纹和可追溯参考谱的公版真实演奏，至少 8 段为受控对抗样本；被测算法不得生成自己的真值。
- 为每段保存片段边界、乐句边界、和弦/低音摘要、终止式类型、主音、major/minor、原谱调号、局部调性、一次主音化或持续转调标签，以及人工复核来源。
- 覆盖正格终止、半终止/未终止、G 结尾但无 F♯/属功能、一次 `V/x→x` 后回原调、延续到下一完整乐句的新调、自然/和声/旋律小调形态并存和 C/G 等近邻调混淆。

**Task 33.2 · 版本化调性证据引擎：**

- 保留 `librosa` 色度模板输出作为 pitch-class 先验，新增基于清洗后音符、beat/downbeat 与和弦聚合的乐句级证据；输出终止式、和弦根音/三音、低音进行、导音/特征音、结构重音主音回归和反证。
- 将孤立 `V/x→x` 标记为 tonicization evidence；只有新主音延续到后续完整乐句或获得第二个独立终止证据时，才升级为稳定局部调性候选。
- 生成不超过两个候选、归一化候选权重、候选差、证据版本和 `notation_eligible`；色度第一名不得绕过证据门禁直接变成确定调号。

**Task 33.3 · 校准、回退与兼容合同：**

- 用固定集校准 top-1、top-2、候选权重和候选差阈值；阈值集中进入类型化配置和版本指纹，禁止散落魔法数字。
- 扩展时间线和质量报告，保存 `local_tonal_center`、top-2、终止式/和弦/导音/特征音证据、`mode_family`、`mode_variant`、`minor_form_evidence` 和 `notation_eligible`；旧任务缺字段时按“未分析”读取，不伪造 C major。
- 保持 Basic Pitch 原始事件、原始 MIDI、清洗事件和 beat/downbeat 指纹不变；Phase 33 只新增分析结果，Phase 34 才消费它决定记谱。

**关键文件：**

- `songdance/api/app/pipeline/tonality.py` — 乐句、终止式、和声证据及候选聚合。
- `songdance/api/app/pipeline/analysis.py`、`analysis_features.py` — 保留色度先验并输出版本化调性证据。
- `songdance/api/app/pipeline/harmony.py` — 复用和弦/低音结构，不复制另一套和声聚合。
- `songdance/api/app/pipeline/quality.py`、`artifacts.py` — 新分析合同、旧任务兼容与质量报告版本。
- `songdance/api/app/settings.py` — 候选、候选差和写谱资格阈值配置。
- `songdance/api/scripts/evaluate_tonality.py` — 固定集评测、校准和门禁报告。
- `songdance/api/tests/fixtures/tonality/manifest.json` — 音频、参考谱、许可、真值和人工复核清单。
- `songdance/api/tests/test_tonality.py`、`test_analysis.py` — 终止式、主音化、转调、反证和兼容回归。

**验收标准：**

- AC-095 与 AC-100 通过：G 结尾无终止式/导音不得写成 G major；一次 `V/x→x` 后回原调不得判转调，持续到下一完整乐句或第二个终止证据才可升级候选。
- 至少 20 段固定集全部有独立真值与来源；评测报告记录 top-1、top-2、候选校准误差、弃权率和确定调号误写率，确定调号误写率超过 5% 时 `notation_eligible` 门禁整体失败。
- 相同输入、分析版本和阈值重复执行两次，候选、证据摘要和门禁结果完全一致；原始事件、原始 MIDI、清洗事件和 beat/downbeat 指纹不变。
- 90 秒输入新增调性证据分析 P95 不超过 5 秒，结构分析总预算继续不超过 15 秒；超时或失败时返回最多两个未确认候选或“未可靠推断”，不回退成已确定的 C major。
- API pytest、Ruff、固定集评测和 `git diff --check` 通过；完成后 spawn `code-reviewer` 从 Stage 1 审查数据真值、证据泄漏和回退语义。

**依赖与风险：**

- Phase 33 依赖 Phase 14–16 和 Phase 32 Task 32.3；开始前冻结当前共享流水线与固定集指纹，不与 Phase 32 对 `analysis.py`、`score.py` 的改动并行。
- Basic Pitch 错音会污染和弦与终止式证据；固定集必须同时保存参考谱真值和当前转录输入，分别报告“真值事件上限”与“生产转录实际表现”，不能把上游错音伪装成调性算法错误。
- 本阶段不引入新生产依赖；复用已锁定的 `librosa 0.11.0`、`music21 10.5.0` 和现有和弦聚合。任何新 MIR 模型先走许可与固定集离线审计，不直接进入 Worker。

**实施记录（2026-09-01）：**

- Task 33.2 已交付 `songdance/api/app/pipeline/tonality.py`：支持最多两个候选、top-2 归一化、完整句末三和弦终止式、孤立主音化弃权、导音比例门禁、未知模式拒绝和版本化证据摘要。
- 证据合同包含 `chord_roots`、`chord_triads`、真实最低音 pitch class、结构主音回归、反证、候选差和 `notation_eligible`；无事件/单起音输入均有稳定降级。
- `tests/test_tonality.py` 6 tests passed，Ruff 和 `git diff --check` 通过；独立 `code-reviewer` Stage 1/2 PASS，0 HIGH/MEDIUM。重复分组 helper 和概率四舍五入误差为 LOW，留到后续 Task 处理。

**Task 33.3 实施记录（2026-09-01）：**

- 已将局部调性证据接入 `StructureAnalysis`、`build_score`、timeline 和 quality report；enrichment 只消费清洗事件，原始事件与 raw timeline 不变。
- 旧任务/未执行路径统一返回 `mode_family=unknown`、`tonality_evidence.status=not_analyzed` 和 `minor_form_evidence.status=not_analyzed`；有候选的新结果才标记 `major_minor`。
- 专项测试（analysis + tonality）25 passed，Ruff 与 `git diff --check` 通过；独立 code-reviewer Stage 1/2 PASS，0 HIGH/MEDIUM。额外 OSMD 回归的 Chrome SIGABRT 属环境残余，不归因于本 Task。

**实施记录（2026-09-01）：**

- Task 33.3 已接入 `StructureAnalysis`、`build_score`、timeline 和 quality report：清洗后的 `NoteEvent` 进入 `enrich_analysis_with_tonality`，原始事件与 raw timeline 保持不变。
- 新字段统一为 `tonality_evidence`、`notation_eligible`、`mode_family`、`mode_variant`、`minor_form_evidence`；旧任务/未执行分析明确返回 `unknown` 或 `not_analyzed`，不伪造 C major。
- 专项测试 `analysis.py + tonality.py` 共 25 passed，Ruff 与 `git diff --check` 通过；独立 code-reviewer Stage 1/2 PASS，0 HIGH/MEDIUM。额外回归 `pickup + score_validation + pipeline` 为 45 passed、1 failed，唯一失败是宿主 Chrome 导致 OSMD SIGABRT，非本 Task 引入。

**Task 33.1 状态记录（2026-09-02）：**

- 已提交局部调性固定集评测器基础设施（`8401722`），专项测试 8 passed，Ruff 与 `git diff --check` 通过。
- 已收集 11 段技术候选录音；其中 Mozart K.545、Chopin Op.28 No.7 和 Haydn Hob. XVIII:11 已核验参考谱来源与文件哈希，但均未完成片段级人工音乐真值。
- 人工标注暂缓；候选资料保存在 `tmp/tonality-candidates/`，不进入正式 `tests/fixtures/tonality/manifest.json`，不计入固定集指标。
- 当前正式可用真实样本数为 0，Phase 33.1 保持未完成；恢复人工确认后统一补录乐句边界、终止式、局部调性、对齐和 reviewer 信息，再运行固定集门禁。

---

## Phase 34：保守调号、小调临时变音与语义谱表输出

**后续子任务：11-waltz-34 复合拍 6/8 记谱合同（实现待开始）**。参考 PDF 已确认该样本应按 6/8 处理：左手 `do-fa-sol-re` 每音占 3 个八分音符，右手每小节 6 个八分音符槽并保留参考谱空位。旧 `11-waltz-34` 的 3/4 产物保留为对照，不覆盖旧真值。

- 先固定参考 PDF 页图、音频起音、左右手音高和每小节映射，形成独立真值 MIDI/manifest。
- 增加显式 `compound_68_reference` 上下文，分离检测拍号/BPM 与参考记谱拍号/BPM，保持绝对播放时间不变。
- 验收：MusicXML/PDF 为 6/8；每小节 6 个八分音符单位守恒；左手每音 3 个八分音符；右手空位/音符顺序匹配参考；一个 Piano part 内两个 staff，无额外声部休止符；旧 3/4 回归不退化。
- 参考来源：:codex-file-citation{path="/Users/lixinyue/Desktop/11-waltz-34 - 完整乐谱.pdf" purpose="source"}。本轮尚未修改模型、普通上传或最终评审包。

2026-09-11 统一产物：当前评审包为 `songdance/api/dist/songdance-structure-review-c55e9f7661cb.zip`，SHA-256 `8a12578f8e5ed65069da40bfa776bf291dc9c75d6c9f7cdc468d2e2e732b59`；包含 16 份 PDF。08 已进入 60 BPM/4/4/八分音符/单高音谱表路径，09 已进入单高音谱表路径。人工评级仍 pending，不能标记 Phase 完成。

**2026-09-06 当前子任务：单谱表构建与回读合同**

**后续子任务：09 音尾重识别**。在显式单旋律上下文内，用量化前事件匹配 STFT 起音证据；只有最近同音音尾、新音独立起音、候选频带衰减同时成立才删重识别事件。无证据/真实重击/低音伴奏保留。时值只截断到有证据的下一起音，不改原始 MIDI，不靠每组最大置信度选音；动作逐条写入 reconstruction。完成标准为 09 实际模型 36 个事件到 30 个正确起音、音高序列与真值对应，真实八度/弱音/持续音反例和音尾边界回归通过。仍不重生成固定集或评审包。

- 实施：移除 `_select_monophonic_melody` 的最强候选筛音；新 `melody_cleanup.py` 保存删音和时值变更记录，`onset_decay.py` 以窄带复解调振幅及相位的衰减外推差异保护弱重击。附加证据仅在显式单旋律固定集启用，默认上传路径不启用；无法测量时保留事件。
- 实测先发现单凭 80 ms 窗口净能量下降会误删弱重击，加入合成音频重击反例后修复。当前 09 经生产预处理、Basic Pitch、现有清洗和新记谱路径，36 个原始事件保留 30 个记谱事件，6 次删除有逐事件证据；参考 MIDI 的 30 个音高与起音全部匹配（100 ms 容差），XML 前 29 音为四分音符，末尾截断音不强行补长，单高音谱表且无 fallback。原始事件和模型不变。
- 相关 pytest `208 passed`，追加不同间隔/力度/相位及检测器是否切分父音的 36 组弱重击音频后专项 `56 passed`；覆盖实际 09/10 音频、缺失证据、真实八度/持续低音、单谱表导出和 OSMD。删除还要求父音结束与候选起点相接（80 ms 容差），衰减振幅/相位差上界收紧到 0.05，阈值随审计输出。变更相关 Ruff、TypeScript、`git diff --check` 通过。此结论只覆盖已测样本及显式上下文，不构成未知录音泛化能力或专业人工签收。

**后续子任务：08 均匀八分音符记谱（未打包）**。固定上下文 `eighth_note_melody` 仅用于该结构回归样本：参考老师确认的 4/4、每拍两个八分音符，强制记谱拍号/量化来源为 `expert_review`，但保留分析 BPM 与绝对秒时间；含低音或明确左手的反例不折叠。该提示不扩展为普通上传自动拍号识别。

- 已接入 manifest 上下文和 runner 传递：08 固定 4/4/四分拍网格的专家来源与八分音符样本提示，10 等含低音输入不使用该提示。相关单测/流水线 `95 passed`；单谱表 OSMD 测试唯一失败为当前 Chrome 沙箱 `SIGABRT` 启动限制，xmllint 和 MusicXML 回读通过。正式 runner 重生成前不刷新固定产物。

**后续子任务：06 三音和弦候选（独立候选，未入固定集）**。保留旧四音 `06-sustain`；新 `06-sustain-triad-v2` 使用老师确认的 `G3-C4-E4 / A3-C4-F4 / G3-B3-D4`。全量审计必须满足 `45 真值匹配 + 34 额外 = 79`，音程关系只作假设，删除必须经过通用音频证据。默认清洗 F1 为 `0.789474`；0.60 速度比实验虽提高到 `0.849057`，但误删真实低音八度，已判定不具备生产资格。普通上传配置不变。

- 06 候选审计已补齐 45 个真值匹配对的 truth/raw、候选数、起止误差和各策略决策；每个真值只有一个匹配候选，最大起音误差 0.01161 秒，三套策略均保留全部 45 个真值。构建器改为只消费版本化 manifest 的 ID、pattern、时长、采样率、噪声、带宽和 seed。专项 `24 passed`，Ruff、`git diff --check` 通过，独立 Stage 1/2 审查 0 HIGH/MEDIUM。PDF 有效但未人工签收，未加入最终评审包。

**后续子任务：10-device 低音带宽/力度配对实验（独立候选，未入固定集）**。以同一 `two_hand` MIDI 建立全频/180–5500 Hz 带限 × 标准/弱低音的 2×2 固定实验，四组共享噪声等级和 seed。分别报告低音、右手及全体的原始/清洗 precision、recall、F1、具体漏音和输入哈希，并计算带宽效应与力度效应。实验只判断问题来自输入退化还是 Basic Pitch，不改模型阈值、预处理或生产路由，不生成最终评审包。

- 10 配对实验已改为共享 unit bass/treble stem、noise 和固定 master gain；噪声在带宽过滤前加入，四组只改变声明的低音增益和带宽。报告绑定 source/normalized 频谱、C2/F2/G2 基频 RMS、raw/cleaned 指标、cleanup 原因、score/voicing/staff 分配、manifest/代码/输入哈希。
- 修正后的原始低音召回：full-standard `1.0`、full-weak `1.0`、device-standard `1.0`、device-weak `0.966667`，仅漏 20 秒 C2；四组右手召回均 `1.0`，清洗低音召回差值均 `0`。唯一结论为 `BANDLIMITED_WEAK_BASS_INTERACTION`，范围限定为合成端到端预处理实验，模型与生产变更均为 false。
- 旧报告曾把内存 notation_events 与最终 MusicXML 混用，显示出错误的 28/30、25/30。现已改为直接读取 music21 最终谱面并使用独立的 130 ms 量化容差；四组最终谱面均匹配 30/30。该评估口径修复不改变原始模型召回指标，也不放宽原始 100 ms 门禁。
- 专项 `12 passed`，Ruff、`git diff --check` 通过；独立复审关闭原 3 HIGH/1 MEDIUM，当前 0 HIGH/MEDIUM。未人工听辨，不能外推真实录音或 Basic Pitch 的普遍能力。

- 原“量化层低音起音保持”阻塞已解除：最终 MusicXML 实物逐音匹配为四组 30/30；报告保存 score.musicxml 哈希、matching_source 和量化容差说明。无需修改生产 BPM/量化算法，后续只保留 7 秒 C2 的原始/量化时间差诊断。

- 配对评估器现保存四组最终 `score.musicxml` 及哈希；报告由实际 music21 score offsets 计算，四组谱面均匹配 30/30。原始模型仍用 100 ms 门禁，谱面量化单独用 130 ms 容差并在报告中标明，二者不混算。
- 配对实验验证 `8 passed`、Ruff 与 `git diff --check` 通过。正式修复前不改生产 BPM/量化、不重新生成最终评审包。

- 接通显式单旋律上下文的单 Piano part/高音谱表、结构校验、MusicXML 写出与回读及降级路径；默认双谱表继续严格校验。
- 验收：单谱表无空低音、无意外 fallback；导出再解析保留音符；真实双手、持续低音和非法谱表有反例验证。
- 此子任务只交付布局支持，现有 fixture 的 `texture_hint` 不代表自动音频判定能力；先前按最强候选筛音也不构成已验证的泛音修复。09 音尾/伪起音仍需独立验证。
- 所有批次修复完成后统一生成评审包，本轮仅在临时目录生成测试产物，不刷新固定集或发行 ZIP。
- 子任务实现结果：单谱表使用普通 Piano Part 和高音谱号，双谱表继续使用两个 PartStaff/StaffGroup；结构摘要、MusicXML 回读和 fallback 已接通，显式左手/低音输入拒绝折叠。布局来源记录为 `fixture_texture_hint`，版本 `explicit-staff-layout-v1`。
- 当前验证：单谱表及 score/voicing/pipeline/pickup/sustain 相关回归 `123 passed`（含真实 OSMD 和 xmllint），变更相关 Ruff、Web `tsc --noEmit`、`git diff --check` 通过。未执行整套 Web E2E 或人工 PDF 签收，不代表 Phase 34 完成。
- 共享流水线变更使旧真人/结构集指纹过期是预期门禁行为；暂不绑定旧产物到新代码，不更新人工评级。统一重生成时再重新验证、绑定指纹和打包。

**目标：** 只把 Phase 33 已达到写谱资格的局部调性转换为推断调号；证据不足时保留临时变音和最多两个候选，同时按演奏者可读性在全段单高音谱表与钢琴大谱表之间稳定选择。

**Task 34.1 · 可空记谱调号与小调语义：**

- 将 `local_tonal_center`、`notation_key_signature` 和各自来源/置信度继续分离；参考谱/用户输入优先于局部推断，普通片段只有 `notation_eligible=true` 时可使用 `inferred_local_tonality` 调号。
- 支持“没有确定调号”的记谱状态：MusicXML 可以为渲染兼容序列化 0 个升降号，但质量报告和 UI 来源必须为 `unspecified/default`，不得显示成已识别 C major。
- 小调只输出“主音 + minor”；自然、和声、旋律小调倾向留在诊断证据，常规小调调号保持不变，升高的第六/第七级按实际音高写临时升降号。

**Task 34.2 · 单谱表/大谱表语义决策：**

- 在记谱事件稳定后计算一次全段 `staff_layout`，同一片段不得中途切换谱表数量；决策保存版本、支持证据和反对证据。
- 只有去除装饰音后整段为功能性单旋律、没有同时持续的独立声部/真实左手织体，且最低音不低于高音谱表第三条下加线时，生成一个 Piano part 和单一高音谱表。
- 任一完整乐句存在经音高层、起音连续性和织体共同确认的独立低音或左手伴奏时，全段保留同一 Piano part 内的高低音大谱表；`04-arpeggios`、K.545 和真实持续低音回归不得被折叠。
- 扩展 MusicXML 结构校验、导入校验和 PDF/OSMD 渲染，使合法结果同时接受一谱表或大谱表，但继续拒绝两个 Piano part 展开成四行的旧缺陷。

**Task 34.3 · 候选展示与旧任务兼容：**

- 结果页最多显示两个局部调性候选和校准权重；证据不足时固定显示“请根据完整音频确认主音”，并区分“推断调性”“参考谱调号”“未确定调号”。
- 八种语言共享同一候选/调号状态合同；新增消息 key 时同步八个物理目录，未审校语言使用显式英语基线，禁止运行时缺 key 回退。
- 旧任务只有 `key_signature` 时继续按旧产物展示并标记 legacy；不得回写新证据、改变旧 MusicXML 下载或使结果页解析失败。

**关键文件：**

- `songdance/api/app/pipeline/notation_context.py`、`score.py` — 可空调号、来源优先级与调性候选消费。
- `songdance/api/app/pipeline/score_construction.py` — 小调临时变音和一/双谱表 MusicXML 构建。
- `songdance/api/app/pipeline/staff_layout.py` — 全段单旋律、大谱表证据与版本化决策。
- `songdance/api/app/pipeline/score_validation.py`、`score_io.py` — 一/双谱表结构、调号来源和外部解析校验。
- `songdance/api/tests/test_notation_context.py`、`test_score_validation.py`、`test_pipeline.py` — 调号、小调和 staff 正反例。
- `songdance/web/src/lib/result/quality-report.ts` — top-2、来源、候选权重与 legacy 解析。
- `songdance/web/src/components/result/quality-summary.tsx` — 推断调性、未确定调号和候选提示。
- `songdance/web/messages/*.json`、`web/e2e/quality-result.spec.ts` — 八语言状态和真实结果页回归。

**验收标准：**

- AC-096、AC-098、AC-099 通过：完整终止式加独立证据可写推断调号；证据不足不写确定调号；A minor 的 F♯/G♯ 使用临时升号且调号不变；单旋律输出单高音谱表，任一真实低声部让全段保留大谱表。
- K.545 的参考谱调号继续覆盖局部候选；普通上传不把 `unspecified/default` 0 个升降号显示成 C major；候选最多两个且提示文案存在。
- `04-arpeggios`、K.545、交叉手、持续低音和稀疏左手固定集继续输出一个 Piano part 内的双谱表；纯单旋律正例输出一个 Piano part/一个 staff，且所有产物通过 music21、xmllint、OSMD 和 PDF 视觉复核。
- 旧任务、旧质量报告和旧 MusicXML 下载保持可用；API/Web 全量单测、Ruff、TypeScript、ESLint、生产构建、八语言 key 对齐和 Playwright 通过。
- 完成后 spawn `code-reviewer` 从 Stage 1 审查调号误写、旧任务兼容、staff 丢音和 UI 误导文案；任何一个已通过样本退化即回 Phase 33 修正证据或本 Phase 修正记谱，不以提高弃权率掩盖。

**依赖与风险：**

- music21/OSMD 可能把未指定调号序列化或解释为 C major；必须同时检查原始 XML、质量报告来源和用户文案，不能只看渲染画面。
- 当前 `score_validation.py`、`score_io.py` 和多项测试固定假设两个 `PartStaff`；扩展时必须保留双谱表严格合同，再增加单谱表合法分支，不能放宽成任意 part/staff 数。
- Phase 34 与 Phase 33 顺序执行，不同时修改 `analysis.py`、`notation_context.py`、`score.py`；模式家族不在本 Phase 顺手实现。

---

## Phase 35：非西洋调式家族 P1 研究与生产门禁

**目标：** 在不破坏 major/minor P0 的前提下，研究并按独立真值集识别 `Chinese pentatonic`、`Japanese miyakobushi`、`Blues` 家族；首版不强猜宫/商/角/徵/羽或布鲁斯大小调变体。

**Task 35.1 · 模式家族真值与反例：**

- 每个家族建立至少 8 段独立固定样本，其中至少 4 段为带许可、参考谱/权威分析和人工复核的真实演奏，至少 4 段为受控正反例；保存音阶集合、旋律音程分布、主音证据和家族标签。
- 固定中国五声与西洋大调共享 `do/re/mi/sol/la` 的配对反例，包括 `1-3-5-5-6-5 / 3-1-5-5-5-3-1`；禁止用五个 pitch class 直接决定家族。
- 为主音保存乐句终止/停驻、结构重音回归、稳定低音或持续音证据；至少两类证据一致才输出主音，否则家族可成立但 `tonic=unknown`。

**Task 35.2 · 隔离分类与弃权：**

- 在 Phase 33 候选合同上增加版本化 `mode_family` 评分，使用 pitch-class 集合、旋律二/三度进行、显著跳进、结构重音与主音证据；major/minor 和三个 P1 家族使用同一候选/弃权框架。
- 首个生产合同只输出 `Chinese pentatonic`、`Japanese miyakobushi`、`Blues` 或 `unknown`；`mode_variant` 固定为 `unknown`，宫/商/角/徵/羽与布鲁斯大小调变体不进入 UI 或确定调号。
- 使用独立 feature flag 运行离线/灰度评测；门禁未通过时生产继续只显示 major/minor 或未可靠推断，不允许 P1 标签污染调号。

**Task 35.3 · 评测、展示与回退：**

- 输出每家族 precision/recall/F1、macro F1、高置信误标率、弃权率、主音准确率和 P95 时延；保存逐样本证据与反证。
- 只有 macro F1 不低于 0.80、任一家族高置信误标率不高于 5%、主音不满足两类证据时能够弃权，才允许开启生产标签。
- 结果页只显示家族与可选主音，不显示未经验证的细分变体；低置信度统一显示“未可靠推断”，不生成模式专属调号。

**关键文件：**

- `songdance/api/app/pipeline/mode_family.py` — 家族特征、候选评分、主音证据和弃权。
- `songdance/api/app/pipeline/tonality.py`、`quality.py` — 复用 Phase 33 合同并隔离 P1 版本。
- `songdance/api/app/settings.py` — P1 feature flag、阈值和版本配置。
- `songdance/api/scripts/evaluate_mode_family.py` — 家族/主音指标与生产门禁。
- `songdance/api/tests/fixtures/mode-family/manifest.json` — 三家族真实样本、受控反例、许可与真值。
- `songdance/api/tests/test_mode_family.py` — 五声音集合冲突、主音证据、弃权和 major/minor 保护。
- `songdance/web/src/components/result/quality-summary.tsx`、`messages/*.json` — 家族标签、未知状态与八语言基线。

**验收标准：**

- AC-097 与 Q-011 合同通过：共享五声音集合的两段不会被机械判成同一家族；首版只显示家族，细分变体保持 `unknown`。
- 每个家族至少 8 段独立真值，macro F1、高置信误标率、弃权率和主音准确率达到门禁；任何一个家族失败只关闭该家族，不影响 major/minor 与其他已通过家族。
- P1 feature flag 关闭时 API、时间线、质量报告和 UI 与 Phase 34 完全一致；开启但低置信时不写模式标签或调号。
- API/Web 全量检查、固定集报告、八语言 key 对齐、OSMD/PDF 回归和代码审查 Stage 1/2 通过后才能标为生产可用。

**依赖与风险：**

- 中国五声、日本都节和布鲁斯不是仅靠音阶集合即可稳定区分的标签；真实样本的风格、和声编配和转录错音可能让分类器学到错误捷径，必须保留配对反例和逐样本人工复核。
- 本 Phase 不新增印度、埃及等体系，也不训练自有模型；任何第三方 mode 模型先审计许可、权重来源、数据偏差和运行成本，未通过只作研究参考。
- Phase 35 是 P1，不能拖延 Phase 33–34 的 major/minor、保守调号和谱表可读性上线。

---

## Phase 36：`07-soft` 专业失败复现与三项结构修复

**目标：** 针对最终离线评审包中 `07-soft` 的真实专业失败，分别修复四分音符型假弱起、无 F♯ 证据却写一升号调号、钢琴残响污染独立起音时值三项问题；不借总体 16 段统计或其他示例通过掩盖该失败样本。

**Task 36.1 · 四分音符完整首小节与弱起反证：**

- 在现有八分音符周期反证之外，增加 4/4 四分音符型检测：首个起音到候选 downbeat 约一拍、首个起音后连续占满至少两个完整四分音符小节时，判定首拍为完整小节并将 `measure_offset_units=0`。
- 保留真实弱起和现有 `04-arpeggios` 反例；弱起判定不能简化为永远关闭。

**Task 36.2 · 导音缺失的调号保护：**

- 对需要升号导音的 major/minor 候选计算真实 pitch-class/和声证据；没有 F♯ 起音或属和弦 F♯ 时，不得把 G major、E minor 等候选直接写为一升号调号。
- `07-soft` 目标结果为 C major/0 sharps（或等价的未确定调号保守路径），质量报告记录 `leading_tone_absent`，不得只靠色度模板候选排序。

**Task 36.3 · 独立起音时值与残响隔离：**

- 以相邻独立起音和 beat 网格决定单旋律基本时值；音频残响只进入 `SustainEvidence`，不得把尾音当作事件 `end_sec` 延长。
- 对单旋律规则四分音符增加正反例：无 CC64/独立低音时，记谱事件保持四分音符；有真实 CC64 或独立持续低音时只保留相应证据和独立声部，不能把整条旋律改成二分/附点音符。

**Task 36.4 · 失败样本重生成与复评包：**

- 将 `07-soft` 的 PDF、离线包内音频/MusicXML/WAV SHA-256 和人工缺陷写入独立 baseline；修复后重跑该样本与 16 段结构集，更新产物指纹。
- 评审包继续显示 `07-soft` 的逐项评级，修复前后的 `needs_redo` 历史不可被 `pending` 覆盖；重评至少达到 `minor_edits` 后才可完成 Phase 36。

**关键文件：**

- `songdance/api/app/pipeline/quantize.py` — 四分音符周期弱起反证和完整首小节对齐。
- `songdance/api/app/pipeline/analysis.py`、`analysis_features.py` — 导音/pitch-class 反证和候选保护。
- `songdance/api/app/pipeline/score.py`、`score_notation.py`、`voice_compression.py` — 调号消费、独立起音时值与残响压缩边界。
- `songdance/api/tests/test_pickup_decision.py`、`test_analysis.py`、`test_sustain_compression.py`、`test_score_validation.py` — 三项缺陷的最小复现与旧回归。
- `songdance/api/tests/fixtures/audio/structure-review-phase36-07-soft-baseline.json` — PDF/包指纹、专业原文、逐项失败状态和恢复条件。
- `songdance/api/scripts/run_structure_review.py`、`structure_quality_gate.py` — 重生成、指纹和评审包绑定。

**验收标准：**

- AC-101 通过：`07-soft` 首小节 `paddingLeft=0`、4/4 时值守恒，后续小节线相对旧产物后移一拍；真实弱起和八分音符完整周期回归继续通过。
- AC-102 通过：无 F♯ 起音/和声证据的 C 大调反例不写一升号，质量报告含 `leading_tone_absent`；参考谱调号覆盖仍优先。
- AC-103 通过：规则四分音符旋律事件保持一拍，残响不制造二分/附点时值；真实 CC64/独立持续低音证据仍保留且不污染其他音符。
- 07-soft 修复产物通过 music21、xmllint、OSMD 和 PDF 视觉复核；16 段结构集重新生成并保存新指纹，任何已有通过样本不得退化。
- API `pytest`、Ruff、Web TypeScript/ESLint/生产构建、`git diff --check` 和 `code-reviewer` Stage 1/2 全部通过；专业复评未达到 `minor_edits` 时保留 `needs_redo` 阻塞并不得标记完成。

**依赖与风险：**

- Phase 36 消费 Phase 29–32 的当前产物，必须先冻结 Phase 32 固定集；与 Phase 33–34 不并行改写相同分析/记谱文件。
- 07-soft 是合成结构集，不代表真实踏板录音；它用于证明算法没有把已知独立起音和结构相位弄错，真实录音仍需后续专业复评。
- music21 可能把 0 sharps 序列化为 C major，因此必须同时检查 `notation_key_signature_source`、`leading_tone_absent` 和最终 XML 的 `<fifths>/<mode>`，不能只看渲染结果。

**实施记录（2026-08-31）：**

- `07-soft` 已按当前代码重生成：`measure_offset_units=0`，弱起反证为 `FALSE_PICKUP_REJECTED_FULL_MEASURE`；调性为 C major/default，并记录 `KEY_SIGNATURE_LEADING_TONE_ABSENT`；记谱音符（排除高音泛音候选）最大时值为 0.743039 秒，MusicXML music21 校验最大四分音符时值为 1.0，超过一拍的事件为 0。
- 新增四分音符完整小节、导音缺失和高音旋律残响截断回归；Phase 36 专项回归 `65 passed`，Ruff 和 `git diff --check` 通过。同步真人集与结构集指纹后，API 全量在沙箱外为 `400 passed, 6 skipped`，覆盖 Redis、本地 HTTP 和 OSMD/Chrome 解析门禁。
- 新离线包已生成：`songdance/api/dist/songdance-structure-review-ec38a2b251b2.zip`，SHA-256 `f729a9f71f34b606d96af06688d44e5fc1ddb9cfba503870337b4cccb3796301`；`07-soft` 的历史 `needs_redo` 记录仍保留，当前新产物需重新人工复评，未标记为通过。
- 独立 `code-reviewer` 复审确认 AC-101～103 行为通过；Stage 2 提醒相关模块超过 300 行且截断规则只覆盖高音规则旋律，已在本 Phase 风险中保留，不扩展成未经真值验证的全局规则。

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
| 单音候选 | librosa pYIN / CREPE | librosa 0.11.0 / CREPE 固定提交待验证 | Phase 18 与 Basic Pitch 按乐器 A/B；CREPE MIT 但维护与 TensorFlow 兼容需验证 |
| 任务模型候选 | Omnizart | 固定提交/checkpoint 待审计 | Phase 18 人声与 Phase 20 鼓；代码 MIT，权重和 ARM/Python 兼容需验证 |
| 直接多轨候选 | MT3 | 固定提交/checkpoint 待审计 | Phase 21 多 instrument program A/B；代码 Apache-2.0、非官方支持产品、T5X/GPU 依赖隔离 |
| 音频分析 | librosa | 0.11.0 | Phase 14 的 BPM/beat/色度基线；Phase 33 起色度只作调性候选先验，不可直接写调号 |
| 乐谱后处理与和声证据 | music21 | 10.5.0 | MIDI 量化、分手、MusicXML，以及 Phase 33–35 已量化事件的和弦/终止式证据；不新增生产 MIR 依赖 |
| 可选分轨 | Demucs/维护分支 | P1 实验，固定提交待审计 | Meta 上游仓库已归档；四轨/六轨在独立 Worker 评估，不进入主 API 镜像 |
| 媒体处理 | FFmpeg | 7.x 或部署平台稳定版 | 解码、裁剪和规范化；镜像内固定小版本 |
| 数据库 | PostgreSQL | 17.x | 任务和产物元数据 |
| 队列 | Redis + RQ | Redis 7.x | Worker 排队、重试和限流 |
| 对象存储 | S3 兼容存储 | 服务端版本 | 私有临时音频和产物 |
| 包管理 | pnpm / uv | pnpm 10.x / uv 当前稳定版 | Web 与 Python 依赖管理 |

版本说明：前端和核心 Python 包版本于 2026-07-28 通过 npm/PyPI 查询；2026-08-05 复核当前锁文件与官方仓库，确认 librosa 0.11.0 已锁定、Basic Pitch 明确支持跨乐器复音但建议一次一个乐器、Demucs 上游已归档且六轨钢琴质量有限、MT3 提供多乐器 checkpoint 但不属于官方支持产品、Omnizart 存在 ARM 兼容限制。2026-08-28 的 Phase 33–35 计划不新增外部运行依赖，复用锁文件中的 librosa/music21 和现有和弦聚合，因此不产生新的版本选型；若实现中提出新 MIR 模型，必须先重新联网核验版本、许可、权重与兼容性再更新本计划。开发时先在隔离环境验证固定提交、checkpoint 哈希、许可和资源预算；未选中的模型不得进入主 Worker。Essentia 为 AGPL-3.0，madmom 的源代码与模型数据许可不同，二者未完成审计前只允许离线评估。

## 数据库表

| 表名 | 所属 Phase | 用途 |
|---|---|---|
| `transcription_jobs` | Phase 3 | 任务状态、阶段、区间、过期和错误码 |
| `source_assets` | Phase 3 | 输入文件元数据和对象键 |
| `transcription_results` | Phase 4、33–34 | 模型版本、速度、拍号、局部调性 top-2/证据、记谱调号来源、staff layout、音符数和质量标记；优先扩展版本化 JSON 合同，确需结构列时再单独迁移 |
| `artifacts` | Phase 4 | MIDI、MusicXML、JSON、PDF 产物元数据 |
| `transcription_quality_reports` | Phase 11、33–35 | 原始/清洗音符统计、结构错误、调性/模式候选证据、staff layout、置信度、模型和后处理版本 |
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

### 后续子任务：13-key-change 六音循环单旋律修正
- 采用 `six_note_melody` 专项上下文，固定 3/4、每小节 6 个八分音符槽位和单高音谱表。
- 每个槽位最多保留一个模型事件，隔离泛音/延音导致的伪和弦；原始 MIDI 仍保留用于审计。
- 专项测试与 06/11 回归通过后，等待后续人工复评；不单独生成最终评审包。

### 后续子任务：14-hand-crossing 镜像八分节奏修正
- 采用 `crossing_eighth_melody` 专项上下文，固定 4/4、60 BPM，将模型事件对齐到 0.5 秒八分槽位并统一时值。
- 保留双手复音和模型给出的 C4 交汇同音；不得用参考音高模板替换、补写或删除无音频证据的事件。
- 原始 MIDI 与未匹配事件写入审计。使用现有 `14-hand-crossing.wav` 生成候选，不改写旧合成器，也不生成最终评审包。
- 2026-09-15 续作验收：先用未量化事件匹配确认为可删除的谐波证据，再按绝对秒时间归入八分网格；谐波观察和单一能量增长不足均不得单独作为删音证据。每条保留、移除和时间变更可追溯，位移超过 0.2 秒的事件标记复核。
- 只在该上下文使用参考记谱的秒/拍网格及首拍原点，保留检测 BPM/grid；固定样本是 59 个起音槽、尾小节不完整，不能补音填满。MusicXML、MIDI、timeline 的时值与音高事件互校，单独报告泛音残留、漏音和同音合并，不用节奏通过代表整段通过。
- 完成顺序：修复与反例测试 → 原 WAV 候选及三种解析器验证 → 相关/全量 API 与 Web 类型检查 → fresh 两阶段审查。产物保存在独立候选目录，既有人工评级及统一评审产物不刷新。
- 双 C4 保留必须覆盖 `clean_note_events → build_score → MusicXML/MIDI` 整链：仅交叉练习显式开启同刻同音保留，普通上传的去重策略不变；不能拿直接调用 helper 的测试替代整链证明。
- 2026-09-15 结果：59 项相关 API 回归、140 项 Web 测试、类型检查/编译/Ruff 通过；候选三个产物 264 个事件一致且全为 0.5 秒，解析器通过。源 111 个不同音高起音全部匹配，但153个额外/重复事件仍待复评，候选保持禁止发布。全量 API 520 passed/8 failed/6 skipped，8项失败均在续作前存在，涉及固定集指纹和07历史记录，未用重新绑定掩盖旧产物。

### 后续子任务：14-hand-crossing 音尾重复识别（AC-114）
- 诊断基线：153 个额外事件中，122 个与前两槽真实音高重合、22 个符合同时泛音音程、9 个未分类；这些是评估分组，不是删除依据。
- 新增独立的交叉双声部音尾判断模块，复用现有窄带振幅/相位衰减测量，不改变 09 的单旋律清理。候选必须精确匹配音频事件，满足 `growth<=1`、正的有限前后能量且没有回升、`decay_fit_error<=0.05`。
- 同音前一事件必须唯一且端点与当前起音相距不超过 80ms；可沿已证实的尾音片段回溯，但最终根事件须有独立起音，根至候选不超过两个八分槽加80ms，同刻同音不进入删除。当前附近80ms内须有另一音独立起音。所有删除保存根、直接前驱、其他起音及精确音频测量。
- 完成标准：原 WAV 的111个不同音高起音全部保留，多余事件减少；新增声音级弱重击/相位变化、双C4、长音/无证据反例及落盘产物回归；原音频/MIDI、普通上传、12/13逻辑不变。重新生成独立候选并fresh审查；全量旧指纹门禁如实保留，不生成最终评审包。
- 审查反例：真实短弱重击可在起音后60ms前衰减。混音直接探测早窗又会误认其他键的攻击，故 `transient_fit_error` 用64ms窗的联合正弦/余弦及线性包络拟合分离邻音/6阶内倍频，在起音前40ms及后40/60ms估计当前音，和前170/130/90ms预测比较；瞬态误差<=0.01且原60–180ms衰减窗误差<=0.05才删。当前音附近15Hz内存在其他载频、矩阵条件数>100或拟合不可测时保留。验证衰减率50/s、振幅0.03/0.08/0.16、模型±80ms与另一手±70ms的组合反例；正常上传/09不启用此测量。
- 瞬态分别以候选原始起音和附近其他独立起音的中位时刻为锚点，两者均可测时取更大误差，任何一个窗口不可测则保留；审计保存邻音锚点。这同时保护模型切分延迟和双手轻微错开的真实重击。
- 最终音尾候选单独输出到 `candidates/14-hand-crossing-tail-v2`，保留此前仅修节奏的候选作对比。数值分解仅缓存最多32组与音频无关的投影矩阵，不缓存波形或事件；降低批量反例验证时重复计算成本。
- 音尾清理结果：最终25条删除、264→239个记谱事件，111个不同音高起音全部保留、余音153→128；此前106/55删除方案因短弱重击反例弃用。128项音频与规则反例通过；三种实际产物和三种解析器均通过。最终源码及输入/产物哈希保存在tail-v2候选报告，人工评级仍待复评。
- 最终验证：交叉专项152 passed；全量API650 passed/8 failed/6 skipped，失败集合与前一阶段完全一致；Ruff/compileall/Web类型检查通过。8项旧指纹与07历史评审问题依旧阻止整项目放行，未重绑掩盖。
- AC-114 最终独立Stage 1/2审查通过，0 HIGH/0 MEDIUM；额外108个短重击音区/相位/偏移抽查未命中删除条件。本轮音尾实现完成，候选仍待人工复评，余下128个多余事件继续保留为后续修复项。

### 后续子任务：14-hand-crossing 同时泛音审计
- 当前 tail-v2 剩余128事件中，97为近期音尾候选、22符合同时泛音音程、9未分类。先逐条绑定22候选的原始模型事件、精确基音配对、独立起音、能量/力度/时长、release/tracking与源哈希；分类只在离线评估时使用参考MIDI，不作为生产删除条件。
- 复核两个可疑策略：相对低能量/无独立延迟起音 + 尾部跟随，以及更严格的跟随比。用同一低音含泛音的波形，分别叠加真实弱八度/十二度，对照纯泛音；覆盖三个低音音区、两种时值、多个力度与相位，保存波形、参数和逐条假阳性。删除误音的效果与误删真音的损失分别报告。
- 仅没有误删且有充分音频证据的策略才可接入；若反例否决，交付可复现审计工具与保护真实八度的回归，不修改生产阈值或重生成正式评审包。候选余音保留待复评，不能为降低数量用参考谱直接筛音。
- 核验结果：22候选中2无精确基音测量、14无可用release probe、6具备测量。120控制波形中12纯泛音、108包含明确上音；两策略理论选中目标6/3条，却误删控制真音80/50条，均否决。本轮不新增删音，交付独立审计report与9项回归；原111正确起音/128余音不变。详见 `songdance/docs/reviews/2026-09-15-14-harmonic-audit.md`。
- 新增9项审计测试及原交叉相关回归共161 passed；Ruff/编译/diff检查通过。此子任务仅完成候选核验和假设否决，22条泛音候选清理仍待后续独立证据。
- 独立两阶段限定审查通过，0 HIGH/0 MEDIUM；120份控制音频与22条候选测量重新核对一致。两种阈值策略不接入生产，原111起音/128余音保持不变。

### 后续子任务：14-hand-crossing 独立高音频谱可辨识性
- 在已冻结的22候选/120对照上测量候选前6个泛音的真实FFT峰值，记录原始窗长对应的频率分辨率与补零后的采样间距，补零不得被当作新增分辨能力。
- 对比同起音的模型低音可产生的整数倍频，包含6阶以上的可能低音分量，不能借合成器只有6阶的限制推断真实钢琴没有高阶泛音。允许35cent调音偏差，频率区间和窗分辨能力重叠时必须输出不可区分。
- 该阶段只输出频谱归属证据与弃权原因；观测到峰值不等于独立击键，未观测到独立泛音也不等于未演奏。全套对照验证保留真八度/十二度，另加非谐波关系高音可被正向检测的正常例，防止恒定弃权的假实现。
- 不修改生产删音规则或旧候选；输出独立spectral-family审计、回归和评审记录，确认是否有足够条件开展后续音色建模。
- 实测22候选与120对照全为ambiguous；3/5/7/13半音正常例能检出频率支持，方法不是恒定弃权，但对八度/十二度尚无可靠归属能力。新增删除0，保持原239事件/111正确起音/128余音。记录见 `songdance/docs/reviews/2026-09-15-14-spectral-family.md`。
- 枚举竞争高阶分量时包含35cent调音区间，补零不改变窗长分辨保护；不可测路径统一independent_attack_confirmed=false。幅度门槛仅启发式，不宣称SNR或旁瓣彻底排除。下一步技术比较需引入钢琴音色先验，不能把此诊断当生产删音规则。
- 31项频谱与前序审计测试、Ruff/编译/diff检查通过；独立Stage1/2限定复审通过，0HIGH/0MEDIUM。没有新增删音，22候选仍待后续有效证据。

### 后续子任务：钢琴专用模型离线对照
- 在独立临时Python环境运行Transkun V2 CPU候选，源码固定 `Yujia-Yan/Transkun@c5cb8370e17b4a1650b5971ba87ee4b0d208e5b6`；核对MIT源码许可、随包 `transkun/pretrained/2.0.pt`、配置及SHA-256，保存精确依赖。权重默认版本上游声明为No Pedal Extension，不用其论文指标代替本地测量。
- 仅研究对照，不修改生产模型/依赖锁/旧模型准入清单，不表示已确认商业部署所需的全部权重和训练数据许可。
- 第14条原音频经相同预处理后分别比较Basic Pitch原始事件与Transkun原始MIDI；参考MIDI只用于事后评价，去除源同刻同键重复以比较111个独立音高起音，同时保存原118条源计数。报告50ms/100ms起音匹配、precision/recall/F1、错音/漏音、运行时间、输入/代码/权重指纹。不可套用教师音高模板或记谱修正夸大模型表现。
- 交付可复现运行/评价脚本、来源审计与一次真实模型推理结果；任何安装、加载或模型失败须显式保留，不将环境准备称为完成转录。全部产物留在独立候选目录，最终评审包仍不生成。
- 2026-09-15 实测已完成：Transkun官方随包56MB权重通过Git blob/SHA-256核验，CPU约13.735秒完成30秒第14条转录。两个容差50/100ms下Basic Pitch285/111/174/0、Transkun105/105/0/6（预测/匹配/额外/漏音），起音F1由0.5606到0.9722。真实6漏音已列明，不能直接生产换模。
- 对照结果为 `candidates/piano-model-comparison-14/comparison-v3.json`；两边同输入哈希、Basic Pitch新推理、源码/权重/适配器/原始产物绑定，失败留档与禁止覆盖均实现。不改生产API依赖和旧模型准入清单；后续扩大真实钢琴/弱音/踏板/带限片段对照。
- 2026-09-16 独立复审要求补齐Basic Pitch实际转录模块指纹及原始MIDI校验；重新推理保存basic-pitch-v3和comparison-v4，保留历史产物。新增转录代码与MIDI篡改拒绝测试，复审通过后才关闭本轮。
- 2026-09-16 修复后fresh限定Stage 1/2通过，0 HIGH/0 MEDIUM；31项相关测试、Ruff、compileall、diff检查通过，v4完整报告独立重算一致。本轮离线对照完成，生产准入与整项目旧失败不因此放行。

### 后续子任务：钢琴模型跨样本原始对照
- 将现有准备/评价脚本参数化为显式case_id与基线目录，固定06-sustain、07-soft、10-device、14-hand-crossing和真实02-brahms-intermezzo。输入选择只读现存文件，不改合成器，不套教师模板；真实片段校验human-provenance中音频哈希并保存来源及许可记录。
- 合成样本继续50/100ms逐音起音评价；真实片段没有逐音参考，不输出准确率、F1或胜负，只保存两模型事件、数量和对称差异供后续听审。禁止把模型间一致率当准确率。
- 各样本独立运行两模型、保存失败状态与完整来源/代码/产物指纹；新增目录保留历史v4，第14条重新生成基线并验证数值不变。生产模型、生产依赖、统一评审包均不修改。
- 验收顺序：参数化和篡改/无参考测试 → 五样本实际运行 → 逐样本报告及汇总 → 相关API回归/编译/独立fresh审查。真实片段仅转录与差异审计完成，音符正确性和谱面质量仍待验证。
- 2026-09-16 五样本扩展对照完成：06-sustain Basic/Transkun F1 0.7018/0.8889，07-soft 0.6325/1.0000，10-device 0.5682/0.9831，14-hand-crossing 0.5606/0.9722；Transkun分别漏音12/0/3/6且无额外事件。真实02-brahms无逐音参考，仅保存242/158事件及交集差异，不输出准确率或胜负。24项专项测试、Ruff、compileall通过。下一步是隔离候选进入MusicXML/PDF链路验证时值、踏板、声部和可读性，仍不改生产模型、不生成最终评审包。
- 结构摘要：06-sustain 48事件/12声部/13和弦/8休止，07-soft 40/30/0/55，10-device 87/59/0/100，14-hand-crossing 105/91/8/124，02-brahms 158/67/21/131；五组均4/4且小节时值错误0。该结果暴露通用评分器会把稀疏或弱音候选拆成大量声部/休止，不能直接交付老师，下一步先做声部压缩诊断，不改生产阈值。

### 后续子任务：Transkun 起音与声部分组原型
- 输入仅使用 `transkun-v2/raw.mid`，原始 MIDI、模型 receipt 和当前评分器输出保持不变。
- 先按连续起音和音区形成左右手候选，再在每个候选组内截断重叠时值；禁止用全局下一起音截断跨手事件。
- 每次时值变化记录原始起止、目标起止、分组理由和延音证据；无法区分真实持续音与残响时保留原事件并标记复核。
- 验收：06-sustain 不得删除参考低音或三和弦基音；07-soft 不得生成大量伪声部；10-device 必须保留低音循环；14-hand-crossing 必须保留双手镜像及交汇同音。MusicXML 小节时值错误为0，声部和休止符只作为诊断指标，不能单独作为通过条件。
- 先生成候选 JSON/MusicXML 与四样本对照，人工复评前不进入生产链、不生成最终评审包。

### 教师回传：07/10 Transkun候选
- 07：单行高音谱、音符时值、循环/小节对齐均获确认；明确不需要踏板或延音标记。仅确认已发送候选的这些项目，不代表模型生产准入。
- 10：低音循环不完整，“低音一拍一音”不正确；双手对齐、高音时值正确。撤回此前“低音一拍”及0.9秒可用的推断，后续候选保护已确认的高音与双手起音关系。
- 10原始模型相对当前源MIDI缺失0/15/16秒的C2(MIDI36)，与低音不完整反馈一致；只作漏音定位，不可直接按参考谱补入模型结果。低音正确记谱时值仍需音频/拍格证据，不能从“不正确”倒推出唯一正确长度。
- 反馈绑定发给老师的MusicXML SHA-256，保存在songdance/docs/reviews/2026-09-16-transkun-teacher-feedback.json；06仍未通过，不重新生成总评审包。
- 10低音节奏v2：从老师听审的XML制作新候选，只将staff2的17640单位双附点四分音符与紧接的同voice 2520单位休止合并成20160单位二分音符。保持所有音高、音符起音、右手XML节点及120 BPM不变；缺失三个C2不补。附逐音时间轴等价检查及SHA审计。此候选只修订低音节奏，仍不完整，不标通过。
- 10低音节奏v2实测：26处时值改为二分音符、30→4休止符，87个音高起音和右手节点逐项一致，2staff/0小节时值错误。2项测试、Ruff/编译/xmllint通过；fresh审查0 HIGH/MEDIUM，独立完整XML变换核对一致。此阶段仅完成节奏假设候选，三个C2漏音仍待音频验证，未作音乐正确性或生产准入声明。
- 10漏低音音频核验：对两模型未匹配的所有Basic低音候选测量基频窄带投影，比较起音前后能量；窗口200ms、保留文件开头无前窗的弃权。以纯高八度/有低音/噪声对照验证，不把基频存在当作独立重击证明；不补音，不使用参考MIDI筛选候选。
- 上下文实测：前加4秒静音后15/16秒C2恢复、3/20秒C2漏检、0秒C2仍漏。新首音C4映射-3.6ms被严格裁切排除，属于映射规则问题非模型漏检。7项局部测试通过；研究方案未选为补音规则。fresh复审受子任务数量上限阻塞，尚未完成全验收，详见device-context-shift记录。
- 首音映射v2采用显式10ms边界容差：仅起音在[-10ms,0)且结束在原区间内的事件钳到0，记录调整；更早起音及完全位于padding的事件拒绝。该容差是映射约定，不是音频起音检测。保留v1，输出evaluation-v2/aligned-v2，附两次推理的低音交集与差异，不做融合。
- 首音映射v2完成：C4的-3.6ms调整留档，两版87/87正确匹配、各漏3音；25个低音共同检出，原版独有3/20秒、移位版独有15/16秒，0秒C2共同漏检。不拼接；9测试/Ruff/编译通过，fresh复审仍未完成。
- 10边界稳定性扩展：预先固定1/2/6/8秒四个前置静音长度，保持原PCM样本逐一不变，所有运行都评价完整输出并保存结果，不按得分选择融合。记录不同移位对全段误音/漏音及首C2的影响，参考只在推理后读取；固定10ms首音映射规则。
- 固定1/2/6/8秒对照完成：分别89/88/88/89正确、额外均0、漏1/2/2/1，所有运行均漏0秒C2；1秒和8秒完整输出均检出所有内部参考起音。14项测试/Ruff/编译通过，原始结果/执行脚本快照保存于context-sweep-v1。未融合/未换模型/未修改听审XML；fresh复审尚未完成，首C2继续待查。
- 10首C2带宽对照：先逐样本重建当前device音频确认一致，再只关闭180–5500Hz设备滤波生成full-band控制（相同音符/力度/噪声seed/时长）。同样预处理并前置1秒/后置1秒静音，固定Transkun推理；比较完整90事件，不把控制音频当作原音频修复，保存生成脚本与哈希。
- 首C2带宽假设否决：原设备WAV可逐样本重建，关闭带通的全频控制仍漏首C2，全段漏音从1增至7（均C2）。同前1秒静音、同噪声/音符/预处理/模型，不融合。15项测试与Ruff通过；fresh审查未完成。详见device-bandwidth-control.md，不把谱面或低音完整性标通过。
- 10音色对照：本地FluidSynth 2.4.6与pretty_midi随包TimGM6mb.sf2钢琴program0渲染原MIDI，关闭混响/合唱；保留原音高、起止和力度，30秒mono/22050Hz、峰值0.82后同设备滤波与seed1009噪声、相同预处理和1秒前后静音。音源包络/频谱/力度响应都会变化，只能称替代音源对照，不能称纯音色单因素。原输出/生产/已确认谱面不改，不随听审包分发音源。
- 10替代音源对照完成：FluidSynth/TimGM6mb用原MIDI渲染、同设备滤波/噪声/预处理/1秒padding，50/100ms均90/90匹配、0额外0漏，首C2可检出。支持调查原合成渲染特性，不能锁定单一音色成因或冒充原录音修复。16项回归/Ruff/编译通过，fresh复审未完成；原候选不变，详见device-soundfont-control.md。
- 跨样本音源对照预注册06/07/14：每条同时跑原音频和TimGM6mb替代音源，统一前后1秒静音及固定模型，防止把padding变化误算成音源效果。参考同刻同键去重仅用于评价（14保留118/111计数），完整报告误音/漏音，不择优融合，不改听审包。此音源与10相同，不是新的独立音源，也不等同真实演奏。
- 跨样本6次配对推理完成：同1秒padding下06原45/0/15→替代60/0/0，07原40/0/0→40/1/0，14原103/0/8→111/14/0（匹配/额外/漏）。50/100ms一致。替代音源并非全面改善，不融合不换模型，保留误音回归。23测试/Ruff/编译/diff通过，fresh审查尚未完成；详见soundfont-cross-cases记录。
- 替代音源误音审计：对07/14新增误音列出同起音源音高关系（仅评价标签），并在06/07/14两种音源六组全输出离线模拟“同时有低八度就删高音”。统计误音减少与真实音损失，若伤真音则否决，不修改模型/谱面，不把参考标签用于生产决策。
- 替代音源误音审计完成：07的1音、14的14音均为同刻高八度关系；离线全局八度删除在14删14余音同时损失15真音，在06损失10真音，规则否决。实际删音0，新增8项反例/落盘重算测试，相关共16 passed，Ruff/编译通过；fresh审查尚未完成。
- 补齐06/07/14×原/替代音源的Basic Pitch同输入对照：直接读取已跑Transkun的padded.wav，先核验推理receipt输入/MIDI指纹，Basic以当前生产阈值原始推理，不量化/删音/套模板。双方同10ms映射、同50/100ms评价；保存失败、原始时间线/MIDI/代码/输入指纹，逐组完整报告，不凭模型名称判断优劣。
- 六组Basic/Transkun同输入对照完成：Transkun起音F1在5/6组更高，07替代音源Basic无额外音而Transkun多1；06原音源Transkun仍漏15。全量原始Basic推理与哈希保存cross-case-model-comparison-v1。22相关测试/Ruff/编译通过，fresh复审尚未完成；不据F1换生产或融合，详见cross-case-model-comparison报告。

### 统一候选流程第一步：冻结教师反馈与重建入口
- 以已发送XML哈希和教师记录作为输入门禁：07原样保留，10仅复用已测试低音节奏修订（低音缺失仍标未解决），06明确blocked，不重新生成不合格候选。
- 单一脚本接受新输出目录，拒绝覆盖；逐项保存源/结果/反馈/代码指纹、结构解析状态与失败记录。10验证全部音高起音和右手节点不变。保留模型版本和“非生产”标记，不宣称完整转录链已集成。
- 本机已安装MuseScore 4；offscreen方式启动失败（该安装仅提供cocoa插件），这是当前无界面验证方式不可用，不是文件导入失败，不把music21解析当MuseScore通过。
- 统一候选入口实际运行到reviewed-candidates-v1：07逐字节冻结，10与已测试bass-rhythm-v2结果一致，06blocked。5项测试/Ruff/编译/xmllint通过；MuseScore实际导入和fresh复审仍未完成，后者被agent thread limit reached阻塞。本阶段仅固定重建入口，非完整模型集成。
- 06版本纠正：当前听审包来自旧generated/06-sustain.wav，源MIDI60音/每簇4音（含额外低八度）；已有sustain-triad-v2-manifest声明老师三音513/614/572，但对应truth.mid当前未落盘。建立独立、拒绝覆盖的三音源准备脚本，45音/15簇/每簇3音，保留旧源历史指标，不把新合成音频称为原音频修复。07/10 MuseScore UI尝试未确认新乐谱进入活动窗口，仍不标导入通过。
- 06源核对完成：旧源60音/15簇每簇4音，与老师三音反馈不一致；独立新源06-teacher-triad-source-v1为45音/15簇每簇3音，保留旧源，不冒充原录音修复。5测试/Ruff/编译通过，未转录/未复评。MuseScore原生界面文件选择成功但未观察到新乐谱活动窗口，导入验收仍未完成，不改用户未保存乐谱。
- 06三音新源双模型对照：核验source-receipt及源WAV/reference.mid哈希后，同一预处理和前后1秒静音输入分别运行当前Basic Pitch与固定Transkun，原始事件只做统一时间坐标映射、不删音不补音。完整45事件50/100ms评价，旧06指标不覆盖；结果未明前不生成谱面。
- 06三音双模型实测完成：同输入Basic45匹配/33额外/0漏，Transkun38/0/7（50/100ms一致）；仍未达到完整且干净，不生成已修复谱面。7漏中四个C4与一个G3被模型前一同音长事件覆盖，另两G3完全漏；后续分同音重击合并与完全漏检验证，不按参考补音。7测试/Ruff/编译通过，fresh审查未完成。
- 06同音重击隔离原型：候选仅来自Basic独立起音，且位于唯一Transkun同音长事件内部（离前起音>300ms、距尾>100ms）；200ms基频窗前后幅度比≥4、后窗幅度≥0.001才建议分割。同期其他低音可在35cent内以2–6阶泛音解释该音时弃权。阈值只作实验，不使用参考生成建议；反例覆盖纯衰减、噪声、其他音起音、低八度泛音与真重击。先保留原MIDI并输出带审计的新候选，事后评价，不接生产。
- 06同音重击实验恢复5起音：38/0/7→43/0/2（正确/额外/漏），剩4/22秒G3不补，原输出保留。反例/实际重算相关11项通过，Ruff/编译通过。真实音频/渐强拍频等未覆盖，fresh复审未完成；结果仅实验MIDI，不标45音完整通过。
- 06完全漏检候选验证：枚举Basic相对已恢复43音的全部未匹配事件，100ms匹配；仅对有前后基频窗、后窗振幅>=.001且回升>=4的事件考虑新增。若同期/仍在持续的任何较低模型音可在35cent内以2–6阶泛音解释，则弃权。此为研究准入假设，偏保守地拒绝真八度也不能换取误补；参考只事后评分。测试空波形/其他音/低八度泛音/边界/独立低音，不改原输出及老师谱面。
- 06三音源missing-notes-v2实验：35个Basic未配对事件中只加入两G3，43→45正确、0额外0漏（50/100ms，实际MIDI重读一致）；原43音不变。前窗0的除零弃权问题以幅度不等式修正，v1保留未通过状态。18相关测试/Ruff/编译通过，fresh复审与谱面/听审未完成，不接生产不冒充旧原音修复。
- 06三音候选记谱：仅消费missing-notes-v2审计事件（核验MIDI指纹），按80ms起音簇，必须每簇恰好3个不同音高；不读参考音高模板。展示约定60 BPM、4/4、每和弦二分音符（2秒），所有起音偏移<=50ms才允许；15和弦形成7完整小节+末尾半小节，不补休止填32秒。原始与记谱时值逐音留档，单高音谱表、无踏板猜测，MusicXML/MIDI/timeline一致；属于新合成源待听审候选，不改原录音。
- 06三音谱v2落盘：45音/15和弦/1高音staff/0休止，60BPM/4拍每和弦2拍为展示假设，7完整小节+末尾半小节总30秒。v1被导出器补休止至32秒故不用；v2校验后删除仅末尾自动休止，完整逐音审计。24测试/Ruff/编译/xmllint通过，实际MuseScore/fresh审查/教师复评未完成；搭配新三音源，不对应旧录音。

### 用户确认后的候选冻结
- 用户“都没问题进行下一步”按对当前06新三音候选和10低音节奏修订的确认记录，不伪写为新教师逐项评语或生产模型准入；07保留既有教师确认。
- 新建版本化接受清单，绑定每组XML及配套音频哈希。06必须绑定新三音源，不能混用旧四音原音频。10仍保留已知模型漏音事实，候选接受与算法完整性分别记录。
- 统一构建入口默认复制已接受版本（不重新运行模型/时值变换），保留旧生成模式供追溯；拒绝文件漂移和覆盖，输出清单及解析证据，不创建最终评审ZIP，不切生产模型。
- 用户接受清单与默认accepted构建模式已落地，accepted-candidates-v1含06/07/10固定XML+对应WAV，构建拒绝漂移/覆盖。15测试/Ruff/编译/xmllint通过；旧模式保留historical。用户确认≠新教师逐条意见≠生产放行，10漏音限制保留，fresh代码审查未完成。
- 已接受候选增加独立只读验证入口：从接受清单而不是产物自报状态确认3组身份/音源类型/限制，逐一校验WAV/XML哈希并重新解析XML对比结构。缺组/重复组/替换音频/隐藏限制/路径逃逸/生产标记变更必须失败；不得将接受状态转换成生产放行。此入口只核验冻结候选，不替代MuseScore或代码复审。
- 独立候选校验入口已运行，三组XML/WAV哈希及实际结构与接受清单一致；8新增反例测试、相关共23 passed，Ruff/编译通过。缺组/重复/篡改音频/隐藏限制/越界路径/生产标记变更均拒绝。输出candidate_integrity_passed不等于production_eligible，fresh代码复审仍未完成。

### Transkun隔离原始转录入口
- 新增单命令输入任意本地音频与独立Python/固定源码路径，复用现有音频预处理和已核验run_cpu，不安装Torch进API。
- 仅导出原始MIDI和原始事件JSON，不偷偷padding/量化/补音/写模板；未知置信度/左右手用null，不再伪造0.99。源/规范化音频/模型receipt/脚本和产物哈希绑定。
- 非空既有输出目录拒绝、分阶段状态/失败留档、推理超时终止；只读模型源码。完成实际端到端推理与失败/输入替换/导出一致性测试后仍保持research_only及生产不切换。
- Transkun单命令离线原始入口实际跑通07，输出40事件且JSON与MIDI一致；修复venv解释器resolve丢依赖，新增回归。18项相关测试/Ruff/编译通过，API仍无torch。失败v1与成功v2留档，不改生产路由，记谱接入与fresh独立审查仍待完成。
- 离线记谱阶段首版仅显式confirmed-monophonic配置：输入原始入口目录及人工选择的BPM/拍号（不伪装自动识别），只接受高音区、独立起音、无同时多音的事件；裁剪相邻尾音并保留所有变化。复用build_score单旋律上下文，内部confidence=0只作未知占位，导出JSON仍null。真实10/06多声部拒绝，不自动分手，不扩散规则。XML/记谱MIDI/时间线与原音高数量互校，失败留档禁止覆盖。
- 单旋律记谱阶段notate_transkun_candidate已用原始入口07结果实际跑通：40音顺序保留，1高音谱表/0休止/0小节错误，输出MIDI与timeline逐事件一致，量化位移<50ms；06/10/14原始复音回归拒绝。20相关测试/Ruff/编译/xmllint通过。未知音符与手置信度导出null，原始推理/已接受谱不改。双手记谱集成与fresh独立审查仍待完成。

### 上线前既有问题收尾（不部署）
- 暂停新增Transkun实验与生产换模；保留已接受06/07/10候选，10漏低音不能以验收标记掩盖。
- 前端Webpack生产构建与140测试已完成；默认Turbopack在沙箱绑定端口失败，不改应用行为绕过权限。
- 修复单测对真实Redis的意外依赖、评审提交单测对过时全局评审状态的耦合、07历史意见引用错误；正式人评/结构评审指纹门禁仍保留，不能重绑冒充当前代码已复评。
- 2026-09-19收尾：修正Redis配置单测隔离、tmp人评行为测试前提和07历史意见字段引用，新增过期提交拒绝且不写回反例；正式评审指纹未变。API797通过/5失败/6跳过/3准备错误（原790/11/6/3）；Web140测试/tsc/Webpack构建通过。余3项旧报告/人评指纹+2OSMD失败+3浏览器打包错误、fresh审查资源阻塞及10漏音，统一记录docs/reviews/2026-09-19-closeout.md，不部署不扩实验。纠正voice_count为全谱Voice容器数量，0不代表无声部、91不代表91同时声部。

- 2026-09-19收尾续作：申请解除本地浏览器/端口测试限制后重跑OSMD及离线包集成；仅生成临时测试包，不发布。设备低音A/B指纹失败通过归档旧报告并用当前代码真实重跑处理，不改指标或哈希蒙混；正式人工评审仍保留过期状态。
- 2026-09-19收尾最新：解除浏览器/本地端口限制后OSMD/评审包8项通过；旧device-bass-ab完整归档，当前代码真实重跑及8项报告测试通过。API最终803通过/2失败/6跳过/0准备错误，余仅正式人评/结构review指纹过期，未重绑。fresh独立审查仍资源上限阻塞。前端Webpack构建/140测试/tsc此前通过，不部署不换模型，统一见closeout记录最新段。
- 最后两项正式评审过期：当前Basic Pitch代码在新独立目录重建16条结构集+10条真实集，复制输入不覆盖旧产物/评级。使用原生成流程与同一上下文，完整重新推理；新评审全pending，生成新旧语义/文件对照，代码通过不代替人工复评，不创建最终ZIP。
- 2026-09-19固定集26条已独立重建并绑定当前代码，旧评审hash保留：26原始事件一致、25记谱语义一致，仅14记谱264→239（既有音尾25条清理）。结构16条三解析器通过，新两份人评均pending不迁移评级。3新增测试/Ruff/编译通过；差异详见2026-09-19-rebuilt-review-differences.md，正式两个旧门禁尚不自动放行。
- 14逐音核验补充：变化不仅25音删除，还含固定八分网格。50ms旧86/178/25→新111/128/0；100ms旧111/153/0→新111/128/0（匹配/额外/未匹配），新全0.5秒、休止85→3。音尾25条删除审计完整但128额外仍未解，不标通过；4项重算/隔离测试通过，无新模型或规则改动。
- 14收尾对照材料生成至songdance/output/14-closeout-review/index.html，包含原音频/旧新版XML与MIDI/PDF/同音源播放音频，明确128额外仍未通过。旧PDF导出有右端裁切和上下谱表跨页，单独closeout渲染器改为700px宽连续长页，两版逐页图像检查完整；不修改生产PDF路径或评级、不创建最终ZIP。
- 14对照材料实际file://浏览器验收完成：3音频可解码且播放进度推进、6链接有效、375/1280无溢出、无JS错误、文件哈希一致。尾音时长说明已补并重验。正式质量未因材料可用自动通过，128额外音/旧人评指纹/fresh代码审查仍分开保留。
- 完整用户流程Playwright26项全通过（1.9分钟），含真实Worker转录/看谱/播放/移调/MIDI-XML-PDF下载、上传恢复删除、多格式和移动端，独立临时数据目录。不替代音符质量或正式人评门禁；保留现有Basic Pitch，不部署。
- 10归属核清：生产Basic原始MIDI低音100ms匹配29/额外49/未匹配1（12s）；记谱23/55/7，含时间偏移因素。0/15/16s漏C2特指Transkun候选，不再混为生产模型同一问题。新增完整分区指标重算测试，相关10通过；仍未修音质，不扩实验不部署。fresh审查仍线程上限阻塞。
- 10量化定位：帧量化拍点约0.488/0.511交替，_subdivision_grid取上中位数0.510839匀速外推，与检测首尾跨度差0.604s；6个C2原始<100ms偏移经舍入后越过阈值。BPM/记谱换算也耦合，未盲改全局均值。5诊断/归属测试通过，26条网格差异留档；算法修复尚未完成。
- 稳定拍格修复：在音频分析阶段对>=12拍且跨度>=6秒的严格递增拍点拟合直线；仅残差<=一帧、各间隔偏差<=两帧、前后半段斜率差<=1%、拟合速度与检测BPM差<=5%时校准BPM和拍格为同一拟合结果，变速/缺拍/默认速度弃权。保留原BPM/拍点与理由审计，后续量化/秒拍换算共享一致时间基准；不读参考MIDI，不改已接受曲谱。
- 2026-09-22独立审查确认0 HIGH/2 MEDIUM：轻微变速可能符合容差，不能承诺所有变速弃权；真实候选测试需现场调用当前代码。已追加微变速边界及真实音频analysis→Basic→cleanup→score→MIDI测试，限定承诺为超过稳定阈值才弃权。指标纠正：10低音50ms匹配14→29、extra64→49；100ms匹配23→29、extra55→49，不能说extra49始终不变。新分析版本使旧7份证据绑定失效，尚未更新旧评级。
- 2026-09-22修正后fresh限定复审通过：原2 MEDIUM关闭，范围内未发现HIGH；独立10测试/Ruff/编译通过，主流程相关41测试通过。稳定性仅为阈值假设，小变速可在容差内；本次修复可保留工作区接入，旧证据7项绑定/正式质量问题仍未放行，不部署不换模型。
- 2026-09-22证据刷新：完整归档14-tail/harmonic/spectral与device-bass-ab四组自动产物后，以当前稳定拍格代码逐依赖真实重跑；不手工修改哈希/指标。正式人评原记录保留。新固定集使用closeout-review-20260922-v1，不覆盖0919历史评审。
- 2026-09-22刷新实测完成：4组自动证据真实重跑，旧目录完整归档；新26固定集0922全pending且当前指纹一致，26原始事件均不变、15结构记谱MIDI变化、10真实演奏语义不变。相关50passed，全量822passed/2正式旧人评指纹fail/6skip/0error；没有迁移旧评级，未部署。详见2026-09-22-evidence-refresh.md。
- 证据刷新fresh限定审查通过0HIGH/0MEDIUM，独立50测试与26条SHA/语义重算通过；正式人评仍pending，生产/部署不放行。
- 2026-09-22复评清单：按0922新旧文件指纹读取实际MIDI，区分音高事件数量/有序序列/起止/力度变化，附XML拍号/速度/谱号/调号等可见信息对比。语义相同不称仅元数据或自动通过；25条未变旧结论不用于此次新版，不迁移人工评级。
- 0922复评范围清单已生成closeout-review-20260922-v1/review-scope.md及绑定JSON：08事件90→92、14为264→239需数量/完整谱面复核；其余按音高有序序列/时值/力度/可见标记差异分类，10真人已比较内容未变但不自动继承旧评级。5项相关测试/Ruff/编译通过，清单不代表人工验收。
- 2026-09-22定位08零时值缺陷：_cap_eighth_note_durations把同刻下一事件当结束点，复现C4起止均0。最小修复改为下一严格更晚起音（无则八分槽上限），保持同刻所有音符正时值，不根据参考删音；这是时值合法性修复，不是泛音消除。
- 2026-09-22零时值修复闭环：fresh限定审查通过无新增HIGH/MEDIUM，补乱序/长间隔与近同时边界测试。11文件相关189passed（40.48秒，含OSMD/服务/pipeline），Ruff/编译/diff通过。08新94事件、53匹配/41额外/6未匹配，仅关闭时值合法性缺陷，不标音质通过；旧证据需随score.py变化刷新，未部署。
- 2026-09-22本轮修复冻结：第二次独立08审查确认无新增必须立即修复逻辑错误，零时值可关闭、08质量不可签收；最新API825/7指纹fail/6skip，Web140与tsc通过。保留音质缺口，不继续为降低计数扩规则。当前收尾索引docs/reviews/2026-09-22-closeout-status.md，未部署/未换模型/未整体提交。
- 冻结后最后刷新完成：90个app源码哈希未变，4自动证据归档并重跑，26固定集closeout-review-20260922-final全pending，绑定测试50通过。全量830passed/2正式旧人评指纹fail/6skip/0error（114.86秒）。不再改算法；剩余需实际复评，不能改hash代替。不部署不换模型。

### 15/16 最后一批教师反馈的核对与验收约束
1. 保存用户转述原文和机器可读条款，评级保留 requires_revision/未给正式档位；绑定本地源WAV/MIDI以及原/冻结最终XML的指纹，标明具体听审曲谱版本尚未确认。
2. 用现存生成器在内存重建原WAV，逐PCM样本比对后才引用生成器音符作为来源证据；独立比较Basic原MIDI和记谱MIDI、分开报告起音匹配与结束时值，不用曲谱可解析代替音乐正确。
3. 核对15的118次真实重击、14个完整八音循环及末尾6音；120四分BPM/0.25秒八分单位来自原源时间，老师“速度正确”不等于指定数值。16核对右手十二音与每2秒四音左手，单独揭示MIDI共享音note_off解析与生成WAV时值差异，不擅删低音/补和弦。
4. 输出隔离诊断和完整性/版本/反例测试，经fresh code-review复核。此轮先完成反馈与证据闭环，不改生产谱面规则，不生成新测试音频替代16，不重写旧评级，不部署或制作最终ZIP。
- 15/16反馈闭环核验完成：两源PCM逐样本重建一致；15原始118匹配/119额外，16原始120匹配/29额外（100ms起音），16源内15组三和弦之外各有一个真实低音，9处共享同键MIDI时值解析差异另记。新增11定向测试、Ruff/编译/diff通过，fresh限定两阶段审查无HIGH/MEDIUM，末组裁切文字LOW已修正。本轮完成反馈/来源/约束记录，生产记谱修复与具体评审导出版本仍未确认，未改旧音频或正式评级。
- 2026-09-23 15循环对齐第一步：只做隔离时间候选，原MIDI全部事件保留，不按11223355筛音。由模型起音80ms簇中心的中位间隔估计八分单位，以首簇为原点拟合槽序列；要求残差<=50ms、间隔稳定且拟合速度接近120（教师4/4八分约定+源时间验证），否则拒绝。每事件留原起止/槽号/新起止，重复同键同槽冲突拒绝，不合并真实重击。源MIDI只事后评价；分手/泛音尚不应用，先导出MIDI+审计而非宣称可用谱。
- 2026-09-23 15时间候选v2：模型网格拟合约0.25s、120BPM/4拍，237事件全保留、118真起音匹配、119额外不删。修正首音22.7ms与MIDI0拍错位，导出减原点并留audio=midi+origin映射；现场导出测试检查pitch/velocity/时值/拍号/小节边界。17相关测试/Ruff/编译/diff通过，分手/泛音未修，不标曲谱通过，v1仅历史。
- 15时间v2 fresh复审通过0HIGH/0MEDIUM，前审MIDI相位与导出测试两个问题均关闭，独立6测试通过。只完成循环时间候选，119额外音与分手仍待处理。
- 2026-09-23 15误音第一轮核验：复用当前harmonics默认删除判据，在原始时间（不先量化）逐事件测量；保留观察与删除的区别，不把harmonic observation当删除许可。复用同时真八度控制并新增同音弱重击波形控制，音高参考只事后评价；若证据不足则报告保留，不调宽阈值、不套音高模板，不改生产。
- 15默认泛音判据隔离核验：原237事件测量未选中删除，118真实起音/119额外保持；12个八度波形控制+3弱重击控制中，3个含真实弱上八度被默认removals误选（低音D4/E4/G4，上音幅度.04）。因此否决将该判据扩展到15，实际删除0，不调宽阈值。执行脚本快照保留，报告不代表生产修复完成。
- 15泛音核验相关20测试/Ruff/编译通过，fresh独立审查重生成15控制与237音核验确认unsafe_on_controls，无阻断问题。默认规则不能直接用于15，原候选不变119额外仍未解；本轮只完成假设否决，不宣称谱面改善。
- 2026-09-23 15同音尾部核验：保持已有泛音删除否决，单独调用已存在crossing-tail保守规则，使用原始MIDI事件、原WAV预处理及衰减/瞬态证据，quarter=.5秒来自此前15模型起音拟合120BPM。所有删除仅模拟统计，不改候选；参考仅事后检查重复击键损失。
- 15同音尾部迁移核验完成：默认保守衰减/瞬态规则选0删除，118匹配/119额外不变。129相关反例测试通过，独立完整重算一致；测试额外字段比较MEDIUM已修复并重跑确认，无HIGH/MEDIUM。fresh重派受数量上限限制，修复复核复用原审查任务。泛音和音尾两类现有规则均未安全清理15，不宣称音质修复。
- 15起音诊断：118真起音中46被现有独立起音标记判false，119余音中65判true，说明快速重复音/同时泛音无法靠该布尔标记区分。精确事件映射留档，不按参考改决策，不新增删除；停止放宽阈值路径，15质量仍失败，后续应改起音证据或人工编辑能力。
- 2026-09-24 16记谱单位隔离候选：先将原始模型MIDI以2/4、60四分BPM重新编码，保持全部音高、力度、起止秒数与乐器事件不变（允许MIDI tick误差），不量化、不删第四低音、不补三和弦、不自动分手。每2秒为候选小节，逐事件记录距强拍误差；原点为音频0秒展示假设，未声称独立检测到强拍。真实源仅事后统计和弦起音覆盖；结果不作为完整修复谱。补现场导出/速度拍号/时间一致性/禁止覆盖及篡改测试，独立审查后报告。
- 2026-09-24 16拍号单位候选实际导出：2/4、60 BPM，149原事件全保留，最大起止误差47.35微秒，120匹配/29额外/0未匹配保持。18相关测试/Ruff/编译通过，fresh审查0HIGH/0MEDIUM；仅MIDI表示层，不宣称强拍识别/三和弦/分手已修复，不改生产或旧源。
- 2026-09-24 16落点诊断：在原模型事件中按80ms固定首事件锚聚类，低于MIDI72且至少3不同音高的簇作为本样本和弦候选（不是通用分手规则），检查15簇/2秒周期及首原点相位。只报告到2/4候选强拍的有符号误差，不将弱拍吸附、不根据参考挑候选，不改起止/力度。对周期缺失/弱拍/链式聚类加反例，区分模型接近强拍与音乐强弱已识别。
- 16落点诊断完成：15组原起音距2/4候选强拍最大15.91ms，旧谱72.285ms、新谱38.636ms，均在80ms内；周期与相位分开，不整体平移。23相关测试/Ruff/编译通过，fresh0HIGH/0MEDIUM，完整强弱/分手/三和弦仍未解决。
- 2026-09-24 16谱面隔离重建：消费16-meter-only-v1原事件，显式2/4 60BPM、原点0与十六分网格，复用build_score；不得将参考和弦音高写入事件。检查输入/记谱音高多重集合、所有正时值及MIDI/XML一致性。若现有谱面构造丢音则失败留档，不宣称保留全部音。手部为现有推断非教师确认，分配和时值需复评。
- 16 MusicXML实际调用暴露2/4 KeyError：quantize._measure_units和analysis._downbeats映射缺2/4。最小补2/4=2拍，两处统一；不改变自动拍号候选排序，不声称自动检测2/4。覆盖build_score显式2/4的XML/MIDI、小节长度及原拍号回归，原失败预览保留。
- 16预览v2已生成149事件/2谱表/2/4/60BPM，时值经十六分网格量化而非秒数原样；仍82休止、每谱表最多3voice，不标音质通过。2/4两处映射修复的36分析/量化测试及6现场导出测试通过，XML可解析，独立审查进行中。
- 16谱面独立审查2MEDIUM后补证：显式meter/key置信度0且默认调号非推断；新增XML stripTies与MIDI/notation逐事件对照，实际153 vs149及部分时值不符，v3正确失败留档。38相关测试/Ruff/编译通过，只关闭2/4 KeyError及错误放行，底层导出一致性待定位，不交付v2为成功谱。
- 16导出门禁修复fresh复审通过：2MEDIUM关闭，独立19测试通过，完整XML153/MIDI149差异与failed审计一致；底层XML时值/事件差异仍明确未修复。
- 2026-09-24 16 XML差异根因复现：populate_part默认HarmonyConfig允许end相差1单位，合并后取最长结束使XML时值偏离MIDI。临时仅将谱面分组合并条件设duration_tolerance_units=0后，16 XML/MIDI/notation149事件完全相同。最小修复仅谱面分组使用严格时值，不改和声分析默认配置、原模型、参考音高或泛音阈值；补同起音不同时值/跨小节延音反例与完整候选重建。
- 16 XML时值修复实际验证：谱面分组只合并相同结束，不改默认和声分析；v4 XML/MIDI/notation149逐音一致，2staff/101rest仍待可读性复评。117相关测试含浏览器通过，Ruff/编译/xmllint通过；原失败候选保留，未部署/未换模型。
- 2026-09-24 16休止符核查：先检查纯休止声部和音符区间覆盖，再决定是否精简。v4共101休止：46被同谱表其他音完整覆盖、55含谱表静音，纯休止Voice为0；逐项及输入SHA留档polyphony-rest-audit.json。没有证据支持继续删声部，不改代码/候选、不生成空变化v5。后续应处理额外模型事件和音尾证据，不以隐藏休止符冒充修复。
- 2026-09-24 16额外事件专项：先对绑定原WAV提取现有泛音、起音、衰减和瞬态证据，再独立运行现有删除判据；源生成器经PCM核验后仅用于事后标注149事件中的匹配/额外及同音持续覆盖，禁止用参考选择删除。输出逐事件证据与误删统计、失败留档、不覆盖旧候选；现场重跑和反例测试后独立审查。无安全删除证据则保持曲谱不变并明确阻断原因。
- 16额外事件工具实跑v2：149原事件中120匹配/29额外（100ms），泛音与尾音现有规则均选0；额外12处同音源仍持续，尚不能据此删除。起音标记真音115true/5false、额外14true/15false，单独按无起音删除不可用。45相关测试及新增失败留档后的专项4测试、Ruff/编译/代码指纹通过。fresh独立审查工具返回unsupported call，未审查通过；未改谱面或生产。后续需更强时间频谱证据及弱音保护反例，不能继续单阈值扩张。
- 2026-09-24 16证据阻断原因：先纠正上一轮5个false起音的解释（均为音频开始约11ms，不是5个弱音反例）。为每个模型事件记录起音前窗口是否越界、衰减/瞬态检验缺失或超阈值原因，覆盖所有149事件而非只看12个参考标记；复用生产阈值，保持实际判据和输出不变。完成标准：边界/缺失/非有限值/严格阈值反例通过，真实输出逐项可复核，报告明确不能据此删除及独立审查状态。
- 16证据解释v4完成：纠正5真实false均为11ms音频边界，不能当弱音反例。12持续同音额外事件：9衰减误差超标、6瞬态超标、6瞬态不可用（重叠计数），全部未满足局部必要条件；未增加删除。诊断模块覆盖149事件，numpy bool序列化故障修复后v4实际重跑成功、v3失败留档。55相关测试/Ruff/编译/指纹通过；未实现新频谱分离算法、不生成新谱或评审包。
- 16证据解释fresh两阶段限定审查通过0HIGH/0MEDIUM/0LOW：独立22测试和149项真实重算通过，v2/v4既有事件与选择不变。仅工具完成，不标29额外音已修。
- 2026-09-24 16多泛音隔离实验：新增scripts限定的多频率投影，复用现有局部正弦投影器，以前段衰减预测后段幅相，逐个记录可分离泛音；近频冲突/病态拟合/低能量弃权。预先固定误差阈值0.01（沿用现有瞬态上限）、至少2条可分离轨迹且全部满足连续衰减才记为研究假设，不据此删音。先跑持续衰减与真实弱重复击键（多音高/相位/强度/噪声）控制，再跑16全部149事件，参考只事后评价；任何真实重击被误选即否决。所有结果留档，经测试和fresh审查，不接生产、不生成评审包。
- 16多泛音实验v1实跑：12纯衰减配置全true、24弱重复击键配置全false（纯衰减相位配置存在相同波形，不称独立12样本）；真实149事件全无连续假设。576轨迹中383频率冲突/137测量/56非衰减，首5音边界跳过。专项6测试/Ruff/编译/指纹通过，未删音或接生产，控制成功不代表复音质量改善。
- 16多泛音实验v2修复nondecaying轨迹被忽略的错误放行，新增真实增长泛音反例与控制真假断言；59相关测试通过，fresh复审无遗留HIGH/MEDIUM、1LOW类型标注建议，独立8测试通过。控制仍12true/24false，16原149事件选择0；实验未提供删音依据，不继续放宽阈值，不标音乐质量改善。
- 2026-09-24 真人录音覆盖验证：复用已有02-brahms真人片段及Basic Pitch原事件；核对源provenance、推理完成记录、normalized/raw MIDI哈希和事件数后，运行冻结的多泛音实验，无新阈值。无逐音真值，准确率/误删率必须null，禁止借合成MIDI评价真人。逐事件留测量与输入/代码指纹、覆盖与异常测试、独立审查；只读诊断，不改谱面或生成最终包。
- 真人覆盖验证完成：02-brahms绑定原录音/历史Basic原MIDI242事件，2边界/128不可测/112部分可测，连续假设0、实际删音0；无逐音真值，accuracy/false_deletion_rate=null，未证明安全或收益。15相关测试/Ruff/编译通过。停止继续扩阈值，标注真人数据缺口；不接生产、不生成评审包。
- 真人覆盖工具fresh两阶段审查通过：0HIGH/0MEDIUM、1LOW绑定分支补测建议；独立7测试、完整报告逐字段重算、输入哈希不变、5代码指纹与编译全部通过。仅诊断增量完成，音乐质量与真实弱音安全率仍未验证。
- 2026-09-24 真人重复音标注准备：从已绑定02-brahms模型事件选取同音前驱间隔0.1–1.2秒的候选（仅检索，不是真值），保留原录音精确PCM片段、时间映射与来源；输出pending标注模板和填写说明。验证器要求候选身份/源与片段哈希一致、人工reviewer、判断及真实重击的原片时间/音高，未完成或不确定不能通过。覆盖篡改/缺项/时间越界/真假类型；现场生成并独立审查，不自动标注、不删音、不生成最终评审包。
- 真人标注准备v2已生成120原PCM短片及全pending模板；validator补源PCM/映射复算防止manifest联合篡改，主13相关测试/Ruff/编译通过，fresh两阶段复审0HIGH/0MEDIUM、独立6测试通过。仍需实际听辨，未获得真人逐音真值，不自动删音或生成最终包。
- 2026-09-24 真人标注本地页面：复用现有离线评审简洁样式，新增单页播放/前后导航/候选位置/人工判断与音高时点填写/草稿导入导出。file直接打开，不fetch、不依赖Python服务器；导出允许pending并明确只是草稿，原labels不覆盖。浏览器验收播放、切换保留、刷新恢复、错误导入、下载及手机宽度；独立审查后提供本地入口，不生成最终ZIP。
- 真人听辨页面完成本地实现：file播放、候选导航、字段填写、manifest隔离缓存、草稿导入导出；修复非法字段污染全局缓存与缓存配额阻断导出的两项MEDIUM。主8Python测试与实际Chrome故障反例通过；375px/桌面目视无截断，已与既有本地对照页比较。原120labels仍pending，不修改音频/模型/评级，不生成最终包。
- 听辨页面最新独立复审通过0HIGH/0MEDIUM，M1/M2关闭，Chrome与独立VM缓存故障反例通过。交付入口real-repeat-annotations-v2/index.html，实际听辨仍需人工。
