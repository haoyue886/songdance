# 38.1 认证与任务归属本地交付

日期：2026-09-30。基线 `f3fb52a`。范围为本地认证代码、任务访问隔离、迁移与 UI；不是生产认证/收费上线。

## 实现

- 固定 `@supabase/ssr 0.12.7` / `@supabase/supabase-js 2.117.2`、`PyJWT 2.15.1` / `cryptography 50.0.1`；依赖已安装并写入锁文件。
- Next.js 的 Google/OTP、回调、access-token 和退出接口：固定 Origin、站内回跳白名单、HttpOnly Cookie、no-store、PKCE、OTP 挑战与错误恢复。仅内存提供短期 access JWT；不向浏览器返回 refresh token。
- 刷新委托固定 FastAPI server-only bridge，用 Redis 锁和 10 秒加密结果缓存跨实例协调。OTP 按邮箱摘要、IP/全局预算限制；账户相关供应商拒绝使用不承诺实际送达的统一提示。
- FastAPI 验 JWT 固定 issuer/audience/算法、UUID sub/session_id，再检查供应商 session 行、邮箱确认/封禁/删除及本地 active；验证失败不会匿名降级。
- 迁移 006 增加 users/auth_identities 和 nullable owner/guest 摘要。保护查询、下载票据、重试、删除、事件；新游客仅创建时收到独立凭证，认领原子写 owner 并保留 expires_at。旧无独立凭证任务可读但不可裸 ID 认领；受保护任务存在时拒绝 schema 降级。
- 八种语言消息结构齐全；英语/中文认证文案独立提供，其余六语沿用显式英语基线。新增 login/account 为 noindex，不进入 sitemap；375px 下复用 compact 品牌避免导航溢出。

## 验证记录

命令工作目录分别为 `songdance/api` 或 `songdance/web`。每项记录只覆盖实际执行范围。

| 检查 | 结果 |
|---|---|
| API 认证/归属、迁移、配置及原任务/下载/限流/Settings 定向集 | 最终 115 passed；专项 Ruff、编译和 pip check 通过 |
| `SONGDANCE_TEST_REAL_AUTH_SERVICES=1 .venv/bin/pytest tests/test_auth_real_services.py -q` | 3 passed；自建临时 PostgreSQL/Redis，验证真实 SQL 最小列权限/撤销、006 迁移与认领竞争、跨 coordinator 刷新锁/缓存 |
| Web lint / typecheck / `pnpm test` | 最终全部通过，164 passed |
| `pnpm build` | 默认 Turbopack 生产构建成功，61 个生成页面；不是只测 Webpack 替代命令 |
| `pnpm test:auth:ui` | 真实 SDK + 本地协议替身通过：OTP 错误/成功、Google PKCE/locale、HttpOnly、响应无 refresh token、退出和过期刷新桥接；375px/1280px 页面实看，无横向溢出 |
| 独立审查 | 游客事件缺 capability 的 P2 已修复：/events 明确传 jobId 上下文，前端实际请求与 API 正负路径均补回归；复审无遗留 P1/P2 |

浏览器使用隔离临时 Next 输出目录与新浏览器上下文，拦截非本地浏览器请求；截图留在 Web 的 `test-results/songdance-auth-ui-*`，不是用户真实账号。原真实 Google/SMTP/Supabase 未连接。

最终浏览器复跑通过，截图目录为 `test-results/songdance-auth-ui-4uZETf`，已实际查看 375px 登录截图。默认生产构建在沙箱内因 PostCSS/Turbopack 创建本地端口失败，按同一 `pnpm build` 在允许该能力的环境重跑成功，未切换构建器或放宽检查。最终独立复审覆盖 bridge secret 格式、JWT 非字符串反例、防邮箱枚举、HTTPS Secure 与 locale 修复，无遗留 P1/P2；审查者独立执行 API 48 项、Web 26 项通过，其他结果按主 Agent 实跑记录。

## 全量 API 回归与基线区分

首次 `.venv/bin/pytest -q`：**959 passed / 10 failed / 6 skipped / 3 errors**，220.16 秒。不是全量绿色。

- 其中 2 个解析失败与 3 个离线包 setup error 由沙箱阻止 Chrome 启动造成；在允许本地浏览器的环境，窄范围复跑 `test_score_validation.py::test_musicxml_loads_in_osmd_and_an_independent_xml_parser`、`test_single_staff.py::test_single_staff_loads_in_external_parsers`、`test_offline_structure_review.py`，**8 passed**（包含原已通过用例）。
- 其余 8 项位于 crossing candidate/harmonic audit、device bass、human quality、review rebuild、spectral family、structure regression/review。以 `git archive f3fb52a` 在独立临时目录提取基线 app/scripts/相关测试，仅只读复用现有 fixtures，逐项运行同一失败测试，**8 failed**，断言位置和差异一致。
- 基线复现具体包含：旧 code hash 与当前算法文件不一致、真人/结构人评指纹过期、已更新评级仍被历史测试要求 needs_redo、重建记录旧人评摘要不一致。本批未修改这些算法/评级/真值，不为通过而重写 hash 或删除失败。
- 原 6 项真实外部服务测试因未配置其各自集成环境跳过；新认证服务验证使用自建临时实例单独完成，不宣称填补了所有旧外部集成缺口。

## 未完成与接续

- 真实 Supabase 项目、Google consent/callback、SMTP 送达、供应商 session 策略及生产 HTTPS Cookie 尚未联调；BA-02/11 不能标为生产通过。
- Free 月额度、Pro 已付周期账本、Creem、账户删除先停续费等仍待 38.2–38.4；本版本账户页明示这些未启用，默认 AUTH 开关关闭。
- 未开放 5/10 分钟，未修改转谱模型或宣布音乐质量验收通过；历史 8 项失败仍保留。
- 接入用 `../auth-setup.md`，只将凭据放到未提交文件/平台环境。代码后续开发从 38.2 开始；真实认证联调可以独立补齐，不需重做已验证的本地链路。
