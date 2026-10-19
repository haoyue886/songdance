# 2026-10-19 双付费客户隔离预检与真实补验准备

本地签名JWT+一次性PostgreSQL下的两份合成客户/付费周期隔离通过，真实补验独立库已准备且停服。**真实数据目前仍只有Google的既有退款客户；邮箱身份尚无客户绑定，不能标记双付费客户真实验收通过。**未新增付款、邮件或Portal调用。

## 本地预检

新增 `api/tests/test_two_paid_customers_real_services.py`。沿用opt-in新PG、私有songdance_auth视图与受限reader，本机RS256签名JWT，仅JWKS获取替换为本机公钥，原Verifier/会话SQL/业务映射保留。两subject/session不同、email相同，两个业务user各有独立合成BillingAccount、PaidPeriod、UsagePeriod，已用量分别15/60秒。

- 两账户的账单summary均为本人owner、pro、各自已用/剩余额度，不能按同邮箱合并。
- 带另一user_id/customer_id的GET query不改变本人summary；Portal空body即使附带另一客户query，离线provider也仅收到当前认证用户的持久customer_id，返回可区分的本人假Portal URL。
- Portal/checkout body注入另一user_id或customer_id均422，错误响应private/no-store；没有额外Portal或checkout provider调用。
- 两客户合法Portal各调用一次离线provider；前后BillingAccount/PaidPeriod/UsagePeriod关键快照一致，没有创建支付或改变用量。

这是明确合成付费记录，不声称真实Test付款或商户客户证据。未修改生产代码。

## 真实补验数据准备

本机准备脚本 `/tmp/notavue-prepare-two-paid-20261019.py` 已成功执行，源码保存在私密 `.data/notavue-two-paid-20261019/tools/prepare.py`。仅临时恢复原本机隔离PG集群，读取原四库及10/19账单隔离库的全public表摘要；用后者模板创建独立 `notavue_two_paid_20261019`，复制其storage，创建独立tmp/Redis命名空间及mail SQLite副本，随后停止PG。

新库初始事实：

- 两份既有active业务身份，来源为先前已核对的精确issuer+subject；无删除申请。
- 仅Google具有原客户绑定及revoked/used30历史；邮箱无绑定，未伪造新客户或付款。
- 新库初始摘要与来源相同，准备前后五份来源数据库摘要完全一致，来源mail文件摘要不变。
- `.env.two-paid-test.local` / `.env.two-paid-mail-test.local` 为0600、Git忽略，全部落盘feature flags=false；mail仍限定hello@notavue.io。未输出密钥、JWT或客户链接。
- 所有服务停止；新库/文件保留。未启用Hook、Tunnel、Web/API、Redis或进行供应商调用；新OTP/交易授权计数均0。

证据为私密data目录的 `source-digests.json`、`preparation.json`、`fixture-manifest.json` 和 `resources.json`；这些文件不提交Git。

## 检查

API目录：

```sh
.venv/bin/ruff check tests/test_two_paid_customers_real_services.py
.venv/bin/python -m compileall -q tests/test_two_paid_customers_real_services.py
SONGDANCE_TEST_REAL_AUTH_SERVICES=1 .venv/bin/pytest tests/test_two_paid_customers_real_services.py -q --tb=short
.venv/bin/pytest tests/test_creem_billing.py tests/test_billing_ui_contract.py tests/test_entitlements.py -q --tb=short
```

新增PG **1 passed，1.91秒**；相关回归 **57 passed，15.54秒**；Ruff/编译通过。PG两条、普通回归五条既有依赖弃用警告。准备脚本编译及真实本机副本创建/摘要/停服通过，配置权限/flags/无postmaster检查通过。没有真实供应商、浏览器或付款验收。

fresh独立code-reviewer检查新增测试、准备脚本及原路由，未发现可行动问题；独立PG **1 passed**、Ruff通过。首次沙箱回环绑定被拒，正常提权后通过。审查者只读确认私密权限/flags/停服与授权计数，未重新执行prepare或重算历史五库摘要。测试snapshot仅三张表的选定关键字段，不冒称全部财务表逐字段不变；真实浏览器/供应商/双付费客户未覆盖。

## 后续真实补验范围（尚未获新交易授权）

复用原Test产品及凭据，不新增权限或改生产；在Google既有退款客户和邮箱新客户两份不同customer绑定下，以原BFF真实会话分别验证本人summary、另一客户query不切owner、body注入拒绝、本人Portal。需要先为邮箱身份完成最多一笔新的Test月付，商品USD9.90，含测试税总额以现场收银台为准并再次确认条款；不使用旧两笔已耗尽授权。

建议限定本批为：最多一次新checkout/一笔模拟付款（含税上限USD12）、最多一封hello@验证码、每客户最多一次Portal。必要时只临时启用两条签名邮件HTTPS回调，保持2/h；Creem webhook保持关闭，用原后台权威GET对账，不新增Creem公网入口。发送和checkout结果未知时不自动重复，真实最终付款/条款按浏览器规则现场确认。

验收后对本轮新交易做全额Test退款并核实停止未来续费，保留原Google与所有历史账本；结束退出会话、禁用邮件Hook、关临时入口/服务。此批不删除真实Google/Supabase身份、不进行不可恢复的业务账户删除；active删除停费属于后续独立验收。真实补验开始前需取得上述新增发送、付款和Portal授权。

BA-11仍未整体勾选，测试准备不能替代两个不同真实付款客户的证据；两个同时active订阅、真实Supabase同邮箱注册策略、云端多副本和其余BA/LA门槛仍需分别核验。
