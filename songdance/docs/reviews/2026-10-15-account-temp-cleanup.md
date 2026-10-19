# 2026-10-15 账户删除临时目录整链补验

已补充可复跑的本地整链用例：生产转谱入口留下临时文件后，通过 FastAPI 删除申请及原删除 Worker 完成清理；同时覆盖真实文件删除失败后的持久重试。没有修改生产清理逻辑、扩大删除范围或操作既有验收账户。

## 测试范围

- 新增 `api/tests/test_account_deletion_temp_cleanup_real_services.py`，沿用一次性 PostgreSQL 集群及迁移后的独立数据库；每个用例使用独立存储和临时目录，不连接前三份业务验收库。
- 两个离线测试身份分别经真实 `/jobs` 上传合成 WAV。各自在独立进程中调用生产 `run_transcription_job`：实际创建 `TemporaryDirectory`、下载源文件、运行 FFmpeg 并写入 running/transcribing 状态。在模型推理调用处注入 `os._exit(73)`，跳过上下文清理，留下真实 `pipeline-{job_id前8位}-{随机后缀}` 目录及 source.wav、normalized.wav。
- 这是转谱进程中断的故障注入，不执行模型推理，不据此评价转谱听感或谱面质量。认证 verifier 和供应商客户端沿用离线替身，不声称重跑 Google/Supabase 或 Creem 联调。
- 子进程移除继承的 `SONGDANCE_` 环境变量，在测试临时目录运行，并显式指向本用例数据库/存储；不读取仓库 `.env`，不注入供应商凭据。删除 CLI 的新准入开关保持默认关闭，验证已接受申请仍能继续处理。

## 实际链路与断言

1. 通过真实 FastAPI `DELETE /me` 提交申请，返回202。第一次 `python -m app.jobs.account_deletion --once` 提交 billing→cleanup 检查点；账户 inactive，但邮箱、任务、源文件和转谱临时目录仍在。
2. 成功分支第二次原 CLI 批次完成清理，status=completed、attempts=2；目标任务、源文件及转谱临时目录均删除，邮箱清空，身份墓碑及 reservation/release 账本保留。
3. 失败分支仅在目标目录的底层 `shutil.rmtree` 注入一次 OSError，原 `cleanup_job_temp_files` 和删除状态机照常执行。结果为 retry/cleanup/DELETION_CLEANUP_RETRY，任务保留 failed/DELETE_FAILED，邮箱未清空、completed_at 为空，源对象已删除但临时目录仍在。
4. 随即执行原 CLI 得到 handled=0，不提前跳过退避。移除故障后使用状态机支持的测试时钟推进到 next_attempt_at 之后，再处理一次；完成于attempts=3，预占已释放且不重复记账。
5. 两分支都比较另一账户临时目录的完整文件内容，确认其源对象、running任务、active账户及 reserved=1 均保留；无关普通文件保留。目标账户 reserved=0/consumed=0，必要身份记录保留；`/me`可读完成状态，`/billing/me`拒绝访问，重复处理handled=0，无订阅取消调用。

## 验证

在 `songdance/api` 执行：

```sh
.venv/bin/ruff check tests/test_account_deletion_temp_cleanup_real_services.py
.venv/bin/python -m compileall -q tests/test_account_deletion_temp_cleanup_real_services.py
SONGDANCE_TEST_REAL_AUTH_SERVICES=1 .venv/bin/pytest tests/test_account_deletion_temp_cleanup_real_services.py -q --tb=short
SONGDANCE_TEST_REAL_AUTH_SERVICES=1 .venv/bin/pytest tests/test_account_deletion.py tests/test_account_deletion_real_services.py tests/test_lifecycle_attempt_cleanup.py -q --tb=short
```

新增2项首次有效运行通过（14.86秒）；随后按Settings大小写不敏感规则加固子进程环境过滤，最终复跑2项通过（16.47秒），Ruff/compile也通过。两条既有依赖弃用警告。首次在默认沙箱运行时，随机回环端口 bind 被环境拒绝，2项在fixture初始化时报错、未进入测试；获得执行环境权限后重跑通过，不计作产品缺陷或跳过项。Ruff先修正新增文件的导入格式，再检查通过。

相关账户删除、PostgreSQL并发与历史产物清理回归70项通过（20.68秒），两条同样的依赖警告；与上述新增2项为不同用例。

## 独立审查

fresh `code-reviewer` 对最终测试、生产调用路径和交付记录审查后，结论为“在本次账户删除临时目录补验范围内，未发现可行动问题”。核对AUTH-03、BA-12/13相关要求，确认故障注入在真实临时目录创建及FFmpeg之后，失败恢复与隔离断言没有扩大为供应商验收。

审查者独立执行新增2项通过（16.26秒），另执行 `tests/test_account_deletion.py tests/test_lifecycle_attempt_cleanup.py` 56项通过（9.07秒），Ruff `--no-cache`通过；pytest禁用缓存、指定 `/private/tmp` 临时根并设置 `PYTHONDONTWRITEBYTECODE=1`。新增用例同样先遇沙箱bind限制，再在获得执行权限后通过。审查者未修改仓库，没有亲自验证浏览器、真实身份/计费供应商或模型质量。上述独立用例与主Agent验证重叠，不另作新增覆盖计数。

## 收尾

- 一次性PostgreSQL已由fixture关闭，专门进程查询未发现 `auth-postgres*/cluster` 残留；默认沙箱不能读取进程列表，随后只读提权确认。两类子进程均按预期退出，未留下模型/删除循环服务。
- 原测试资源清单仍为 `stopped=true`；3002/8002/8025/8027/58776/58777均无监听。本轮没有启动原集群，也没有操作三份既有数据库、真实业务账户、私密配置或供应商开关。
- `git diff --check`通过，新增测试/报告无尾随空白且保留末尾换行；本报告、删除验收和商业准备3份文档中的21个本地链接均存在。

## 验收边界与下一步

本轮补齐的是生产临时目录创建→进程中断→删除申请→原Worker清理/失败恢复的本地整链。此前浏览器用例的错误命名夹具仍按原报告保留为无效覆盖；本轮没有新建真实登录账户或再次提交浏览器删除。

本轮之后，已在原账本独立副本中完成两份已退款/canceled订阅均绑定的限定删除及真实Google重新登录墓碑，历史重叠投影冲突保留，见 [付费副本验收](2026-10-15-paid-account-deletion.md)。正常完整付费账本、active订阅删除时停止续费、两个真实身份互访和供应商竞态仍待验收，BA-11/13不整体勾选。两次原授权模拟付款已用完，本轮未新增付款、公开入口、凭据或外部配置变更。测试修改尚未提交、推送或部署。
