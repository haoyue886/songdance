# 2026-10-20 完整两期付费账本的删除失败恢复（本地PostgreSQL）

本地新增两种指定场景通过：一个账户有两期相邻、完整且不重叠的已付账本，另一付费客户同时持有任务和独立账本；取消停费前失败或取消成功但响应丢失时，都保留待删账户/文件，恢复后先核实停止续费、持久停用检查点，再清理任务。历史用量与付款、身份墓碑保留，另一客户记录/源文件不变。

本批只新增测试，不改生产逻辑。真实身份与支付均为离线替身，一次性PostgreSQL及临时存储不连接任何既有验收库。本地结果不替代真实Creem停费/退款或真实Supabase重登录，也不签收完整BA-13。本轮真实USD11.78退款仍因Test余额不足受阻，已取消新订阅的证据与账本保留在[真实双客户记录](2026-10-20-distinct-payment-email-preparation.md)。

## 数据与验收路径

新增 `api/tests/test_paid_account_deletion_real_services.py`，沿用原自建临时PG/迁移和FastAPI测试客户端。原`create_checkout`、签名事件inbox、支付投影及退款/删除服务保持，provider和身份用显式离线对象。首张合成发票结束于昨天、续期从该终点开始，两个PaidPeriod均由原支付投影建立，避免旧真实副本的重叠历史冲突。

历史成功任务是显式数据库夹具，使用原reserve_period/settle_job留下30秒consume账本，不声称历史HTTP提交或模型推理。当前周期待处理任务及另一付费客户任务走原multipart `/jobs`，分别预占15秒并生成可读源文件；pipeline目录为明确合成临时文件，不冒充真实FFmpeg中断目录或音乐验收。

两场景分别验证：

- **取消前失败**：provider抛出故障，删除单保留billing/retry、用户仍active且邮箱保留、历史/当前任务及源文件仍在，后续新任务409；恢复后实际取消一次，并经GET核实，再进入cleanup。
- **成功响应丢失**：离线provider已取消却抛超时，第一次同样留billing/retry；恢复通过GET发现已停，无第二次取消，继续持久检查点及清理。

两者均先在第一成功批次停用用户且保留文件，第二成功批次才清理；随后重复Worker handled=0。最终当前预占归原周期release一次，旧期30秒consume不变；两张PaidPeriod保持active（取消不等于退款），checkout、客户绑定、付款行、身份映射及退款取消记录前后精确快照一致，没有凭空创建退款补偿。

同subject换邮箱后经原业务映射返回同一已删除账户、邮箱仍None、再次建任务403，用户/身份数不增加且没有新Free周期。真实JWT验签及供应商身份变更不在本测试内。另一付费客户的User、Identity、客户、checkout、订阅、付费周期、用量周期/账本、退款取消记录和任务行全字段快照均不变，源文件字节相同，其订阅取消方法若被调用会直接使测试失败。

## 命令、结果与审查

在api目录执行：

```sh
SONGDANCE_TEST_REAL_AUTH_SERVICES=1 .venv/bin/python -m pytest -q tests/test_paid_account_deletion_real_services.py --tb=short
SONGDANCE_TEST_REAL_AUTH_SERVICES=1 .venv/bin/python -m pytest -q tests/test_paid_account_deletion_real_services.py tests/test_account_deletion_real_services.py tests/test_billing_recovery_real_services.py --tb=short
.venv/bin/python -m pytest -q tests/test_account_deletion.py tests/test_billing_customer_conflict.py --tb=short
.venv/bin/ruff check tests/test_paid_account_deletion_real_services.py
```

新测试最初因误用不存在的LocalObjectStorage.read_bytes而2失败，改为本地路径读取，并按mapper属性快照处理映射字段后2通过；这是测试代码问题，未发现或修复生产缺陷。PG组合 **20 passed**；相关普通回归 **64 passed、1 skipped**，跳过为该普通命令未启用的客户绑定PG竞争项，其路径已在上一批验证。最后新增另一客户任务全字段快照后，仅重跑受影响两项，最终 **2 passed**；Ruff及diff检查通过。两条既有Starlette/httpx和pkg_resources弃用警告保留，不通过改依赖消除。

fresh独立code-reviewer检查新测试及原删除服务，发现的另一客户任务记录未入快照盲区已补齐，最终复审无可行动问题。独立最终版一次性PG **2 passed**、Ruff通过；审查者未修改文件或访问现存库/供应商。测试fixture在finally销毁各自数据库并停止临时PG，未启动项目Web、邮件Hook、Tunnel或原商业测试集群。

## 后续边界

完整两期账本的指定失败恢复在本地得到证据，真实active停费删除、第三方身份重新登录、云端多实例/完整BA-13仍待验。真实Creem退款不因离线测试通过而解除：用户已反馈有支持答复，正文尚待提供；不自动恢复旧服务、发送验证码、新建付款或修改已保存真实账本。
