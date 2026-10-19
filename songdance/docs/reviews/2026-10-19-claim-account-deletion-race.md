# 2026-10-19 认领与账户删除竞争本地集成验收

两个独立app/数据库连接池连接同一一次性PostgreSQL，认领先行与删除先行两种顺序均通过。删除申请提交后两个app均拒绝继续认领；先完成认领的任务被后续Worker清理，未认领游客任务和其他账户任务保留。**这是本地签名JWT与真实PG集成，不是删除真实账户、停止真实扣款或多进程部署验收。**生产代码未改，BA-11/13不整体勾选。

## 需求与新增范围

依据根目录 `Billing-Auth-Spec.md` AUTH-02/03：capability认领原子写owner；删除申请后暂停认领，保留必要身份墓碑，完成后本人仅查询删除进度。既有 `test_account_deletion_real_services.py` 已覆盖删除先持用户锁、claim等待后拒绝，但未完整验证反向顺序与认领任务被清理。

新增 `api/tests/test_claim_account_deletion_real_services.py`。测试只新建可丢弃PG与合成auth用户/会话、业务用户和静音任务；无真实凭据或既有验收库读取。两份原FastAPI app分别创建自己的engine/连接池；请求经TestClient同进程执行，不冒称本轮跨进程HTTP。

本机RSA签名JWT保留原SupabaseVerifier的签名/issuer/audience/expiry、私有songdance_auth视图会话状态及 `reauthenticated_at` 原SQL；仅JWKS公钥获取替换为本机公钥。账号删除开关、usage及可靠队列按Settings验证启用；没有账单绑定，Worker以provider=None执行，不能冒充付费取消。

## 两种竞争顺序

在第一个app的用户 `FOR NO KEY UPDATE` 已成功执行后暂停，在第二app执行同一用户锁前记录另一backend PID。父测试调用 `pg_blocking_pids`，必须实际观察到第二连接被第一连接阻塞，且两请求均未完成后才释放第一锁；等待有界，不只以线程启动顺序冒充数据库竞争。

| 首先持锁 | 第一个请求 | 第二个请求 | 提交后任务 |
| --- | --- | --- | --- |
| claim | 200 | DELETE /me 202 | owner为该用户，旧guest hash清空 |
| DELETE /me | 202 | claim 409 ACCOUNT_DELETION_PENDING | owner仍NULL、guest hash保持 |

删除pending时用户仍active、phase=billing，源文件保持。两个app的后续claim均409，包含原owner重放也不绕过删除门禁。

## 清理、隔离与墓碑

- 原Worker第一批核验无账单义务后持久写active=false、phase=cleanup、attempt1，任务和源文件仍保留，不提前清理。
- 第二批完成清理、attempt2、completed_at非空，用户邮箱清空且inactive；AuthIdentity仍映射原user_id。
- 认领先行时，新归属任务及源文件被删除；删除先行时，该未归属游客任务与capability、源文件保留，匿名正确cap仍200。
- 另一合成用户的任务owner/status和源文件字节均完整，两app均正常读取200。
- 两app凭原有效subject读取/me仍返回同一墓碑ID和completed状态，claim403；再跑Worker handled0，不重复处理。

## 验证结果

API目录执行：

```sh
.venv/bin/ruff check tests/test_claim_account_deletion_real_services.py
.venv/bin/python -m compileall -q tests/test_claim_account_deletion_real_services.py
SONGDANCE_TEST_REAL_AUTH_SERVICES=1 .venv/bin/pytest tests/test_claim_account_deletion_real_services.py -q --tb=short
SONGDANCE_TEST_REAL_AUTH_SERVICES=1 .venv/bin/pytest tests/test_account_deletion_real_services.py tests/test_claim_account_deletion_real_services.py -q --tb=short
.venv/bin/pytest tests/test_account_deletion.py tests/test_auth_ownership.py -q --tb=short
```

新增两顺序 **2 passed，2.51秒**；与既有删除PG竞争组合 **16 passed，12.60秒**（包含新增2项，不相加冒称18）；普通删除/权限回归 **67 passed，10.00秒**。Ruff和Python编译通过，两条既有依赖弃用警告。初版两处行长静态问题已修正，未改业务实现或放宽断言。git diff空白检查通过。

SQL事件监听在finally移除，release事件在失败时也释放，并发请求各有超时；两个业务/认证engine释放，新PG由fixture带check=True的pg_ctl stop清理，测试退出0。无浏览器、邮件、公开入口、付款、系统代理修改、真实账户删除或长期服务启动。未提交/推送/部署。

fresh独立code-reviewer核对新增测试及原claim/delete/用户锁/认证调用路径，未发现可行动问题；独立执行新增测试 **2 passed，2.51秒**。首次沙箱bind回环地址被拒，随后正常提权审批通过；两条既有依赖警告，未修改仓库或操作供应商。独立确认pg_blocking_pids证明跨backend实际等待、两种顺序及清理/墓碑/其他账户/未认领guest断言有效；本次同进程双app、不冒称多进程删除竞争。

## 仍未覆盖

没有验证真实Supabase最近登录、BFF/浏览器、真实active订阅停费、多进程或多主机的删除竞争、S3对象存储及历史已付用量墓碑。此场景使用无账单合成任务，无usage reservation，因此不能证明付费消费/退款或防赠送额度重领；这些门槛保留。此前多进程claim/claim与真实双浏览器claim/claim记录独立有效，不扩写成本轮claim/delete真实供应商结论。
