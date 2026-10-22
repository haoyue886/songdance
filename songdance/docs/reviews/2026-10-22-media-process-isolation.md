# 2026-10-22 Linux 媒体子进程文件与网络限制

基线 `e6b5a06`。上传校验和裁剪使用的 FFmpeg/ffprobe 在独立 helper 中安装 Landlock 与 seccomp，然后执行解析器。此批只缩小该调用路径的文件和网络权限，不更新 FFmpeg，不改变业务计费或生产配置，不部署、不推送。

## 实现边界

调用方显式传入当前输入和输出路径。父进程以 `O_EXCL | O_NOFOLLOW`、0600 预创建输出，已有文件或符号链接均拒绝覆盖。Landlock 允许指定输入读取、指定输出写入/截断；只读开放 `/usr`、`/lib`、`/lib64`、动态链接器缓存、时区文件和存在时的 FFmpeg 配置，不给父目录递归执行规则。运行库树仍可读、可执行，不能将凭据或业务数据放入该树后声称受此策略保护。

Linux 要求 Landlock ABI 4。设置 `no_new_privs` 后安装文件权限和无允许端口的 TCP 规则；seccomp 同时拒绝 `socket/socketpair`、`io_uring_*`、`pidfd_getfd`、ptrace 和权限/属主/时间戳/xattr 修改族，含 `fchmodat2`、xattrat 和 `file_setattr`。ioctl 只允许 `FIOCLEX/FIONCLEX` 描述符继承标志操作，拒绝 inode/device 操作。这些补充覆盖 Landlock 未处理的普通网络与文件元数据接口。跨架构、x32 ABI 不能绕过过滤；目前实现 aarch64/x86_64，真实内核验收仅为 ARM64，未运行 amd64 实测。ABI 不足、架构不支持或任何策略安装失败都会退出，调用方返回既有媒体错误，不能降级到未受限解析。

原有墙钟/CPU/地址空间/栈/文件/输出限制、无应用凭据环境、超时终止当前进程组保持。该组合不是完整容器或独立 UID/PID 隔离：仍共享 UID，未封锁同 UID 信号/调度控制；fork 后各进程分别计算 rlimit，恶意后代也可能新建会话脱离原组。不能据此声称父进程完全隔离、聚合资源受控或 FFmpeg CVE 已修复。

范围仅限 `audio_validation` 调用 `run_media` 的上传探测/裁剪。Worker 的 `app.pipeline.audio.preprocess_audio` 以及 YouTube/yt-dlp 的独立媒体调用尚未接入本包装器，不标为隔离完成；YouTube 生产开关继续关闭。Worker 当前输入是既有裁剪生成的 WAV，但这不等于其解析路径已具有同样的操作系统限制。

## 验证与证据

- 宿主最终运行 `pytest -q -p no:cacheprovider tests/test_audio_preprocessing_security.py tests/test_pipeline.py tests/test_jobs.py tests/test_durable_jobs.py tests/test_long_audio_probe.py tests/test_deployment_contract.py`：88 passed、1 Linux-only skipped。focused 为 26 passed、1 Linux-only skipped，含 ABI/安装失败时不执行解析器、输出文件/符号链接不覆盖、双架构过滤器含 x32/错误架构和 ioctl 例外测试。Ruff check/format、`git diff --check` 通过；macOS 跳过项不冒充 Linux 内核验证。
- 仓库 Dockerfile 以已有代理作为临时 build 参数构建的最终 ARM64 镜像为 `notavue-api:media-isolation-final-e6b5a06`，Docker 摘要 `sha256:c6ca531001027bac8a0635d77a8951e94b779da2524644d4ef845650fc6cfb48`。镜像中143个应用源码文件及 requirements.lock 与仓库逐字一致。使用本轮随机名称、`--network none --cpus 2 --memory 2g --init --rm` 容器直接执行仓库 AST 提取的 Linux 回归函数：指定输入读取和输出写入通过，`/etc/passwd` 读取、兄弟临时文件写入、UDP socket 创建、合成文件 chmod/utime/xattr 修改均拒绝；`file_setattr` 即使本内核未实现也由 seccomp 明确返回 EPERM。初轮探针另确认 `/app/app/main.py` 读取被拒。
- 同一最终镜像运行10项 Linux 资源/格式检查，真实 WAV/MP3/M4A 探测裁剪、legacy/durable失败限流及health、无凭据继承、512 MiB地址空间、文件上限、CPU硬上限和当前进程组超时终止均通过。不将普通派生进程终止测试外推为恶意后代无法脱离进程组。
- 最终同摘要镜像 PG/Redis/S3 联合 smoke 退出0：迁移014、空users、health200、Redis PONG、S3字节往返/exists/delete/精确multipart中止与同前缀保护、空库cleanup和Worker优雅退出通过。finally清理无错误，随后限定本轮标签核对容器/网络/卷均空。
- 初次测试脚本 bind mount 因 Colima 不共享该宿主路径失败；改用 stdin。一次未加 `-i` 的空 stdin 容器退出 0，不计为验证。一次将宿主 Docker runner 误放容器执行因无 docker CLI 失败、未创建资源，改回宿主后 smoke 通过。保留这些边界，不把空执行或错误执行算作通过。
- 原全禁ioctl令Python合成探针加载脚本的FIOCLEX操作失败，日志保留；仅放行FIOCLEX/FIONCLEX描述符标志后，精确最终镜像跟踪测试和真实格式检查通过，其他ioctl仍拒绝。
- 私有证据在 `.data/notavue-landlock-20261022`；包含脚本、镜像元数据、成功/失败日志和临时资源清理结果，不入 Git。没有调用真实供应商、原业务库、用户文件或云存储。

## 官方定义与审查

通过 agent-reach 的网页/GitHub 读取后端核对 [Landlock](https://docs.kernel.org/userspace-api/landlock.html)、[seccomp](https://docs.kernel.org/userspace-api/seccomp_filter.html) 及 Linux 官方 [x86_64 syscall 表](https://github.com/torvalds/linux/blob/master/arch/x86/entry/syscalls/syscall_64.tbl)、[generic syscall 表](https://github.com/torvalds/linux/blob/master/scripts/syscall.tbl)，文本快照和 SHA256 保留。Landlock `EXECUTE` 是递归文件执行权限，不能当目录遍历权限；ABI 4 只覆盖 TCP，且不覆盖普通权限/xattr 等元数据修改。独立审查确认父目录授权、网络间接接口、元数据旁路和架构证据表述问题均已修复，未发现本批遗留可行动P0/P1/P2。审查者独立运行新增6项测试及ioctl后双架构2项复核，核阅最终Linux日志与宿主回归；未重演Docker构建或生产环境。最后联合smoke由主Agent执行与核对。

## 发布边界

FFmpeg 5.1.9 的 CVE-2026-107678 仍未修复。上一批同系统包镜像扫描仍有 Debian 1,069 条/414 唯一 ID，本批不把应用权限变化视为漏洞消失，也未对新镜像复扫。目标 Railway 主机须验证 Landlock ABI 4/seccomp、目标 amd64 架构、聚合容量、备份恢复和音乐质量；当前不批准上线。目标不支持策略时解析失败关闭，需要调整部署环境，不能禁用保护绕过。
