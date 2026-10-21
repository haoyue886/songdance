# 2026-10-21 PostgreSQL ARM64隔离运行验收

从7bb44b5继续本地容器验收，无生产代码修改、不部署或推送。沿用用户对官方PostgreSQL16/MinIO固定镜像的校验下载及导入授权，仅使用现有代理，不改全局代理或镜像源，不禁用TLS。原商业测试库、云存储和供应商凭据均未参与；USD0.18停止补退及部分退款记录不变。

## 镜像取得与导入核对

有界诊断发现PostgreSQL官方manifest已可访问；首次完整下载因解压层超过沿用Redis的256MiB上限被主动拒绝，不是摘要不匹配。仅该下载器解压上限改为512MiB，压缩对象仍限128MiB，index/manifest/config/blob/diffID校验保留。

两次下载进程曾重叠写相同临时归档，属于执行失误；两进程均退出0且报告同一归档摘要。导入前重新校验最终tar整体SHA256、config及全部11层解压摘要，均通过，未直接使用未验证的并发输出。

- 官方源：`docker.io/library/postgres:16-alpine`，linux/arm64。
- index：`sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea`。
- ARM64 manifest：`sha256:2c942175a1255a9abe0366e48c1b401d9f50f835b04dfea13f111609b5530df7`。
- 官方config：`sha256:ef738a34a8651d11b2bace81c55c7e2187f786b484add6c83070884340074368`。
- 下载tar：`145f4c19f0c6082e6e9c2856df53d7c41e9747dce4fc548c37520593729313b7`。

实际执行`docker load -i songdance/.data/notavue-pg-s3-20261021/postgres-16-alpine-arm64.tar`成功。Docker inspect ID为`sha256:24b5c241a22e2daa0ebde55a41277efdf13e9eb391068b69192cc970ebca67c8`，与官方config不同，不宣称ID匹配。随后`docker save`导出，config字节SHA256、11层diffID和inspect RootFS均与官方config一致，平台linux/arm64。ID表示差异原因未定。无网络`docker run --rm --network none --entrypoint postgres postgres:16-alpine --version`输出PostgreSQL16.15。

## 实际运行与清理

执行`songdance/api/.venv/bin/python /tmp/notavue-postgres-smoke-20261021.py`退出0。API镜像固定`sha256:4a1594c1b50d8821a760a93893ba345afe1abf0701c03e850c679a86ed68a14e`（上一轮完整ARM64构建），没有重建或替换API代码。

唯一随机internal网络、两个一次性卷、随机数据库密码，全部业务开关false/Test环境；无宿主端口、宿主目录或云端连接。本轮存储使用local，不启动MinIO。

- 原entrypoint将新PostgreSQL库迁移到014，与镜像head一致，users为0行。
- API容器内`/health`返回200，Redis PONG。
- 原cleanup入口运行，failed和temp_failed均0；仅为空库检查。
- 原Worker入口监听独立空队列，SIGTERM后退出0；不代表真实转谱任务验收。
- Basic Pitch0.4.0/ONNX Runtime1.28.0导入、Node22.23.1和FFmpeg执行通过。
- 镜像内未发现所检查的.env、tests/scripts/dist/experiments/.venv及sqlite3文件。
- finally结果无错误；随后分别执行`docker ps -aq`、`docker network ls -q`、`docker volume ls -q`并限定`--filter label=notavue.preflight`，三类结果均空。未批量停止其它资源。

`songdance/api/.venv/bin/python -m pytest -q /tmp/test_notavue_pg_s3_preparation.py`为5 passed，覆盖清理异常继续、错误消息不泄漏密码、014版本限制；相关脚本编译通过。脚本、下载/导入校验证据和运行/清理JSON私密归档于`.data/notavue-pg-s3-20261021`，不入Git。

## 独立复核

独立审查以fresh上下文完成脚本检查，续接只读复核本轮证据，无可行动问题：归档脚本一致、两份tar的配置与11层实际摘要一致、inspect RootFS/平台一致，运行和清理JSON未冒称S3通过。审查未调用Docker或网络，真实运行由主Agent执行。原始registry index/manifest未留档，离线复核可确认归档与已记录官方config digest一致，不能离线重建registry来源链；来源核验依赖下载器当次TLS请求和摘要断言。

## 保留限制与下一步

MinIO匿名token虽未过期，但未授予`minio/minio`的pull scope，manifest返回401 UNAUTHORIZED；未据此断言标签不存在或仓库私有。不更换未授权来源或要求用户提供凭据，本轮收窄为PostgreSQL-only。结果明确`storage_backend:local`、`s3_verified:false`，S3读写/分片清理仍未验。

本次未验证商业表并发/真实业务、数据库备份恢复、生产权限与连接、目标云端amd64、漏洞扫描或专业音乐质量。上一轮镜像pip check因Basic Pitch声明缺TensorFlow失败继续保留，不因本轮运行通过而关闭。下一步解决固定MinIO官方镜像取得或明确新的隔离S3验收目标，再补真实协议检查；生产Live仍未放行。
