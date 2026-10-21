# 2026-10-21 S3源码测试镜像隔离验收

从e750c5a继续本地S3协议验收。无生产代码或项目依赖修改，不部署、不推送、不启Live；原商业测试库、对象存储和供应商凭据不参与，USD0.18停止补退记录不变。

## 官方分发核对与源码构建

原固定MinIO版本`RELEASE.2025-04-22T22-12-26Z`的Docker Hub匿名token没有pull scope，manifest仍401；版本README指定的官方Quay仓库完成匿名认证后同样401。官方旧二进制下载站的该ARM64校验文件返回410。当前官方README说明社区版改为源码分发、旧二进制不再维护；这些响应不证明所有旧附件均消失。官方GitHub Release另列ARM64安装包，校验文件可取得，本轮未安装或执行该包。

用户明确选择同版本官方源码构建临时镜像，允许额外临时Go工具链与构建依赖。通过agent-reach的GitHub/gh后端核对官方标签，GitHub API报告签名标签验证为true；本地未另行执行GPG验签。固定对象：

- annotated tag：`f19c534b9f457773dcd043d977433e1a71525c3b`。
- 源码commit：`0d7408fc9969caf07de6a8c3a84f9fbb10a6739e`。
- 官方commit源码归档SHA256：`dccf285038a63d48ad52efdfa38c92af525f2d44b0217df5fdc9dc83d7d6075d`。
- Go1.24.2 Darwin ARM64工具链归档：76,241,216字节；官网SHA256 `b70f8b3c5b4ccb0ad4ffa5ee91cd38075df20fdbd953a1daedd47f50fbcff47a`，下载后大小与摘要均匹配。

源码、工具链、GOPATH/GOCACHE均置于`/tmp/notavue-minio-source-20261021`，不全局安装、不修改全局代理。依赖仍用官方Go proxy/checksum database，经已有本机代理传输，不禁TLS。首次`go mod download`两包unexpected EOF，保留日志后有界重试一次成功；256个模块归档下载完成，`go mod verify`通过。

实际执行`songdance/api/.venv/bin/python /tmp/notavue-build-minio-source-20261021.py`，使用CGO_ENABLED=0、GOOS=linux、GOARCH=arm64、kqueue/trimpath、readonly模块配置。`go.mod`和`go.sum`前后SHA一致；ELF为64位小端AArch64。二进制SHA256 `82bb776f4c47cf574aece2afb56439c1fa34e24526324bd7d838a2e09bc3ee64`。

随后执行`/tmp/notavue-package-minio-source-20261021.py`，固定现有Python基础镜像完整ID `sha256:4f5d923c9dcea037f57bda425dd209f3ec643da2f0b74227f68d09dab0b3bb36`，禁止拉取、无网络构建。产物`notavue-minio-source:0d7408f`，ID `sha256:c051262a47bc422605c792f6c18f5dd2d27f6b20ff48e691e537783df0ac5284`。最终平台/基础RootFS前缀核对通过；无网络自动删除容器内SHA256与本地二进制一致，`--version`输出DEVELOPMENT.2025-04-22T22-12-26Z、完整源码commit及go1.24.2 linux/arm64。明确是本地源码构建，不冒称官方预编译镜像或逐字节复现其产物。

## 真实协议与联合运行

执行`songdance/api/.venv/bin/python /tmp/notavue-s3-source-smoke-20261021.py`退出0。第一次启动的自动审批超时、命令未执行；按工具允许重试一次后执行成功。

使用既有API镜像4a1594c1…、官方已校验PG16/Redis和本地源码MinIO。新建唯一随机internal网络、三个一次性卷、随机数据库及S3密码，无host端口/目录或供应商凭据。Test环境、业务开关false，MinIO更新关闭；所有run禁止自动拉取，API和MinIO直接使用已核验完整镜像ID。

探针写入前限定Test/S3、本轮随机MinIO主机名和固定本地测试桶/身份，调用生产`create_storage`和`S3ObjectStorage`，真实S3协议结果：

- 小文件上传/下载字节一致，exists正常。
- 删除目标对象后目标不存在，同前缀其它对象仍在。
- 创建两个未完成multipart upload，删除目标时只中止精确key的上传，同前缀其它上传保留。
- 清除对照对象后，测试桶对象和multipart列表均空。仅验证未上传分片的upload标记中止，未覆盖大文件分片传输。
- 原入口将新PostgreSQL库迁移到014、users为0；API health200、Redis PONG。
- 原cleanup空库运行failed/temp_failed均0；空队列Worker监听并SIGTERM退出0。
- finally清理结果errors为空；之后分别用`docker ps -aq`、`docker network ls -q`和`docker volume ls -q`限定`--filter label=notavue.preflight`核对，三类均空。不清理其它项目资源。

## 检查、审查与保留边界

`songdance/api/.venv/bin/python -m pytest -q /tmp/test_notavue_s3_source_preparation.py`为6 passed，覆盖异常清理继续、密码错误消息脱敏、014限制及已核验ID/禁止拉取。新增测试首次缺少SUFFIX夹具导致1失败，补齐测试上下文后通过；不是生产逻辑失败。相关脚本编译通过。

独立审查发现核验后仍用可变tag启动的P2，已修为完整ID并禁止拉取，复审关闭；打包脚本审查无新增可行动问题。源码归档1367个普通文件与构建目录逐一一致，工具链归档SHA独立核对通过。最终独立离线证据复核无可行动问题：重新计算源码tar和二进制SHA、ELF架构、锁文件与源码一致，镜像proof与运行记录一致，留存脚本与已审版本一致，成功/失败日志分别保留。审查未联网、未重编译或重演Docker，真实执行与清理以主Agent记录为依据。

脚本、源码归档、模块锁文件、二进制及构建/镜像proof私密保存于`.data/notavue-pg-s3-20261021/minio-source`；运行/清理JSON在其父目录，权限0600，不入Git。Go缓存和工具链仍在临时目录，项目依赖不变。

本轮仅本机ARM64、同版本源码MinIO的隔离S3适配器及空库联合运行。未验证真实云存储权限/生命周期、生产数据库备份恢复、跨架构、真实转谱整链、容量或漏洞。既有Basic Pitch镜像pip check缺TensorFlow和专业音乐质量门槛继续保留，不据此宣布上线。下一步优先做锁定依赖与容器漏洞核验，再补目标部署环境配置与恢复验证。
