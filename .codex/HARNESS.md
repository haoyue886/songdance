# Harness 维护说明

这套配置保留项目知识、技能和证据要求，把具体执行方式交给当前任务决定。主入口是根 `AGENTS.md`；本文件仅在维护 harness 或寻找验证命令时读取。

## 分层

| 位置 | 职责 |
|---|---|
| `AGENTS.md` | 项目定位、任务范围、验收和协作边界 |
| `.agents/skills/*/SKILL.md` | 按需加载的领域工作方法，引用只在相关时读取 |
| `.codex/agents/*.toml` | 独立审查和规则分析的角色定义 |
| `.codex/scripts/check.py` | 显式、可重复执行的验证入口 |
| `.codex/EVOLUTION.md` | 基于证据的按需规则改进 |
| `.codex/hooks.json` | 空的项目 hook 集合，不安装隐式动作 |

空的项目 hook 集合不禁用用户、系统或插件的 hooks，也不能证明宿主已加载本仓库配置。需要确认实际加载时使用当前版本提供的 hooks 查看能力；不要靠文件存在推断生效。

## 验证命令

Python 3.11+，无第三方 Python 依赖。此项目已有的解释器位于 `songdance/api/.venv/bin/python`；系统 `python3` 可能版本不足。下列命令在仓库根目录执行，脚本本身也支持从其他工作目录用绝对路径调用。

```bash
songdance/api/.venv/bin/python .codex/scripts/check.py
songdance/api/.venv/bin/python .codex/scripts/check.py web
songdance/api/.venv/bin/python .codex/scripts/check.py api
songdance/api/.venv/bin/python .codex/scripts/check.py full --dry-run
songdance/api/.venv/bin/python .codex/scripts/check.py e2e
```

| Profile | 实际范围 |
|---|---|
| 默认 / `harness` | harness 行为测试、配置解析、技能名称与可识别的本地引用 |
| `web` | 在 `songdance/web` 依次执行 pnpm lint、typecheck、test、build |
| `api` | 在 `songdance/api` 用本地 venv 执行 Ruff 检查 app/tests、pytest |
| `full` | harness + web + api，不包含 E2E、专业质量复评或发布验证 |
| `e2e` | 单独执行项目 `pnpm test:e2e`，需要其配置要求的浏览器和服务 |

`--dry-run` 检查目录和命令是否存在，输出 cwd 和 argv，不运行子进程；不能证明依赖已安装或测试能通过。执行失败返回非零并停止后续检查；harness 没有发现可执行测试时同样失败，不能以零测试通过。脚本不安装依赖、不操作 Git、不清端口，具体测试或构建命令仍可能创建自己的临时/构建产物。

命令入口是可选的组合工具，不强迫每次修改都跑全量。技能前言检查仅覆盖必需字段，不是完整 YAML 验证；修改技能时还应使用可用的 skill-creator validator。

## 2026-09-25 迁移

迁移前基线提交：`184cca6`。仅修改 harness 及其临时缓存忽略规则，保留产品代码、Spec、DEV-PLAN 和历史待审建议。

已撤下的行为及原因：

- `auto-push.sh`：只匹配命令文字，没有核验提交成功；隔离测试中失败提交、dry-run、echo 都会调用 push。
- `pre-tool-shell.sh`：根据文字匹配任选一个 tsconfig；包含 `pnpm dev` 的只读搜索也进入五个端口的强杀分支。
- `mark-review-needed.sh` / `stop-gate.sh`：单个全仓文本标记不能绑定当前 diff，patch/相对路径漏报；手写 clean 可以放行；正常放行还会删除被 Git 跟踪的状态文件。
- `detect-feedback-signal.sh` / `check-evolution.sh`：把普通需求关键词记成纠正，启动时抢占当前任务处理历史建议。

原六个 shell 文件均为 0644，配置却直接执行它们；复现的原样调用返回 126。脚本测试通过显式 bash 和替身命令完成，并不意味着这些危险分支曾在真实会话中运行。

主规则缩减重复路由和初始化仪式；技能改为按输入充分度推进。审查按风险和交付批次执行，保留实际测试、UI 验证、转谱专业复评和范围约束。删除通用规则中的“CPU 0% 就是死锁”“一律 tsc”“每文件 300 行”等误判来源。

四条历史 proposal 保持待审，不把本次通用精简视为对其业务建议的批准。历史产品案例只增加参考范围声明，正文保留。

## 本次验证

- 独立审查覆盖任务路由、授权边界、测试行为和重要约束，发现的两处问题已修复并复审：发布漏洞门槛遗漏、空测试集合误报成功。
- Python 3.11 实跑 14 项 harness 测试通过，覆盖命令顺序、工作目录、失败停止、缺失依赖、dry-run、空测试/无 TestCase 和实际断言失败；Ruff 通过。
- 11 个技能通过系统 skill-creator 的 quick_validate；配置 JSON/TOML 与可识别的本地技能引用通过检查。
- 独立 Agent 在隔离目录实际修复一个 Python 负数价格格式问题，先复现失败再通过回归；没有为了局部修复新增 Spec、DEV-PLAN 或 TypeScript 检查。
- 本次未修改产品行为，未运行产品 Web/API/E2E 全量测试、真实发布或音乐质量复评；没有验证宿主重新加载配置，也没有做模型效率的前后对照。

## 维护与回退

新增规则先给可复现失败和预期改善，再用代表性任务检查是否误伤其他任务。未做真实任务的前后对照时，只报告验证和结构变化，不报告虚构的效率提升。

恢复时先检查当前 diff 和后续改动，按需从迁移前提交提取具体文件，不对整个工作区做硬重置。回退旧 hooks 会同时恢复已知缺陷，不建议整体启用。

## 官方依据

核验日期为 2026-09-25；文档描述的是官方当前能力，本机版本和信任设置仍需独立验证。

- OpenAI《Rethinking skills and prompts for GPT-6 Astra》，2026-09-11：按任务取上下文、缩短技能描述，避免过度规定流程。来源 `https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra`
- Hooks：配置使用顶层 hooks 对象，支持 async；项目 hooks 受信任配置影响，不同来源的 hooks 会合并。来源 `https://learn.chatgpt.com/docs/hooks`
- Build skills：name/description 用于选择，正文和资源按需加载。来源 `https://learn.chatgpt.com/docs/build-skills`
- Subagents：自定义角色文件使用 name、description、developer_instructions；窄范围角色适合独立审查。来源 `https://learn.chatgpt.com/docs/agent-configuration/subagents`
