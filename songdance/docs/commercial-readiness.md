# 商业化 Test 配置与验收准备

2026-10-07：认证、Free/Pro 账本、可靠派发、游客体验、Creem Test 和账户删除已有本地实现，开关默认关闭。本清单用于准备隔离测试项目，不创建供应商账户、不部署、不打开正式收费，也不证明真实 Google、SMTP 或商户已经可用。

详细接入沿用 [认证设置](auth-setup.md)、[Creem Test 设置](creem-test-setup.md)、[部署说明](deployment.md) 和 [恢复手册](runbook.md)。范围与验收以 [开发计划 Phase 38/39](../../DEV-PLAN.md) 和 [商业化子规范](../../Billing-Auth-Spec.md) 为准。

## 1. 先完成本地验证

在已有锁定依赖的环境运行，只使用隔离数据库、存储和队列：

```sh
# songdance/api/
.venv/bin/pytest tests/test_commercial_config.py tests/test_auth_config_preflight.py tests/test_settings.py -q
.venv/bin/ruff check app/services/commercial_config.py scripts/check_commercial_config.py tests/test_commercial_config.py

# songdance/web/
pnpm test:commercial:e2e
```

浏览器走实际 Next.js BFF、FastAPI、迁移后的 PostgreSQL、Redis、RQ 和 Basic Pitch，仅外部身份与支付协议由本地服务提供。A4/静音合成音频验证代码路径、导出与失败恢复；不登录真实 Google、不发送邮件、不购买真实商品，也不能替代真实音乐固定集、专业谱面复评或供应商验收。

运行需要 Python 3.11 API 虚拟环境、锁定 Web 依赖、本机 `initdb`/`pg_ctl`/`redis-server`、FFmpeg 和 Chrome（非 macOS 可用 `PLAYWRIGHT_EXECUTABLE_PATH` 指定）。脚本选择随机端口和新临时数据库/存储/队列，测试后验证自有 API/Web/模型 Worker/PostgreSQL/Redis 退出才删目录；清理不能确认时保留临时目录和失败报告。不会借用现有 3000/3001/8000 服务。

本地最终证据见 [整链验收记录](reviews/2026-10-07-commercial-journey.md)。另有隔离的信号/强制退出恢复检查：API 目录 `SONGDANCE_TEST_REAL_AUTH_SERVICES=1 .venv/bin/pytest -q tests/test_commercial_stack_lifecycle.py`，无需真实供应商项目。

当前代码合同为 Free 每 UTC 自然月 1 次成功、单次最多 90 秒；游客最多 30 秒、签名访客一次成功体验；Pro Test 单次仍最多 90 秒。Test 价格与周期额度沿用现有 Test 快照，不能据此承诺 Live 价格或 5/10 分钟长音频。

## 2. 准备一个明确的配置文件

参考 `../.env.example`、`../infra/env.auth.example` 与 `../infra/env.creem.example` 的字段，整理为一个未提交的 `songdance/.env.commercial-test.local`。每个键只能出现一次，不直接拼接模板；保持开关关闭完成配置整理。该文件已受仓库 `.env.*` 忽略规则保护，仍须检查没有误加到暂存区。

- 使用独立测试 Supabase 项目、业务数据库/存储、Redis DB 与命名空间；不要借用线上数据。
- `SONGDANCE_ENVIRONMENT` 用 `test` 或 `development`，`SONGDANCE_BILLING_ENVIRONMENT=test`；当前 Creem 实现拒绝 production/Live。
- `NEXT_PUBLIC_SITE_URL` 与 API 的 CORS 站点一致；`NEXT_PUBLIC_API_URL` 与 `SONGDANCE_AUTH_API_URL` 指向同一 API origin。远程地址使用 HTTPS，本地开发/测试允许 localhost HTTP。
- 使用现代 `sb_publishable_` key，会话查询连接使用独立最小权限角色；管理员、service_role、`sb_secret_` 和完整数据库连接不能放入 `NEXT_PUBLIC_*`。
- 独立生成 bridge、下载和游客签名密钥；bridge 为 32–128 字符 base64url/hex，下载/游客检查采用相同安全字符范围。密钥保存到私密文件或平台密钥管理，不发送到聊天、测试报告或仓库。游客密钥必须跨副本、重启稳定，轮换按认证设置先排空在途任务。
- Creem Test key、webhook secret、Test product、plan version 必须配套。success URL 固定本站 `/billing/return`，已有 `/account` 配置也兼容；设置精确 webhook 路径并保留原始 body。

本地私密文件应只允许所有者读写：

```sh
# songdance/api/；文件需已存在，检查入口不会创建、改写或 chmod 文件
chmod 600 ../.env.commercial-test.local
.venv/bin/python -m scripts.check_commercial_config --env-file ../.env.commercial-test.local
```

检查不联网，只读取指定文件，不从进程环境、默认 `.env` 或文件密钥目录补齐漏项，不改变开关。沿用锁定解析器，重复键、非赋值行、命令/变量展开和异常编码会被拒绝；含私密配置的文件若对组/其他用户开放权限也会拒绝。报告只含字段名、错误码、布尔状态和当前短音频合同，不回显 key、密码、DSN、异常输入或供应商响应。

`configuration_format_valid` 表示文件值及 Settings 约束合格；`features` 列出对应功能的开关与前置条件。关闭且未填凭据的模板即使格式有效，`commercial_test_configuration_valid` 仍为 false，CLI 退出 2；缺少环境名称或明确非法值也会报错。当前完整 Test 组合须同时配置并显式开启 AUTH（Web/API 两处）、USAGE、PAID_USAGE、RELIABLE_QUEUE、GUEST_USAGE、CREEM 和 ACCOUNT_DELETION；符合时 CLI 退出 0。只有在隔离 Test 环境确实准备好后才改这些开关，Web 构建期 AUTH 变更需要重建。

即使退出 0，provider 连通性、数据库实际权限、SMTP/OAuth、商户商品和后台进程状态均固定为未验证，`production_ready=false`。工具不能核对分布在不同服务上的实际部署值是否相同；需另外核对所有副本的凭据、数据库、存储、队列和命名空间。

## 3. 隔离项目的实际联调顺序

1. 按认证设置配置真实 Google callback、本站 allowlist、自有 SMTP 和 600 秒 OTP；实际验证送达、过期/复用、重发预算、Cookie、撤销与最近新登录。离线 publishable key/DSN 格式不能证明项目存在或权限最小化。
2. 在隔离业务数据库执行 `alembic upgrade head`，核对存储/Redis/队列一致。准备 API/Web、转录 Worker、Dispatcher、Billing Worker、账户删除 Worker 与清理任务；派发与删除恢复命令见现有设置和恢复手册。离线检查不会启动或探测这些服务。
3. 按 Creem Test 设置创建并核对 Test 商品、签名 webhook 和 Portal。实际执行测试卡付款、重复/乱序通知、查询授权、取消、退款、历史对账与删除前完整订阅核验。价格、币种、周期/税额字段及取消后状态需要供应商证据，不以本地替身代替。
4. 启用隔离 Test 开关后重建 Web，跑游客体验、Free 成功/失败与月边界、Pro 购买/扣量/导出/取消、幂等恢复、撤销、跨用户拒绝及账户删除闭环；保留测试标识、版本与不含敏感值的结果。
5. 另行完成 BA/LA、真实音乐固定集/专业复评、容量成本、实际客服地址、法律/隐私退款条款与商户审核。当前未完成项继续保留，不把 Test 配置合格、本地 E2E 或账户删除实现当作正式发布批准。

关闭新准入开关后继续用兼容后台进程排空已接受的任务、通知与删除申请；保留账本、幂等/身份墓碑和签名密钥，不能通过删历史或降级绕开权限和恢复要求。
