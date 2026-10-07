# 商业化整链本地验收

日期：2026-10-07；基线 `b451527`。用户要求继续本地开发，尚未配置独立供应商项目。未推送、部署或开启真实收费。

## 结果与边界

`pnpm test:commercial:e2e` 最终 **24 检查点通过**。测试启动实际 Next.js/BFF 与锁定 Supabase SDK、FastAPI、迁移 013 的新 PostgreSQL、最小权限会话读取角色、新 Redis 与 RQ、Basic Pitch 和原导出路径；仅外部身份/支付协议及托管支付页面由本地测试服务提供。生产接口返回体没有替换，未知响应场景先让真实请求提交再丢失响应。

- 桌面与 375px 完成 OTP 登录、付款确认等待、真实 HMAC 重复事件处理、Pro 授额、音频裁剪/提交、队列/模型、MusicXML 渲染与 Canvas、原音/转录播放、MIDI/MusicXML/PDF 下载、Portal 取消和账户删除。桌面另走 Google PKCE 回跳、checkout/上传响应丢失恢复与同 key/同任务核对。
- API 验签实际 RSA JWT/JWKS 并查询只读会话表，BFF 使用 HttpOnly Cookie，浏览器不收到 refresh token。各账号业务归属一致，跨账号任务、下载、删除被拒绝。
- 付款成功回跳仍为 Free/确认中，真实签名事件持久收件及 Billing Worker 后才授 Pro。重复通知仅一个已付周期；三格式下载/播放不新增推理、队列或消费流水。两项 Pro 各消费 15 秒，余额 1,785 秒，Portal 取消保留原权益。
- 桌面重新激活同一订阅不授第二周期或重置已用量；账户删除经实际 Creem HTTP 取消适配器停止续费一次。移动端已安排取消时不重复调用。两个删除 checkpoint 校验源/attempt 产物仍在，完成时检查文件前缀与临时文件均消失，旧未过期签名下载 404，停用账号不能获取新票据。
- Free 静音音频实际处理返回 NO_NOTES_DETECTED，释放一次；随后真实成功消费唯一月额度，再次提交 429。不重置赠送或借用 Pro 额度。

实际计数：**4 次模型调用、4 次 RQ 执行、2 次供应商 checkout 创建、1 次 HTTP 取消、11 次 webhook 提交、0 次 refresh 桥调用、0 个外部请求**。四次推理使用合成 A4/静音；桌面/移动两份实际下载的成功 MIDI 各有一个 A4 音符，XML 可解析并有实际音符，PDF 有有效头尾，保存大小与 SHA-256。它们证明业务编排和真实引擎执行，不证明真实钢琴转谱质量或专业固定集通过；refresh 桥本批没有新增整链覆盖。

最终本地报告：`web/test-results/songdance-commercial-e2e-D5CUS1/report.json`。脚本保留阶段截图、下载哈希、账本/状态事实及清理结果，不保留真实凭据。执行型 Agent 查看桌面/手机及重新激活阶段，主 Agent 查看实际 mobile-score，SVG/Canvas 非空，375px 无横滚/重叠。

## 配置前置检查

新增 `python -m scripts.check_commercial_config --env-file PATH`，只读明确文件，复用认证检查、解析器和隔离来源的 Settings，不从进程/默认 dotenv 补项、不联网。仅输出字段/错误码及当前短音频合同，验证状态固定未完成。关闭空模板可以格式有效但完整商测前置条件为 false；不能把 exit 0 当生产准备批准。

API 目录：`.venv/bin/pytest -q tests/test_commercial_config.py tests/test_auth_config_preflight.py tests/test_settings.py`，**115 passed**，2.17 秒（两条既有依赖弃用提醒）。覆盖环境隔离、密钥/DSN/异常值不回显、私密文件权限、FIFO/重复键/展开拒绝、URL 与依赖/合同。直接 CLI 合成案例：关闭空配置 exit 2，完整测试配置 exit 0，供应商/数据库实际权限/SMTP/商户/后台及 production_ready 仍为 false。准备说明见 [商业化配置](../commercial-readiness.md)。

## 进程与资源恢复

新测试栈独占随机端口、临时数据库、存储和队列，不使用已有 3000/3001/8000。Node 中断进入幂等清理；Python 处理 Uvicorn 重抛的信号，资源清单记录自有 PG/Redis/模型 Worker。恢复核验 Redis 原 run ID、PID、目录和 Worker 的精确命令/root/进程组，等待结束后才报 stopped。检查失败会保留目录和失败报告，不通过删目录掩盖残留。

`SONGDANCE_TEST_REAL_AUTH_SERVICES=1 .venv/bin/pytest -q tests/test_commercial_stack_lifecycle.py`：四个实际退出场景 **4 passed**，112.52 秒，覆盖 SIGTERM、SIGINT、空闲强杀和活动 Worker 时强杀 API 后显式恢复。新增进程检查失败路径定向 **1 passed**（0.09 秒），活 Worker 未被误认退出、清单仍 false。Node 收到重复 SIGTERM 的实际中断验证也通过，报告 `web/test-results/songdance-commercial-e2e-cuaiGX/report.json`；成功全流程清理验证为 true。最终只读进程核对没有商业化测试残留。

首轮存在脚本启动模块路径错误、托管导航/响应体读取互相等待以及移动端 hydration 前设置文件的测试问题；改为模块启动、按当前页面和真实 owner/provider 事实核对、有界等待与实际 hydration 屏障后通过。没有改变产品逻辑迎合测试。两轮早期异常退出确实留下自启 Redis，主 Agent 按明确 PID/cwd 回收，已有 6379 服务未动；后续正常/重复中断/强杀恢复都按清单验证，不冒充首轮即成功。

## 独立审查与接续

fresh reviewer 确认并复验关闭两个 P2：关闭/中断遗漏自启服务（包括活动 Worker 与 `ps` 失败不能误报退出），以及仅查数据库而不能发现物理文件遗漏。最终审查无遗留可行动 P1/P2。审查者独立配置测试 **89 passed**、信号库行为与资源错误路径隔离复现，核对最终 24 项报告；未重复完整浏览器或真实供应商。

本批 Python Ruff、Node 语法、脚本 ESLint 和 diff 检查通过；没有新增依赖或修改生产业务运行代码/开关。未重跑无关 Web 全量构建或音乐质量集。

当前本地认证收费链路已有完整证据；接下来按配置准备说明创建/选择独立 Supabase 与 Creem Test 项目，补真实 Google/SMTP、测试卡/税额/Portal/退款及撤销。真实音乐固定集/专业复评、容量成本、正式政策和适用 5/10 分钟 LA 门槛仍待完成，不勾选整套 BA 或宣布可上线。
