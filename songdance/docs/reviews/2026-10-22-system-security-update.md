# 2026-10-22 Debian 容器系统包更新与复验

基线 `a6359c1`。本批在 API Dockerfile 的两个运行阶段启用严格 APT 索引错误处理并升级可更新的 Debian 包；没有修改 Python/Node 锁定依赖、生产开关或业务配置，不部署、不推送、不启用 Live。FFmpeg 的漏洞仍未修复，本记录不作为发布批准。

## 构建与系统更新

`APT::Update::Error-Mode=any` 与更新、安装命令通过 `&&` 串联。用不可达索引复验时，普通 `apt-get update` 返回 0，严格模式返回 100，避免镜像源失败后构建静默继续。Dockerfile 只使用 Debian 官方签名源，没有关闭 TLS/GPG 校验或允许未认证包。

使用仓库中的 `songdance/api/Dockerfile` 完整构建本地 ARM64 镜像 `notavue-api:system-repo-a6359c1`，Docker 显示的 manifest 摘要为 `sha256:d842a9c8beb19f5826bac064693e3bd6002730112656c43f814fa591741bf2f4`。本轮前次构建的 Node 工具阶段已升级 4 个包，仓库复建复用该缓存；Python API 阶段实际升级 22 个包，完整 22 步构建成功。使用已有本机代理作为本次 `docker build` 参数，未将代理写入运行时 ENV。仓库 APT 源使用 HTTP 加官方签名校验，未宣称全部下载经 HTTPS。容器内系统为 Debian 12.15，`libc6` 为 `2.36-9+deb12u14`，OpenSSL 为 `3.0.22-1~deb12u1`。

实际成功构建命令在 `songdance/api` 下执行：`docker build -t notavue-api:system-repo-a6359c1 --build-arg HTTP_PROXY=http://host.docker.internal:7897 --build-arg HTTPS_PROXY=http://host.docker.internal:7897 --build-arg ALL_PROXY=http://host.docker.internal:7897 .`。本机 legacy builder 不接受最初尝试的 `--progress` 参数；那次在构建前退出 125，随后移除该参数完成构建。

## 漏洞扫描

使用 Trivy 0.76.1 和同一份离线数据库扫描更新前后 ARM64 镜像。数据库 `UpdatedAt` 为 `2026-10-21T13:15:34Z`。Debian 漏洞匹配记录从 1,235 条、543 个唯一 ID 降到 1,069 条、414 个唯一 ID；减少 166 条记录、129 个唯一 ID。更新后仍有 8 条 critical、279 条 high、461 条 medium、289 条 low 和 32 条 unknown 的 Debian 匹配记录。Python 扫描保持 11 条、10 个唯一 ID，与更新前相同。

Trivy 的 ImageID 为 config 摘要 `sha256:ac0f70623a60cc75e12f14d158c4548318abdda93cf081848d4e7ff27d112d4a`，与 Docker 的 manifest 摘要含义不同。导出归档核对 manifest→config 关系、全部 16 层压缩摘要与解压 diffID，并与 Docker RootFS 和 Trivy DiffIDs 逐项一致；镜像内 143 个应用源码文件和 requirements.lock 与仓库一致。扫描不是对另一个标签产物的推断。

镜像内 `pip check` 仍因 `basic-pitch 0.4.0` 声明 TensorFlow 而未安装返回 1；对更新前镜像得到相同结果。Dockerfile 有意通过 `--no-deps` 使用 ONNX 路径，因此本批没有改变这个既有可选后端元数据缺口，也不声称 `pip check` 通过。

Debian Bookworm 当前提供的 FFmpeg 仍为 `7:5.1.9-0+deb12u1`。Debian tracker 将 CVE-2026-107678 标为 vulnerable，Trivy 也未给出该包族的修复版本。虽然已有独立进程、超时和 Linux 资源限制，仍不能把这些控制描述成 FFmpeg 补丁或 OS 沙箱；解析器风险和发布阻塞继续保留。

## 运行验收

- `pytest -q tests/test_deployment_contract.py tests/test_audio_preprocessing_security.py`：25 passed；补强契约测试后单独重跑为 5 passed。契约测试现要求同一 `RUN` 命令链中的严格更新、升级和安装，并拒绝 `|| true`、命令输出伪装、注释伪装与拆分命令。
- 固定最终镜像 ID 的 Linux ARM64 runner：10 项通过，包括 WAV/MP3/M4A 实际解析与裁剪、legacy/durable 上传失败计数、health 响应、无凭据继承、CPU/地址空间/文件限制和超时进程组终止。
- 固定最终镜像 ID 的 PG/Redis/S3 联合隔离 smoke：迁移到 014、health 200、空 users、Redis PONG、S3 字节往返/exists/delete/精确 multipart 中止、cleanup 无失败、Worker 优雅退出均通过。只使用随机 internal network 与临时卷；无宿主端口、宿主目录挂载或供应商凭据。自动清理后核对本轮容器、网络和卷均为空。
- Ruff check/format、`git diff --check` 通过。独立审查确认最初的字符串顺序测试存在 P2 盲区，后续 shlex 分词又暴露引用分隔符可伪装的 P2；最终保留引号并增加负例，复审确认旧反例、单双引号分隔符、整链 echo、注释、忽略失败和拆分 RUN 均被拒绝，当前两阶段合法链通过，无遗留可行动 P0/P1/P2。审查者执行 5 项契约测试及静态检查、复核归档与记录，未重演 Docker 构建、联网扫描或 smoke；真实执行由主 Agent 留证。

扫描 JSON、镜像归档、构建日志和 smoke 证据放在私有 `.data/notavue-system-security-20261022`，不入 Git。未操作真实数据库、云存储、供应商或用户账户。ARM64 本地构建不验证生产 amd64 平台、备份恢复、真实容量或音乐质量。

## 后续阻塞

本批减少了可由 Debian 当前版本修复的包漏洞，但没有清零系统风险。下一步需取得 FFmpeg 上游或 Debian 的实际修复版本，或单独完成可审查的更强操作系统隔离方案；随后对目标架构重新构建、使用更新漏洞库复扫并测量真实容量。完成这些工作前，仍不得以本地 smoke 通过宣布容器安全或正式上线。
