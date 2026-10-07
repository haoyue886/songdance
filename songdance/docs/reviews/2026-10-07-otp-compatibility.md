# Supabase 测试配置与 OTP 兼容修复

## 范围与复现

用户要求保留测试 Supabase 项目的默认 8 位 OTP，先调整应用兼容性，不将供应商降为 6 位。现有需求仍为托管邮箱一次性验证码、600 秒有效期、每挑战最多 5 次尝试，不自建密码系统。

原输入框 `maxLength=6` / 六位 pattern 与 BFF 六位正则共同阻断 8 位验证码。先添加回归、保持实现未改，运行 `pnpm exec vitest run src/lib/auth/server.test.ts`：37 passed / 2 failed；普通 8 位及前导零 8 位均返回 400，而不是成功的 200。

## 修改

- 输入框与 BFF 使用同一 OTP 格式，只接受 6 或 8 位 ASCII 数字；保留旧 6 位项目兼容，不接受 7/9 位、全角、空白、换行或非字符串，不截断前导零。
- 八语言的验证码标签不再错误限定六位；沿用现有语言回退，不扩展翻译范围。
- 8 位验证仍先调用 `otp-attempt`，供应商成功后才调用 `otp-consume`。原挑战、尝试预算、邮箱绑定、单次使用与 HttpOnly 会话逻辑未改。
- 测试供应商只接受确定的本地测试验证码；浏览器 smoke 新增 8 位失败/成功和 7 位 HTML 拒绝，保留 6 位登录及刷新路径。

## 实际验证

在 `songdance/web/` 执行：

- `pnpm exec vitest run src/lib/auth src/lib/api/jobs.test.ts`：3 个文件、54 项通过。
- `pnpm test`：前端全量 41 个文件、313 项通过。
- `pnpm exec tsc --noEmit`：退出 0。
- `pnpm exec eslint src/lib/auth/server.ts src/lib/auth/server.test.ts src/lib/auth/otp.ts src/components/auth/auth-panel.tsx`：退出 0。
- 使用 Node/JSON.parse 逐一核对 8 个语言 JSON：解析有效，验证码标签不再限定六位。
- `pnpm test:auth:ui`：首次因沙箱 `listen EPERM 127.0.0.1` 未执行流程；获得独立本地测试运行权限后重跑退出 0。
- 浏览器验证：8 位失败/成功、6 位兼容、7 位拒绝、Google PKCE/语言回跳、退出、刷新 bridge、HttpOnly Cookie、不向浏览器返回 refresh token。仅本地协议替身，未联系真实供应商。
- 查看 `songdance/web/test-results/songdance-auth-ui-cnQfAB/otp-mobile.png` 和 `otp-desktop.png`；375px 与 1280px 输入框能完整显示 8 位，无文本重叠；375px 无横向溢出的自动断言通过。
- 独立 `code-reviewer` 只读审查当前 diff、需求及调用链，未发现可行动问题；直接导入实际 OTP 模块的 194 项内存断言通过。审查者未操作用户浏览器、读取凭据或修改文件。

测试使用新临时 Next.js 构建目录、随机本地端口和独立无头浏览器，结束后退出自有服务；没有接入现有预览、数据库或供应商。截图不含真实账户、密码或验证码。

## 控制台与剩余工作

- 用户确认后保存测试 Site URL `http://127.0.0.1:3002` 和唯一精确 callback；未配置通配符、线上域名或扩展其他项目权限。
- 重新打开邮箱设置，核对持久值为 600 秒与 8 位。当前 ECC（P-256）JWT 签名仅核对，未轮换或撤销。
- 已建立 0600/Git 忽略的本地商业化配置骨架；离线检查格式有效，但凭据/数据库缺失、功能关闭，退出 2，未启用登录或收费。
- 默认邮件模板预览仍为登录链接，控制台要求自有 SMTP 才能编辑；Google provider 仍 Disabled。SMTP/OTP 模板、OAuth client、最小权限会话连接、Creem Test key/webhook 和隔离服务尚未就绪。

真实发码、送达、8 位验码、过期/复用、供应商后台撤销以及完整 BA-02 未验证；Supabase 页面参数正确或本地回归通过不能代替真实供应商验收。未部署、未开放 Live，也未宣称音乐质量或长音频通过。

后续用户选定 Resend 免费层与 Supabase Send Email Hook/API 主路径，准备记录见 [Resend 设置](../resend-setup.md)。该新增邮件运行代码尚未实现，不属于本批 OTP 兼容修复已通过的范围。
