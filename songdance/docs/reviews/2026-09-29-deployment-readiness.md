# 部署准备检查

受测提交：f838890。范围为本地准备检查，无远端写入、无部署、无模型/质量门槛变更。

- Web：`pnpm exec tsc --noEmit`、`pnpm exec next build --webpack`成功。Vercel默认`pnpm build`未在本轮验证，不能称完全同命令验证。
- API：`pytest tests/test_deployment_contract.py tests/test_human_quality_gate.py -q`：11 passed / 1 failed。失败为既有人评suite_fingerprint与当前流水线不一致，未重写指纹或继承旧评级。
- `pip check`：No broken requirements found；仅依赖一致性，不代表漏洞扫描通过。venv未安装pip-audit。
- Docker：CLI存在，但Colima socket不存在、daemon未运行；docker compose子命令不可用。容器构建、迁移/Worker/Cleanup真实启动和存储连通性未验证。
- 仓库结构：部署指南假设songdance子目录作为远端根，当前仓库根包含songdance。实际Vercel/Railway项目必须设置与其一致的根目录/配置路径，当前尚未验证平台配置。未重组仓库。
- 真人10条发布质量门槛与16条结构评审包交付是不同验收。16额外音暂缓只解除该专项交付阻塞，不表示真人质量门槛已通过。

后续限定顺序：确定部署项目根目录配置与目标环境；补容器运行验证及依赖漏洞核验；处理正式真人质量证据有效性。账户、域名、对象存储和代理CIDR等线上配置未读取或验证。当前不能宣布上线就绪。

`pnpm audit --prod --json`实际执行退出1：registry.npmjs.org DNS解析ENOTFOUND，未取得漏洞结果，不标记无漏洞。本轮未安装额外依赖。
