# 2026-10-21 本地容器构建预检与网络阻塞

受测代码基线3121a61，用户已自行启动Docker，授权本地API镜像构建与一次性隔离验证，不部署、不推送、不打开Live。原商业Test库、身份、密钥和18分部分退款记录均不读取或修改。

## 实际执行

- 沙箱内初次Docker socket访问permission denied，随后按审批授权只读确认Docker Server29.5.2、Linux/aarch64。此前Docker CLI29.6.2与Server版本不同，不混报。
- `docker build --progress=plain -t notavue-api:preflight-3121a61 -f songdance/api/Dockerfile songdance/api`因缺buildx、legacy builder不接受--progress而退出125。移除仅日志参数，继续同一Dockerfile/锁定依赖构建。
- 首次实际传输上下文1.094GB；发现api/dist约617MB、experiments约426MB并未被忽略，虽然Dockerfile不COPY这些目录，仍会传入本地daemon。只新增 `.dockerignore` 的 `dist/` 和 `experiments/`，不删除或修改目录内容、不改锁文件。现有app/requirements.lock/alembic.ini/docker-entrypoint.sh四类COPY来源均保留。
- runtime-tools阶段完成Debian ARM64索引下载与tini安装（9291KB索引3分24秒），Python基础系统依赖层命中已有缓存。pip读取requirements.lock，取得多项ARM64 wheel元数据，没有在本次进度中出现架构不支持错误；尚未完成全部依赖解析/下载/安装，不能据此宣称兼容性通过。
- 官方PyPI下载pretty_midi 5.6MB包实测约17.6KB/s，单包约5分钟；同时`docker pull redis:7.4-alpine`两次在registry-1.docker.io的Head请求超时，用户自行尝试同样超时。未切换全局代理、Docker镜像源或Python索引，不连接业务Redis替代。
- 因网络已阻塞后续完整镜像/Redis联调，明确停止本轮中间构建容器72d975ab42fe（仅该自建容器），构建进程退出137为本次主动停止结果，不当作代码崩溃或OOM证据；随后删除该停止容器，保留成功构建缓存。API镜像未完成，未执行启动/迁移/健康/Worker/Cleanup验收。

## 已验证的局部产物

修改忽略规则后执行：

```sh
docker build --target runtime-tools -t notavue-runtime-tools:preflight-3121a61 -f songdance/api/Dockerfile songdance/api
docker run --rm --network none notavue-runtime-tools:preflight-3121a61 sh -c 'node --version && tini --version'
```

上下文实际846.8KB，stage构建成功，镜像`sha256:b15251d444ccc8d1ddf49b62a54d11f9270f66c3efeafe48e9515ab3c3fab286`/arm64；实际Node v22.23.1、tini0.19.0。仅Node工具阶段，不含最终Python应用，不冒称完整API产物。运行时禁网络、不挂载主机数据或端口，容器退出自动移除。

精确构建容器及notavue.preflight标签容器查询均无遗留。未创建smoke network/volume，未启动一次性或业务数据库/Redis/API/Web/Worker；公开Redis镜像未拉取成功。Docker守护进程保留用户启动状态，没有停止用户Docker或清理其它项目镜像/容器。

## 待运行的验收脚本

私密 `/tmp/notavue-container-smoke-20261021.py` 已准备并编译，用唯一标签/名字、internal network、一次性volume验证API自动迁移空SQLite/health、Redis ping、cleanup、Worker启动与SIGTERM退出，finally逐项清理。无host目录挂载、host端口或真实凭据；此脚本未执行，不代表该调用链已真实通过，也不替代PG/S3生产验收。

独立审查发现并修复两P2：单个docker rm超时/OSError会中断剩余清理，现逐项捕获异常、继续清理并按资源名汇总后报错；原cleanup只核failed0，现解析cleanup_cycle JSON并同时核failed/temp_failed均0。独立离线mock验证四种失败计数组合、两种清理命令异常及正常路径；复审无新增问题。未写生产代码或新增依赖。

## 继续条件与限制

需要恢复Docker daemon访问Docker Hub以及构建容器访问PyPI的网络后，再重试原完整API构建及Redis拉取。不要通过改变依赖版本、削弱生产合同或引用旧API镜像冒充本轮完成。构建和联调都限定本地，后续只清理带本轮身份的资源；镜像构建成功后仍须做运行、依赖漏洞/产物敏感数据与目标架构验证。

真人质量指纹既有失败、当前漏洞扫描、真实PG/S3、Railway root/config/context、平台HTTPS/备份恢复仍未验证，不整体签收部署或BA。本批只交付忽略规则修正、局部stage产物和真实失败记录。

最终独立3文件复核无可行动问题：忽略项不排除Dockerfile实际COPY来源，未发现运行代码依赖dist/experiments；归档脚本与复审版本相同且私密/受Git忽略。`git diff --check`通过。审查者未调用Docker或网络，运行结果引用主Agent实际证据；不扩展完整API或部署通过。
