# 2026-10-22 原始音频预处理与安全节流修复

基线31b1f56，处置上一批审查确认的原始媒体探测DoS问题。本批不部署、不推送，不连接供应商、原商业库或云存储，不变更依赖、计费规则或生产开关。恢复Billing-Auth-Spec既有要求：失败释放业务额度，安全节流独立保留。

## 行为修复

1. Memory/Redis JobQuota的cancel只释放active名额，小时和全局日安全计数不退回。Free/游客的小时桶与Pro独立安全桶继续分开；业务usage/guest账本失败释放逻辑不变。重放已有提交仍复用原任务，不额外收取准入次数。Redis键名、TTL和旧job元数据结构不变，无数据库迁移或清空计数动作。
2. legacy及durable上传的validate_audio_file、extract_clip_to_wav均在线程池执行。探测或裁剪运行期间/health可响应；取消HTTP请求时等待当前线程工作结束，再清理临时文件和并发名额。
3. 媒体调用经独立Python解释器设置rlimit后exec原ffprobe/ffmpeg，不在线程内使用preexec_fn。禁用stdin、清除应用凭据环境，只传PATH/LANG；限制格式为WAV/MP3/MOV、协议为file、编解码线程为1。子进程输出先写受限临时文件，stdout最多读取64 KiB；超时kill整个新进程组并wait回收主进程。
4. ffprobe的JSON形状、stream对象和有限duration须合法；异常统一为既有AUDIO_DECODE_FAILED/CLIP_EXTRACTION_FAILED，不将原媒体输出或凭据写入响应。

| 限制 | ffprobe | ffmpeg |
|---|---:|---:|
| 墙钟超时 | 15秒 | 120秒 |
| CPU硬上限 | 10秒 | 60秒 |
| Linux地址空间 | 512 MiB | 512 MiB |
| Linux栈 | 8 MiB | 8 MiB |
| 单文件大小（含输出/日志） | 512 KiB | 16 MiB |
| 打开文件数 | 64 | 64 |
| Core dump | 禁用 | 禁用 |

继承的限制更严格时继续保留，不扩大。macOS拒绝栈hard-limit变更，初版由此误拒正常文件；已将栈/地址空间限制明确限定在Linux，保留初次失败日志，随后真实格式回归通过。macOS只证明其余限制及兼容性，不替代Linux内核验收。

## 实际验证

在songdance/api使用项目Python3.11环境，未安装新依赖。

- `pytest -q tests/test_audio_preprocessing_security.py`：20 passed。覆盖取消后不退小时/日安全数、重复取消不退数、legacy/durable失败两次后在parser前429、文件/数据库清理、两个预处理阶段的健康响应、取消期间文件和名额仍保留、子进程环境/输出/文件上限、超时终止进程组、异常JSON拒绝。
- `SONGDANCE_TEST_REAL_AUTH_SERVICES=1 pytest -q tests/test_paid_quota_redis.py`：7 passed。实际Lua验证并发原子限额、取消不退小时/日数、释放active、Free/Pro共享全局但小时桶独立。fixture新建随机端口/目录并核对Redis PID，结束关闭，仅使用本轮服务。
- 扩大相关回归：jobs、durable_jobs、entitlements、phase6、youtube、usage_ledger、guest_usage、pipeline、long_audio_probe及安全测试，168 passed。该次执行早于追加的4项异常JSON用例，后者纳入focused及全量运行；最后又补duration=null/{}两例，focused20通过，全量未为这两例重跑；不重复累计为独立测试数。
- 相关9个Python文件Ruff通过，format检查通过。运行手册同步安全次数、子进程限制及故障处置。

API全量`pytest -q`实际结果为1652 passed、94 skipped、10 failed、3 errors（382.60秒），没有标为全量通过。offline_structure_review的三项fixture错误明确记录了沙箱Chrome启动/EPERM；另有两项谱面浏览器失败。用已有兼容Node25、关闭实验WebStorage并扩大本地浏览器权限重跑这三个测试文件的相关范围，8 passed，未改断言，不把该重跑当作完整全量通过。

剩余8项是7个既有指纹绑定失配和1个历史结构评级断言（07-soft当前direct_use、测试仍要求needs_redo），涉及crossing candidate/harmonic、device bass、human quality gate、review rebuild、spectral family、phase36结构回归与结构评审。独立审查在临时目录导出HEAD代码/脚本/测试，引用同一固定素材重跑上述8例，仍为8 failed、失败点一致；344个相关受跟踪依赖文件均等于HEAD。82个未受跟踪素材不能作历史HEAD字节比对。未更新旧报告、移除样本或重算评级；这些质量门槛继续阻塞发布。

## Linux候选镜像与内核实测

沿用上一批仅pip RUN使用已有代理的临时Dockerfile及依赖缓存构建，仓库Dockerfile未变。候选`notavue-api:preprocessing-31b1f56`，linux/arm64，Docker身份 `sha256:d7fdcc0db4dfa0fd02477df64c726d05274765b1430600758d441e9e831ffda0`。完整app源码SHA256与受测文件再次核对一致。

执行私密runner：单个随机名称容器，network=none、2CPU/2GB、--init/--rm、无host目录/端口或业务凭据，finally精确清理本轮容器；事后标签查询为空。10项实际检查全部通过：

- 使用真实ffprobe/ffmpeg分别解析并裁剪WAV、MP3、M4A。
- Linux实际ASGI legacy/durable上传各失败两次后429、active与临时文件清除，health200。
- 子进程实际读取CPU/AS/stack/FSIZE限制及确认无合成凭据继承。
- 600 MiB分配实际被512 MiB地址空间限制拒绝；超额文件写入被内核拒绝。
- CPU无限循环实际被硬上限SIGKILL；墙钟超时后父进程已回收、派生进程停止运行（允许等待init回收的zombie）。

这验证了内核限制和普通格式兼容，不是恶意FFmpeg漏洞PoC或生产容量测试。无联网扫描或部署动作。

## 独立审查、边界和下一步

fresh独立code-reviewer核对最终调用链/资源退出/异常取消/旧Redis结构/业务计量，未发现本批可行动P1/P2；独立相关回归94 passed，最后TypeError分支的6项异常元数据用例复核通过。审查未调用Docker或真实Redis，对应实际结果由主Agent运行并留证。

同步探测阻塞事件循环及失败退回安全计数的既有问题已修复；并发与窗口上限限制重复失败输入。子进程仍以API同UID访问文件系统，rlimit按单进程生效，协议白名单不等于OS网络/文件系统沙箱。FFmpeg及Debian系统库未更新，上批1235条OS包/漏洞匹配记录、543唯一ID的处置仍保留；本批不重新扫描不变的依赖/系统层，也不宣称CVE已修复。下一步为解析器/基础系统更新或更强隔离方案及重建重扫，真实容量、音乐质量和上线门槛仍需验收。

源码指纹、宿主测试日志、Linux runner/payload与结果私密保存在`.data/notavue-preprocessing-20261022`（0700目录、0600文件），不入Git。无删除用户数据、提高限额、额外邮件或模拟交易。
