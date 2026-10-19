# 账户删除补充验收独立审查

在本次范围内未发现可行动问题。此结论仅覆盖本轮验收记录、保存的脱敏证据和直接相关删除实现，不签收完整 BA-11/13。

## 范围

- `songdance/docs/reviews/2026-10-15-account-deletion-acceptance.md`（审查时为新增草稿，状态仍待真实重新登录及环境收尾）。
- 直接调用路径：`app/routes/account.py:79`、`app/services/account_deletion.py:50,87,127`、`app/services/account_deletion_billing.py:24,125`、`app/services/auth.py:80,136,201`、`app/services/lifecycle.py:43`、`app/services/temp_cleanup.py:19`、对应 Web 删除客户端及组件。
- 核对 `Billing-Auth-Spec.md:65,66,187`、2026-10-07 既有交付边界；工作区其余计费 listener / checkout 增量不纳入本轮扩展审计。

## 独立验证

在 `songdance/api` 执行：

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -q -p no:cacheprovider --basetemp=/tmp/notavue-account-review-tests tests/test_account_deletion.py tests/test_account_deletion_client.py tests/test_lifecycle_attempt_cleanup.py
```

80 passed，9.25 秒；2 条既有依赖弃用警告。测试使用隔离 SQLite、临时存储和离线供应商，不连接真实认证/计费服务。

静态追踪确认：本人身份、本站 Origin、明确确认及会话创建时间用于新申请；申请后阻止新任务/重试/购买/认领；完整核验绑定订阅及停止未来续费后才持久切换 cleanup 和停用业务账户；清理失败保存终态栅栏与释放；保留原身份/用量账本，原身份换邮箱不复活本地业务账户；已核验后续计费义务会重开停费处理。

独立核对 7 份已保存脱敏 JSON 与 4 个临时验证脚本。快照呈现第一批 cleanup 检查点时邮箱/任务/源文件和两份产物保留，第二批 completed 后邮箱、任务和已知产物清除，身份与 consumed=1 保留；未知订阅预检为 DELETION_UNBOUND_SUBSCRIPTION，GET=1、无持久删除申请。记录如实说明真实 Google、无账单本地清理、Creem 只读枚举保护、合成夹具及目录组件补验的不同覆盖范围。

独立只读配置检查确认三份账本的数据库、私有存储和临时目录各不相同；三份私密配置均 0600、被 Git 忽略，AUTH/USAGE/CREEM/ACCOUNT_DELETION 默认 false。

## 未覆盖及限制

- 对三份数据库尝试了只读事务连接，均 OperationalError；未直接复核当前数据库，数据结论依据保存快照及脚本，不把连接失败解释为数据验证成功。
- 未亲自运行真实 Google 重新登录、真实 Creem 请求、浏览器 UI 或临时 PostgreSQL 并发；验收记录中的 115/14 项执行结果为交付方证据，未计入本审查者的 80 项。
- 付费且全部订阅已绑定的供应商删除整链、active 订阅删除时自动停费、两个真实供应商身份互访、供应商故障/并发订阅变化、匹配目录命名的浏览器至 Worker 整链、生产保留/匿名化政策仍未覆盖。
- 临时目录初始夹具不符合生产命名，保存快照显示 temp_exists=true；记录已明确组件补验不能替代本次整链覆盖，没有把它判为已证明的生产缺陷。

没有修改仓库、提交、推送、调整验收标准或写入通过标记；仅生成此临时审查报告与隔离测试输出。
