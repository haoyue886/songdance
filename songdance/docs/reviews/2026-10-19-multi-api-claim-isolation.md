# 2026-10-19 多API实例认领隔离集成验收

两个独立HTTP API进程、同一可丢弃PostgreSQL下的三轮游客任务竞争通过；替换其中一个进程后归属和权限保持。**本地签名JWT集成结果，不等同真实Supabase签发、浏览器或云端多副本部署验收。**生产逻辑未改，BA-11不整体勾选。

## 环境与证据

新增 `api/tests/test_auth_multi_instance_real_services.py`。沿用现有opt-in PG fixture，在新的临时集群迁移业务表，并创建合成auth.users/auth.sessions及私有songdance_auth视图和受限reader；不读取或启动历史验收库。

测试通过multiprocessing的spawn模式运行两个独立Python进程，各自创建原FastAPI app、业务engine、认证engine和连接池，随机绑定127.0.0.1 HTTP端口。父进程用禁用环境代理的httpx调用HTTP接口；响应附带仅测试使用的instance/PID，逐次检查实际处理进程。记录任务锁前两个OS PID及两个不同PostgreSQL backend PID，不能由单进程两个TestClient冒充。

认证使用两份本机RSA签名JWT，两subject/session不同、email相同；原SupabaseVerifier验签、claim检查、私有视图会话SQL及issuer+subject业务映射均保留。只替换JWKS获取为本机公钥，不替换验证器。每身份先分别访问两个API的/me，确认跨实例业务ID相同、两身份的业务ID不同。

## 三轮竞争及重启检查

- 每轮新建一个明确的2秒静音合成游客任务和源文件；API a/b分别使用alice/bob、bob/alice、alice/bob。测试不规定某身份必须获胜。
- 仅本轮初次claim请求在原 `SELECT transcription_jobs...FOR UPDATE` 执行前进入跨进程Barrier(2)，15秒有界等待。事件含request ID、进程/连接PID和monotonic时间戳，断言两个到达均早于任何响应，避免只检查顺序请求。
- 三轮均一200一404。随后在两个API分别检查两身份读取及携原capability重复认领：胜者200、败者404；两个API的匿名旧cap读取均404。
- 每轮最终PG owner匹配胜者，guest_secret_hash为NULL，queued/stage queued/attempt1保留，source asset引用及源文件字节完整。
- 停止API a，再spawn新进程/新连接池/新端口，断言PID不同。三个已认领任务在新实例上的胜者读取/重放仍200，败者仍404；这一步排除依赖原实例内存维持归属。

HTTP业务检查含4次/me、三轮共36次初次竞争及权限重放、替换实例后12次读取/认领。health只用于启动就绪检查，不算业务验收项。付款/用量/邮件/队列Worker未开启。

## 已运行

API目录：

```sh
.venv/bin/ruff check tests/test_auth_multi_instance_real_services.py
.venv/bin/python -m compileall -q tests/test_auth_multi_instance_real_services.py
SONGDANCE_TEST_REAL_AUTH_SERVICES=1 .venv/bin/pytest tests/test_auth_multi_instance_real_services.py tests/test_auth_same_email_real_services.py -q --tb=short
.venv/bin/pytest tests/test_auth_ownership.py tests/test_auth_coordination.py -q --tb=short
```

最终Ruff通过；集成 **2 passed，11.73秒**（本轮多进程与上轮同邮箱各1项），权限/协调回归 **18 passed，2.44秒**。两条既有依赖弃用警告。初版新增文件Ruff行长问题已修；新增源内容断言后再次Ruff修正1行，未改验收条件。首次多进程测试单跑1 passed，9.78秒；最终以上述组合为准。

finally按multiprocessing持有的自有Process对象terminate/join，未退出时kill/join并断言全部停止；HTTP client、消息队列及父子engine释放。PG fixture最后以check=True停止新集群，测试退出0，无长期服务/公网入口/供应商访问。未发信、付款、创建真实客户或修改系统代理，未提交/推送/部署。

fresh独立code-reviewer检查本轮测试和原JWT/claim调用路径，未发现可行动问题；独立执行多进程PG测试 **1 passed，9.94秒**，Ruff通过。首次沙箱绑定回环端口被拒，随后正常提权审批运行成功。审查者确认spawn独立进程、独立engine、真实HTTP与不同backend PID断言，未修改仓库或调用供应商。

## 未覆盖

不覆盖真实Supabase/JWKS网络、浏览器/BFF跨实例刷新、负载均衡/TLS、共享Redis容量与队列任务、两个真实付费客户、认领与删除竞争。已有单API真实双浏览器竞争证据仍独立保留；本轮本地多API检查不能冒充云端多副本实测，完整BA-11不勾选。
