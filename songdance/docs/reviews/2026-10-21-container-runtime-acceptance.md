# 2026-10-21 ARM64镜像及隔离运行验收

代码基线dca3b00，本轮无生产代码修改、不部署或推送。用户继续授权本地容器验收，并单独明确允许经既有代理下载Docker官方Redis归档、校验后本地导入。原商业测试库、凭据及18分退款记录未参与。

## 网络恢复与产物

Docker直拉Redis仍超时；容器直连PyPI的1MiB探测44.8KB/s，临时使用已有host.docker.internal:7897代理为153.6KB/s。整次build代理参数使legacy builder重跑系统依赖，apt仍慢，因此主动停止并移除本轮精确中间容器7635d0cc2e8d；exit137来自主动停止，不是OOM结论。

最终临时Dockerfile仅两条pip RUN命令增加HTTP_PROXY/HTTPS_PROXY，不改仓库Dockerfile、锁文件或索引，不禁用TLS、不持久代理ENV。复用原系统层后完成全部依赖与Basic Pitch安装。构建成功镜像notavue-api:preflight-dca3b00，ID `sha256:4a1594c1b50d8821a760a93893ba345afe1abf0701c03e850c679a86ed68a14e`，linux/arm64。不是原Dockerfile无代理直接构建成功的证据；传输调整已私密归档。

Redis经Docker官方匿名只读token获取7.4-alpine ARM64清单，逐项校验index、manifest、config、压缩blob及7层解压diffID，离线mock1项及独立审查通过。首次执行被自动审批拒绝，用户补充授权后才执行下载/docker load。前置urllib探测因本机CA验证失败，未禁用验证，最终requests使用既有CA链正常完成。

官方ARM64 manifest `sha256:1f09a89a207d794a8c61d9edfc26e7c58427de10ccef7c5d18d638df79a63b85`，config `sha256:ec4f171e9ff071bb2a1c936057d3be00206069b028b6c0d61df2477e1dd02c42`。Docker inspect报告ID `sha256:cc0dd7c828f4083b9c504658b2717269f978f85117e923d0422670adf59fa2d4`不同，初次等值断言失败保留；不能宣称inspect ID匹配。另docker save后逐字节比较config和每层diffID完全一致、inspect RootFS也逐层匹配，独立离线复核确认。具体ID表示差异原因未定。无网络版本探针为Redis7.4.11。

## 实际隔离运行

项目venv运行 `/tmp/notavue-container-resume-smoke-20261021.py` 成功。唯一标签/名称、internal网络、一次性volume，无host端口、host目录或供应商凭据；Test环境和全部功能开关关闭。

- 原入口自动Alembic迁移到014，与镜像alembic heads一致，新users表0行。
- API容器内health200、一次性Redis PONG。
- 原cleanup入口实际运行，JSON的failed/temp_failed均0；空库检查，不冒称真实文件清理已测。
- 原Worker入口实际监听独立队列，SIGTERM退出码0；空队列检查，不冒称真实转谱任务整链。
- Basic Pitch0.4.0/onnxruntime1.28.0可导入，Node22.23.1与FFmpeg可执行。
- finally清理所有自建容器、network及volume，后续按标签查询三类资源均为空。一次性版本/模型探针均--rm，无更改用户daemon或其它项目容器。公开镜像及校验归档保留。

## 镜像依赖与敏感产物检查

镜像内87个requirements.lock包逐版本匹配，Basic Pitch0.4.0一致。/app未携带.env、数据库、音频、私钥及tests/scripts/dist/experiments/venv；app142文件树SHA256为 `e8187076730f0cb68a985f4914764e510def828ee2243c1479d1582f68599222`。仅实际检查范围，不把模式扫描称为全面秘密审计。

镜像 `python -m pip check` 退出1：basic-pitch0.4.0 requires tensorflow, which is not installed。既有Dockerfile明确--no-deps避免Linux TensorFlow依赖，生产代码明确加载ONNX；仍如实保留metadata依赖缺口。随后无网络/挂载、1CPU/2GB一次性容器实际调用生产transcribe_audio处理1秒静音，ONNX推理完成并返回NoNotesDetectedError。保留缺CoreML/TFLite/TF可选后端、ARM CPU vendor及静音除零警告；不将此作为音乐质量或pip check通过。未安装TensorFlow掩盖失败。

## 审查与限制

镜像下载及临时构建配方、smoke的目录/标签替换已独立审查。既有smoke两项P2修正（异常继续清理、temp_failed）保持；独立mock、脚本编译通过。具体源码和proof归档在私密data/notavue-container-resume-20261021，不入Git。

本次仅linux/arm64、空SQLite、本地volume和空队列运行；未验证目标云端amd64、PostgreSQL/S3、真实Worker转谱、备份恢复、平台HTTPS/代理或漏洞扫描。真人质量指纹既有失败仍阻塞发布，生产Live禁止不变。运行成功不等于上线就绪，后续优先补目标架构/PG/S3及依赖漏洞核验。
