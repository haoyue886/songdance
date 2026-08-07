# Vercel 部署指南

SongDance 使用 Vercel 托管公开的 Next.js 网站，并使用 Railway 托管有状态、长时间运行的 Python 服务。不要将转录流水线部署为 Vercel Function：它需要 FFmpeg、Basic Pitch、持久化的 RQ Worker 和定时清理进程。

## 架构

```text
浏览器
  -> Vercel Web (web/)
  -> Railway API (api/Dockerfile，公开 HTTPS)
       -> Railway PostgreSQL
       -> Railway Redis -> Railway RQ Worker
       -> 私有 S3 兼容存储桶
       -> Railway Cleanup Cron
```

API 是唯一允许读取或写入存储桶的组件。浏览器只会收到短时有效的签名下载路径，绝不会收到永久对象 URL。

## 账号和仓库

你需要 Vercel、Railway、一个 S3 兼容的服务商（例如 Cloudflare R2），以及一个 Vercel 和 Railway 均可访问的私有 Git 仓库。将 `songdance/` 目录的内容作为仓库根目录推送。不要提交 `.env`、凭据、数据库文件、上传的音频或 `api/uv.lock`。

## 1. 创建私有对象存储

1. 创建一个私有存储桶，例如 `songdance-production`。
2. 创建仅限该存储桶的 S3 API 凭据，用于对象读/写/删和分段上传清理。
3. 保持存储桶的公开访问关闭。浏览器不需要 CORS，因为全部对象访问都经由 API。
4. 如果服务商支持生命周期规则，添加一天过期规则作为备份。应用程序清理 Cron 仍然是权威，因为它还会删除数据库元数据并释放配额状态。

将端点、区域、存储桶、访问密钥和私密密钥记录在密码管理器中。

## 2. 创建 Railway 数据服务

1. 创建一个 Railway 项目，并添加 PostgreSQL 和 Redis 服务。
2. 两者均保持在 Railway 私有网络中。不要创建公开的数据库或 Redis 域名。
3. 使用 Railway 变量引用，将服务商变量复制到应用服务。`SONGDANCE_DATABASE_URL` 接受 Railway 的 `postgresql://` URL，并会将其规范化为已安装的 psycopg 驱动。

## 3. 创建 Railway API

从私有仓库创建一个服务，并将其配置文件路径设置为 `/infra/railway.toml`。仅为此服务提供公开的 Railway 域名。

将 `infra/env.production.example` 中的全部 `SONGDANCE_*` 变量复制到该服务，并替换占位符。重要值如下：

- `SONGDANCE_CORS_ORIGINS`：最终的 Vercel 生产环境源站，不带尾随路径。
- `SONGDANCE_DATABASE_URL`：私有 Railway PostgreSQL URL。
- `SONGDANCE_REDIS_URL`：私有 Railway Redis URL。
- `SONGDANCE_DOWNLOAD_SIGNING_SECRET`：使用 `openssl rand -hex 32` 生成。
- `SONGDANCE_STORAGE_BACKEND=s3`：生产环境必须使用持久化共享存储。
- `SONGDANCE_YOUTUBE_ENABLED=false`：首个版本保持关闭。
- `SONGDANCE_GLOBAL_ACTIVE_JOB_LIMIT=2` 和 `SONGDANCE_DAILY_JOB_LIMIT=25`：初始成本上限；仅在测量内存和处理成本后再提高。

容器入口点会在 Uvicorn 之前运行 `alembic upgrade head`。成功部署后，`https://API_DOMAIN/health` 必须返回 HTTP 200。

`infra/env.production.example` 特意使用保留的 `192.0.2.0/24` 文档地址段。部署前，替换为精确的 Railway 边缘对等 CIDR。API 会在生产环境拒绝 `0.0.0.0/0` 和 `::/0`；绝不要为了让代理检查通过而使用默认路由。若 Railway 无法提供稳定的边缘 CIDR，应将 API 保持在可提供该 CIDR 的私有网关之后，或在暴露服务前调整代理边界。

## 4. 创建 Worker 和 Cleanup 服务

从同一提交创建另外两个服务：

| 服务 | 配置路径 | 公开域名 | 副本数 |
|---|---|---:|---:|
| Worker | `/infra/railway-worker.toml` | 否 | 1 |
| Cleanup | `/infra/railway-cleanup.toml` | 否 | Cron |

为两者提供与 API 相同的数据库、Redis、存储、签名和限制变量。Worker 必须显示 RQ 启动日志，并监听 `songdance` 队列。Cleanup 服务每 15 分钟运行一次，并必须记录 `failed=0` 的 `cleanup_cycle`。

在测量模型内存和队列行为之前，不要将 Worker 扩容至一个副本以上。每个 Worker 进程都会加载转录模型。

## 5. 将 Web 部署到 Vercel

1. 将同一个私有仓库导入 Vercel。
2. 将 **Root Directory** 设置为 `web`。
3. 保持 Framework Preset 为 Next.js。`web/vercel.json` 提供安装命令、构建命令和响应安全头。
4. 为 Production 和 Preview 环境添加 `NEXT_PUBLIC_API_URL=https://API_DOMAIN`。
5. 部署并记录最终的 `https://*.vercel.app` URL。
6. 返回 Railway API，将 `SONGDANCE_CORS_ORIGINS` 设置为该精确源站，然后重新部署 API。若添加自定义 Web 域名，在迁移期间用逗号分隔并同时包含两个 HTTPS 源站，随后删除已废弃的源站。

由于 `NEXT_PUBLIC_API_URL` 会编译进浏览器 JavaScript，修改它需要重新部署 Vercel。

## 6. 生产验收清单

部署后执行以下检查；在真实 URL 上运行前，均不能视为已验证。

1. `curl --fail https://API_DOMAIN/health` 返回 `status=ok`。
2. 在隐私窗口打开 Vercel URL；`/`、`/transcribe`、`/examples`、`/privacy` 和 `/terms` 无需身份验证即可加载。
3. 上传合法的 1 秒、30 秒和 90 秒 WAV 样本。对 MP3 和 M4A 重复有代表性的上传；拒绝无效文件和超过 25 MB 的文件。
4. 在任务排队期间刷新任务 URL，并确认进度可以恢复。
5. 确认乐谱和钢琴卷帘视图、原始音频/MIDI 播放、循环、速度和移调功能。
6. 下载 MIDI、MusicXML 和 PDF；解析 MIDI/MusicXML，并目视检查 PDF。
7. 删除任务并确认其 URL 返回已过期/未找到，且下载停止。
8. 一小时内从同一客户端提交四个任务；第四个必须返回 HTTP 429。
9. 将一个测试任务的过期时间设为过去，运行一次 Cleanup，并确认数据库行和存储桶对象均已删除。随后恢复正常 Cron。
10. 在已部署模型上运行固定的 10 段音频人工回归套件；保留已签署的评审记录，以证明至少 7/10 的片段可用。
11. 在 375 px 宽度下重复核心上传流程，并检查不存在水平溢出。
12. 保持 YouTube 禁用，并确认本地上传流程完整可用。

## 回滚

1. 在 Vercel 中提升上一个成功部署。
2. 在 Railway 中将 API 和 Worker 回滚到同一个先前 Git 提交。当队列负载或模型代码发生变更时，绝不能只回滚其中一个。
3. 事故期间数据库迁移只能向前。若旧版应用无法读取新 schema，应部署兼容性修复，而不是破坏性地降级生产数据。
4. 将 `SONGDANCE_DAILY_JOB_LIMIT=1` 以暂停新任务，并等待活跃任务排空；任务运行期间不要删除 Redis。
5. 在重新开放每日限制前，验证 `/health`、一次上传、全部三种下载和删除。

官方参考资料：[Vercel 项目配置](https://vercel.com/docs/projects/project-configuration)、[Railway 配置即代码](https://docs.railway.com/reference/config-as-code) 和 [Railway 公网网络](https://docs.railway.com/networking/public-networking)。
