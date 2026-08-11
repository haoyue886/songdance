# SongDance Overseas SEO Plan

> 数据日期：2026-08-11
> 当前状态：首轮本地实现与验证完成；待生产域名、GSC 配置和数据回流
> 数据说明：当前没有 Ahrefs、Semrush、Keyword Planner 或 GSC 实测数据。下列关键词优先级基于产品匹配度与搜索意图假设，不包含虚构的搜索量或 KD。

## 1. SEO 定位

**目标受众：** 需要把钢琴录音带入 DAW 或记谱软件的独立音乐制作人、编曲者和演奏者。

**需求假设：** 用户会使用 `audio to MIDI converter`、`piano audio to MIDI`、`MP3 to MIDI` 和 `audio to sheet music` 等任务型关键词寻找能直接上传、试听和导出的工具，而不是阅读泛泛的 AI 音乐文章。

**差异化：** SongDance 同时提供 MIDI、MusicXML、PDF、五线谱与钢琴卷帘验证；公开真实转录示例；明确自动转录误差和 24 小时临时保存边界。

**变现假设：** 当前先验证工具启动、任务完成和导出，不提前建设付费墙。若 GSC 流量和导出行为成立，再验证更长片段、批量处理或高级导出的 freemium 边界。

## 2. 关键词分组

| 分组 | 关键词示例 | 意图 | 当前判断 |
|---|---|---|---|
| 核心工具 | `audio to MIDI converter`, `piano audio to MIDI` | 立即转换 | A，产品能力直接匹配 |
| 输入格式 | `MP3 to MIDI converter`, `WAV to MIDI converter` | 按格式转换 | B，需避免重复薄页面 |
| 乐谱输出 | `audio to sheet music`, `audio to MusicXML` | 获得可编辑乐谱 | A/B，SongDance 有真实输出 |
| 场景 | `convert piano recording to MIDI`, `transcribe piano recording` | 钢琴制作/扒谱 | A，范围最诚实 |
| 教程 | `how to convert piano audio to MIDI` | 学习后使用工具 | B，可反链核心工具页 |
| 比较 | `best audio to MIDI converter`, `audio to MIDI converter alternatives` | 比较工具 | C，竞争与证据要求更高 |
| 知识 | `MIDI vs MusicXML` | 了解格式 | B，适合支持导出决策 |

## 3. 首批 10 个页面资产

| 优先级 | URL | 主关键词 | 页面类型 | 难度假设 | 状态 / 理由 |
|---:|---|---|---|---|---|
| 1 | `/audio-to-midi` | `audio to MIDI converter` | 核心工具页 | 中高 | 本轮上线；最高意图，导向真实上传工具 |
| 2 | `/` | `piano audio to MIDI` | 产品首页 | 中 | 本轮优化元数据与结构化数据 |
| 3 | `/examples` | `piano transcription example` | 真实示例 | 低中 | 本轮优化；提供可验证证据 |
| 4 | `/piano-audio-to-midi` | `piano audio to MIDI` | 子功能页 | 中 | GSC 验证后建设，避免与首页互抢 |
| 5 | `/audio-to-sheet-music` | `audio to sheet music` | 子功能页 | 中高 | 需强化 MusicXML/PDF 示例后建设 |
| 6 | `/mp3-to-midi` | `MP3 to MIDI converter` | 格式页 | 中高 | 只在核心页出词后建设独立格式说明 |
| 7 | `/wav-to-midi` | `WAV to MIDI converter` | 格式页 | 中 | 与 MP3 页分阶段 A/B，不批量生成 |
| 8 | `/guides/how-to-convert-piano-audio-to-midi` | `how to convert piano audio to MIDI` | 教程页 | 中 | 为核心页提供内部链接与教学意图 |
| 9 | `/guides/midi-vs-musicxml` | `MIDI vs MusicXML` | 知识页 | 低中 | 支持导出选择，不承诺转录准确率 |
| 10 | `/best-audio-to-midi-converters` | `best audio to MIDI converter` | 比较页 | 高 | 需真实竞品测试数据，暂缓 |

## 4. 首批 SEO Briefs

### `/audio-to-midi`

- Primary keyword: `audio to MIDI converter`
- Secondary: `piano audio to MIDI`, `convert piano recording to MIDI`, `audio to MusicXML`
- Intent: 立即上传并转换
- Title: `Audio to MIDI Converter for Piano Recordings | SongDance`
- H1: `Audio to MIDI Converter for Piano Recordings`
- First-screen promise: 上传 MP3/WAV/M4A 钢琴片段，导出 MIDI、MusicXML 和 PDF，并先用真实谱面验证结果。
- Differentiation: 真实公共领域示例、可试听原音/转录演奏、透明的 90 秒与自动误差边界。
- CTA: `Convert piano audio`
- Internal links: `/transcribe`、`/examples`、`/privacy`
- Schema: `WebApplication` + `FAQPage`

### `/`

- Primary keyword: `piano audio to MIDI`
- Intent: 了解产品并开始转换
- Title: `Piano Audio to MIDI Converter | SongDance`
- H1: 保持中文产品主张，但正文与元数据明确 piano audio to MIDI、MusicXML 和 sheet music。
- CTA: 进入 `/transcribe`
- Internal links: 核心工具页、真实示例、处理流程、隐私说明。
- Schema: `WebApplication`

### `/examples`

- Primary keyword: `piano transcription example`
- Intent: 转换前验证输出质量
- Title: `Real Piano Audio to MIDI Transcription Example | SongDance`
- Required proof: 授权来源、真实音频、当前流水线产物、可播放/可下载结果和质量边界。
- CTA: `Transcribe your piano recording`
- Schema: `WebPage`，不伪造评分或 Review schema。

## 5. 发布清单

- [ ] 生产环境设置 `NEXT_PUBLIC_SITE_URL` 为最终 HTTPS 域名。
- [x] 每个公开页面拥有唯一 title、description 与 canonical。
- [x] `/robots.txt` 与 `/sitemap.xml` 可访问，sitemap 不包含匿名任务 URL。
- [x] `/jobs/*` 输出 `noindex, nofollow`，避免临时结果进入索引。
- [x] 首页和核心工具页输出与可见内容一致的 JSON-LD。
- [ ] GSC 验证环境变量配置完成并提交 sitemap。
- [ ] 埋点能区分 SEO 页面访问、工具开始、任务完成与导出。
- [x] 首页、核心页、示例页之间存在上下文内部链接，无孤儿页。
- [x] 不创建未经 GSC 验证的批量格式/乐器模板页。

## 6. 30 天迭代

- 第 1 周：部署技术 SEO 和 `/audio-to-midi`；验证 canonical、robots、sitemap、结构化数据与 GSC 收录。
- 第 2 周：按 GSC 查询词修正 title/H1/FAQ；为有曝光无点击的词优化 SERP 文案；获得首批合规目录/产品资料页链接。
- 第 3 周：只扩展已有曝光支持的一个页面集，优先在 `/piano-audio-to-midi` 与 `/audio-to-sheet-music` 中二选一。
- 第 4 周：比较自然搜索访问到 `tool_start`、任务完成和导出的漏斗；合并无曝光内容，规划下一轮教程或格式页。

## 7. 成功信号

- 技术：公开页面被发现、抓取和索引，匿名任务页不被索引。
- 搜索：核心页开始获得目标查询曝光；有曝光页 CTR 与排名可持续改善。
- 产品：自然搜索访问产生真实工具启动、转录完成和导出，而不只停留在页面浏览。
- 扩张门槛：首批页面出现稳定曝光或转化前，不扩展 programmatic SEO。
