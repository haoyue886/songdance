# 2026-10-21 部署与安全本地预检

受测代码基线 `1d30676`，本批只改文档；用户确认Creem Test控制台未找到周期模拟入口后，转入独立部署准备。不部署、推送、开通Live或创建外部资源；不恢复原商业Test库/服务，不继续18分补退。

## 已执行结果

- 在 `songdance/api` 执行 `.venv/bin/python -m pytest -q tests/test_deployment_contract.py tests/test_commercial_config.py tests/test_auth_config_preflight.py tests/test_settings.py`：121 passed。覆盖现有配置合同、HTTPS/Redis/密钥约束、代理默认路由拒绝、Test/production限制；不是实际平台配置通过。
- `.venv/bin/python -m pytest -q tests/test_phase6.py -k 'proxy or cors'`：5 passed/20 deselected。验证现有可信代理与CORS边界，不代表Railway实际边缘CIDR已取得或部署后链路已测。
- `.venv/bin/python -m pytest -q tests/test_human_quality_gate.py`：8 passed/1 failed，失败为 `test_real_piano_human_gate_has_fixed_licensed_sources` 的评审suite_fingerprint与当前compute_suite_fingerprint不匹配。这是2026-09-29准备记录中同类既有阻塞，本批没有修改生产流水线、评审或音频指纹，不继承旧评级宣称当前质量通过。
- `songdance/api/.venv/bin/python -m pip check`：No broken requirements found。pip缓存目录权限警告不影响该结果；仅说明依赖一致性，不是漏洞扫描。
- `docker version --format '{{json .}}'`：Docker客户端29.6.2/darwin/arm64、context=colima，Server=null；Colima socket不存在，命令退出1。没有启动daemon或改Docker context。
- `docker compose version`：unknown command，退出1；`docker-compose`命令未找到。容器构建/运行、迁移及Worker/Cleanup启动仍未执行，不能用Dockerfile静态检查替代。
- `pip-audit`命令未找到；本批没有安装工具或获得Python漏洞报告，未重复运行之前网络失败的npm审计，当前漏洞核验仍未完成。未声称无高危漏洞。

上述pytest保留Starlette/httpx、pkg_resources两项已有依赖弃用警告。没有全量API/Web测试、生产Web构建或音乐重新转谱；本批文档修正不影响这些实现，不把9月旧构建称为当前产物已构建。

## 部署目录修正

现仓库根下有 `songdance/`，但旧deployment.md要求单独将该目录作为仓库根推送，并写Vercel root=web；会误导按另一仓库布局配置。现明确保留当前仓库/锁文件，Vercel根目录为 `songdance/web`；Railway路径说明为应用目录相对路径，真实root/config path/build context必须在实际平台一起核验，尚不是已验证部署步骤。

API Dockerfile有 `COPY requirements.lock`、`COPY app` 和 `COPY docker-entrypoint.sh`，本地命令因此明确为在仓库根执行 `docker build -f songdance/api/Dockerfile songdance/api`；不能仅设置Dockerfile路径而假设其上下文自动正确。该命令本批未运行，Docker守护进程仍不可用。Railway配置仍保持原样，避免在未核平台语义时猜改；Worker/Dispatcher/Cleanup与API需同版本且共享服务配置，生产认证/商业开关依现有限制，不能直接打开Creem Live。

修正部署文档不改变生产行为、配置、依赖或当前工作目录，未新建部署服务/凭据。部署入口会自动迁移，迁移前备份/回退与目标私网数据库仍须实际环境核验，不能将模板placeholder当有效生产配置。

## 下一步与保留门槛

先让本机Docker守护进程可用，再实际构建API镜像并在一次性资源验证启动/迁移/Worker/清理；不要求启动Compose来完成单镜像构建，Compose是否需要按后续测试方案决定。平台目录、S3、代理CIDR、HTTPS会话、密钥、备份恢复与容量尚待实际环境准备；用户希望亲自操作第三方软件时给出当前一步，Agent继续负责本地核验。

真人质量评审指纹不一致、实际依赖漏洞核验、长音频与成本/法律/正式商户门槛继续保留。Creem真实周期推进/重订单列待测，不阻止独立准备，也不以本轮121/5项或文档完成整体BA/发布批准。

最终独立文档/配置审查无可行动问题，核对当前仓库路径、Dockerfile COPY上下文、锁文件及旧9月失败记录一致；`git diff --check`通过。审查者未重跑121/5项或Docker，不将本次审查作为镜像/平台运行验收。
