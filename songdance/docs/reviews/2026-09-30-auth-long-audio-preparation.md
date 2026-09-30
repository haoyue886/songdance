# 认证与长音频实施准备

日期：2026-09-30。基线提交 `13044f8`（已确认需求）；本记录对应其后的准备工具与 ADR，不代表登录/付费/长音频已上线。

## 38.0 产出

- 采用 Supabase Auth；接口、凭证归属、服务端刷新、短期访问 JWT、session_id 撤销检查、Google/SMTP 配置见 `../adr/0001-supabase-auth.md`。
- `../../infra/env.auth.example` 只有空值和说明，不写入真实凭据，也未接入当前生产配置。
- `api/scripts/check_auth_config.py` 显式读取指定模板，不加载进程环境或默认 `.env`；检查 URL、publishable key 类型、会话连接 TLS/常见管理员误用及公开变量中的服务器凭据，只报告字段和代码。通过仅证明格式，不证明角色实际最小权限、项目存在或 SMTP/OAuth 工作。

## 39.0 实际探测

执行 `python -m scripts.probe_long_audio_limits`，在自动清理的临时目录生成当前前端编码形式的静音 WAV，再调用真实 ffprobe 和生产选区验证函数；生产配置、用户音频和固定集未改。

| 秒数 | 实际 WAV 字节 | 25 MiB 文件上限 | 文件本身是否低于 26 MiB 请求体默认值 | 生产选区校验 | 声明的 90 秒分析窗覆盖 |
|---|---:|---|---|---|---|
| 30 | 2,646,044 | 通过 | 是 | 通过 | 是 |
| 90 | 7,938,044 | 通过 | 是 | 通过 | 是 |
| 180 | 15,876,044 | 通过 | 是 | INVALID_CLIP | 否 |
| 300 | 26,460,044 | 超限 | 是 | INVALID_CLIP | 否 |
| 600 | 52,920,044 | 超限 | 否 | INVALID_CLIP | 否 |

请求体列只比较文件下界，未计 multipart 封装，更未发真实浏览器请求。分析窗列读取源代码默认值，未运行音乐分析。JSON 输出含全部相关源码 SHA-256 以便复查；`production_ready`、浏览器、模型和人评标志均为 false。

本机登记的 human-provenance 是 30 秒固定片段，另抽查 Petzold 候选 source.wav 为 42 秒；本批没有把这些片段循环拼接冒充代表性长曲，没有完整调查仓库外素材，也未下载新样本。LA-01 要求的 3/5/10 分钟多首真实录音和参考证据仍待建立。

## 已执行检查

在 `songdance/api/`：

```sh
.venv/bin/ruff check scripts/check_auth_config.py scripts/probe_long_audio_limits.py tests/test_auth_config_preflight.py tests/test_long_audio_probe.py
.venv/bin/pytest tests/test_auth_config_preflight.py tests/test_long_audio_probe.py tests/test_deployment_contract.py -q
.venv/bin/python -m scripts.check_auth_config --env-file ../infra/env.auth.example
.venv/bin/python -m scripts.probe_long_audio_limits
```

- Ruff/编译通过；pytest **38 passed**，无跳过。出现环境中 FastAPI/Starlette TestClient 的 httpx 弃用告警，未因此改动依赖。
- 空认证模板预期退出 **2**，只报告 5 个缺失字段，未打印密钥；测试验证错误类型、凭据不回显、模板不受进程环境污染。
- 长音频探测退出 **0** 表示测量完成，结果如上，绝不等于长音频准入通过。没有推理时延、峰值推理内存、成本或人工评级结果。
- 独立 code-review 发现 DSN 查询参数可覆盖 authority 用户而绕过常见管理员检查；已限制解码后的查询参数白名单、单值和非空值，并增加 8 项覆盖回归。独立复审重跑 38 项测试及 Ruff 通过，原 P2 关闭，无遗留 P1/P2；此结论限于准备脚本/合同，不代表运行时认证通过。

## 下一步与未验证项

- 38.1：安装并锁定兼容 SDK/JWT 依赖，实现 Google/OTP、BFF、供应商会话最小权限查询、用户/任务归属迁移及失败路径；真实项目 URL/key、Google/SMTP 和环境配置尚未提供/核验。
- 39.0：建立授权真实长曲和参考证据、选定目标运行规格，完成探索实测后冻结正式验收阈值。当前 3/5/10 分钟代码限制未放开。
- 未运行产品 Web/API 全量回归、支付 sandbox 交易、真实浏览器登录、模型质量复评或部署；既有部署/质量门禁不因此关闭。
