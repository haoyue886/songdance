# 2026-10-15 账户删除补充验收

**本轮指定范围已完成：真实 Google 登录下的无账单隔离账户申请删除、分阶段停用/清理、重新登录墓碑验证；另已验证真实 Creem 枚举和未知订阅保护。** 115项定向、14项隔离并发测试通过，独立审查无可行动问题。测试服务已关闭；付费账户删除整链、真实双用户权限矩阵等仍待补，不整体签收 BA-11/13。

## 范围与授权

- 使用新建数据库 `notavue_account_deletion_20261015`、独立私有存储/Redis 命名空间。复用已有 Google/Supabase 测试配置，采用真实 JWT 验签和原最小权限 session reader 校验会话创建时间；未替换认证 verifier。
- 用户在已准备的删除确认页明确授权“仅删除本轮专用测试账户”。本轮仅停用该库业务账户，未删除 Google/Supabase 身份，未触碰前两份付款/退款账本。没有创建新付款、密钥、公开入口或外部订阅。
- `SONGDANCE_ACCOUNT_DELETION_ENABLED` 仅在本轮 API/Worker 进程中 true；私密配置默认仍 false。此账户没有业务账单，CREEM/付费用量关闭，清理成功不冒充付费用户完整停费删除验收。
- 为测试清理，在真实登录生成的业务账户下显式准备一笔合成成功任务、2秒合成 WAV、合成 MIDI、未登记的历史 attempt 产物及1次已消费用量。它们是数据库/存储夹具，不是真实模型转谱结果。

## 真实供应商枚举与未知绑定保护

现有 Test 客户的 `GET /customers/{id}/subscriptions` 返回2份 Test/canceled订阅，分页 total_records=2、total_pages=1、current_page=1。枚举合同与当前客户端兼容。

在原账本事务中使用仅允许 GET 的实际 Creem 客户端调用 `verify_stopped_billing`：该客户有一份本地未绑定订阅，预检返回 `DELETION_UNBOUND_SUBSCRIPTION`。仅1次GET、0次外部修改；诊断行没有加入数据库，事务回滚。原用户 active、任务和付款记录保持不变，持久删除申请数仍0。此项证明失败路径先转审查，不证明未知订阅能自动正确归属。

## 真实登录与分阶段清理

1. 正常 Chrome 经现有 Google/Supabase PKCE 登录 `/zh/account`。页面显示专用库业务账户与默认关闭的付款入口；本轮删除申请由浏览器真正的 `DELETE /me` 发起，返回后持久状态 pending/billing、attempts=0，用户仍 active、任务仍1个。
2. 第一批原 `app.jobs.account_deletion --once` 完成无账单义务检查并提交 cleanup 检查点：用户 inactive，但邮箱、任务、源文件、registered MIDI及历史 attempt-2/score.musicxml 均仍在，消费仍1，identity=1。
3. 第二批 Worker 完成清理：status=completed、phase=cleanup、attempts=2，用户 inactive、邮箱清空、jobs=0；源文件及两份产物均不存在。用户行/identity各1，usage.consumed=1、reserved=0，reservation/consume账本两行保留。
4. 实际页面通过独立状态刷新显示“Notavue账户已停用”“账户删除已完成”，邮箱不再显示，任务入口隐藏。随后退出并实际通过 Google 再次登录；正常回到 `/zh/account` 后仍停用/删除完成，没有新的 Free 余额或任务入口。已查看真实渲染截图。此项也证明 Google/Supabase 身份没有被业务删除物理移除。
5. 以同一已保存 issuer/subject 分别传入原/变更邮箱调用身份查找，普通业务访问均403；允许本人读取删除进度，用户总数仍1，未创建新账户或额度。此处邮箱变更是本地身份函数输入诊断，未修改真实Google邮箱。
6. 再次只读核对前两份账本：两者用户仍active，权益仍revoked；原已用30秒、第二份已用0秒，未被本轮删除影响。

## 临时目录夹具限制

初始临时夹具错误放在 `temp/{job_id}/input.wav`，不符合生产 `pipeline-{job_id前8位}-{后缀}` 的命名规则，因此清理完成后该合成目录仍在。这是夹具覆盖无效，未确认生产缺陷，未扩大产品清理范围。

另外按真实命名创建匹配目录并单独调用 `cleanup_job_temp_files`：deleted=1、failed=0，匹配目录删除、无关任务目录保留。两个明确的合成夹具目录随后由验收脚本清理。**真实命名的临时目录只完成组件检查，不能计为本次浏览器整链覆盖。** 初始与补验观察均保留在私密测试目录报告中。未登记产物夹具在 Worker 运行前已校正为实际流水线可生成的 attempt-2/score.musicxml，并设置 attempt_count=2；未用任意未知文件名制造清理结论。

后续已新增本地整链回归：实际调用生产转谱入口并运行FFmpeg，在模型推理前异常退出，留下由生产流程创建的临时目录，再通过FastAPI申请和原删除Worker验证清理、底层删除失败/退避/恢复，以及另一账户目录内容保留。新增2项及相关70项通过，fresh专项独立审查未发现可行动问题；认证与供应商仍为离线替身，本轮未重新提交真实浏览器删除。它补齐本地生产目录整链，不改写前次浏览器夹具的覆盖限制，详见 [临时目录补验](2026-10-15-account-temp-cleanup.md)。

## 实际检查

在 `songdance/api` 执行：

```sh
.venv/bin/pytest tests/test_auth_ownership.py tests/test_account_deletion.py tests/test_account_deletion_client.py tests/test_account_deletion_migrations.py tests/test_billing_ui_contract.py -q --tb=short
SONGDANCE_TEST_REAL_AUTH_SERVICES=1 .venv/bin/pytest tests/test_account_deletion_real_services.py -q --tb=short
```

结果115项定向、14项临时PostgreSQL测试通过，两条既有依赖弃用警告。覆盖不同测试身份的任务/账单边界、匿名认领、签名/撤销、确认/Origin/最近登录、删除/准入/Worker并发与清理失败恢复；供应商协议在这些自动用例中是本地替身，不能据此宣称两个真实供应商账户权限矩阵通过。

本轮未新增生产逻辑、未重新运行无关全量Web构建。真实供应商枚举、原账本保护、浏览器删除与数据清理证据和自动测试分开记录。

## 独立审查

fresh `code-reviewer` 在本次范围内未发现可行动问题，独立运行删除、客户端与历史产物清理回归80项通过。核对保存快照与脚本，但三库只读连接失败，没有独立确认当前数据库状态，也未亲自执行真实Google/Creem/UI或PostgreSQL并发；主Agent的实际运行证据不移作审查者实测。原文见 [独立审查记录](2026-10-15-account-deletion-review.md)。不同测试范围重叠，不合并计数。

临时验收入口：`/tmp/notavue-account-deletion-guard-20261015.py`、`/tmp/notavue-account-delete-seed-20261015.py`、`/tmp/notavue-account-deletion-snapshot.py`、`/tmp/notavue-account-deletion-final-check.py`。脱敏结果保存在受忽略的 `.data/notavue-account-deletion-20261015`，私密配置不提交。

## 环境收尾

- 最后一次真实Google会话已退出，浏览器回到 `/zh/login`。3002 Web、8002 API已停止，原独立PostgreSQL/Redis按清单PID和Redis run_id核对后关闭，三份测试数据库与审计保留；原两份账本用户仍active、权益revoked、已用30/0不变。
- 未运行新的RQ/Dispatch/Billing循环，也未开放Tunnel或启用邮件/计费webhook。删除仅由两个显式 `--once` 批次完成，没有遗留自动清理进程。
- 三份私密配置均保持0600、Git ignored、全部默认功能开关false。复用的Google与Supabase身份保留，专用验收库的业务身份墓碑维持停用；不因下次验收直接回填active或清空历史。
- 最终 `git diff --check` 通过，6份相关文档27个本地链接均存在，改动文件未命中三份实际配置中的key/secret/DSN/bridge值。`lsof`检查3002/8002/8025/8027/58776/58777无监听，资源清单stopped=true。Web `pnpm exec next typegen`（AUTH关闭）退出0、生成引用恢复默认；浏览器自动化会话已reset。
- 本轮与前批代码/文档改动尚未提交、推送或部署。

## 尚未覆盖

两个真实供应商身份互访、active订阅删除时自动停费、无历史投影冲突的完整付费账本删除、真实供应商故障/并发订阅变化、生产保留/匿名化政策仍待补。后续已用原账本独立副本完成两份已退款/canceled订阅均绑定的限定删除分支及真实Google重登录墓碑，历史重叠投影冲突未清除，见 [付费副本验收](2026-10-15-paid-account-deletion.md)。生产临时目录的本地整链已由专项补验覆盖，原真实浏览器夹具限制保留。既有取消/退款实测不能替代未验删除分支；BA-11/13不整体勾选。Google品牌、完整MAIL/BA、法律、容量和专业音乐质量/长音频发布门槛保留。
