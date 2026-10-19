# 2026-10-19 同邮箱身份隔离集成验收

本批补齐本地签名JWT、原认证门禁及隔离PostgreSQL之间的同邮箱身份测试。**限定本地集成检查通过，不等于真实Supabase创建同邮箱身份或真实付款验收。**未发现需要修改生产逻辑的问题，完整BA-11不勾选。

## 合同与实现

依据根目录 `Billing-Auth-Spec.md` AUTH-01/AUTH-02、BILL-01/BILL-02及BA-11：邮箱必须验证；身份唯一键为issuer+subject；禁止仅凭同邮箱字符串合并或猜测付费归属。

新增 `api/tests/test_auth_same_email_real_services.py`，复用既有opt-in一次性PG fixture，迁移全套业务表；本地auth.users/auth.sessions由私有songdance_auth视图及受限reader访问。使用本机RSA私钥签名、原SupabaseVerifier.verify与session_active；仅JWKS公钥获取替换为本机公钥，不替换验证器或会话SQL。测试供应商为既有FakeProvider，没有真实网络、邮箱、商户、凭据或历史测试集群访问。

两JWT的email字符串相同、subject/session不同。owner在auth.users中已确认；另一身份有真实本地会话行但email_confirmed_at为NULL，其签名JWT故意声称email_verified=true，用于证明该声明不能绕过数据库确认门禁。

## 验收断言

- 原owner正常建立业务身份、创建自有任务；另一匿名任务仍由独立游客capability保护。原owner有显式合成BillingAccount绑定，账单摘要显示本人owner_id及portal_available=true。
- 未确认身份携同邮箱、有效签名JWT及正确游客capability，在账户、账单、两任务读取、自有文件下载、两任务认领、重试、删除、Portal、checkout共11路径均401/AUTH_REVOKED。原subject搭配另一人的有效session_id亦401。
- 拒绝前后业务User、AuthIdentity、任务owner/guest hash/status、BillingAccount归属快照完全一致。未创建该身份业务账户，原owner访问200、匿名原cap读取200；离线provider的create_checkout/create_portal调用均为空。
- 仅在一次性auth表中把第二身份改为已确认后，其/me为200，但得到另一业务user_id；同邮箱不合并。原owner任务读取/认领404，缺cap游客认领404。账单摘要owner_id为新用户、portal_available=false，Portal409/BILLING_CUSTOMER_NOT_READY，provider仍不调用。
- 原issuer+subject换JWT中的email仍映射原user_id；最后两身份分别绑定不同user，任务与账单快照保持原值。

## 已执行

API目录：

```sh
.venv/bin/ruff check tests/test_auth_same_email_real_services.py
SONGDANCE_TEST_REAL_AUTH_SERVICES=1 .venv/bin/pytest tests/test_auth_same_email_real_services.py -q --tb=short
.venv/bin/pytest tests/test_auth_ownership.py tests/test_auth_coordination.py tests/test_billing_ui_contract.py -q --tb=short
```

最终Ruff通过；新增PG集成 **1 passed，2.15秒**；相关普通回归 **31 passed，2.96秒**。两条既有依赖弃用警告。新增fixture最初Ruff报导入fixture与函数参数同名，改为从模块导出fixture后消除，未修改产品逻辑。PG fixture结束时执行带check=True的pg_ctl stop；测试退出0，无长期服务启动。git diff空白检查通过。

fresh独立code-reviewer核对新增测试、原Verifier与身份/任务/账单调用链，未发现可行动问题；独立运行新增PG集成 **1 passed**。审查者首次受沙箱回环端口限制，正常提权后通过，一次性数据库由fixture停止；未修改仓库或调用供应商。双方均明确真实注册/关联、BFF、真实JWKS获取和供应商账单未覆盖。

## 范围边界

此次以本地JWKS替身、合成auth表/用户/账单为输入，原JWT签名验证、私有视图会话SQL、API依赖和业务持久化为真实实现。没有真实供应商签发JWT、浏览器/BFF登录、付款、Portal或邮件，也未修改真实Supabase的邮箱确认状态。用量开关关闭，没有证明付费额度/赠送额度的完整隔离。

多API实例竞争、两个真实付费客户、认领/删除竞争与BA-11全部真实供应商矩阵继续待验；已通过的真实三轮双会话竞争不重复。未提交、推送或部署。
