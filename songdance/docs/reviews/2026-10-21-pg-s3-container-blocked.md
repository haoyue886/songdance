# 2026-10-21 PostgreSQL／S3 容器验收受阻

本轮从00ba774继续本地容器部署验收，计划使用一次性PostgreSQL16和MinIO测试S3协议。不部署、不连接正式数据库或云端存储，不修改原商业测试账本或18分部分退款记录。

## 实际结果

本机已有上一轮API/Redis镜像，但无PostgreSQL或MinIO镜像。直接执行`docker pull postgres:16-alpine`及`docker pull minio/minio:RELEASE.2025-04-22T22-12-26Z`，均在Docker Hub清单Head请求超时。

用户随后明确允许这两个固定官方仓库经既有代理下载、逐层SHA256校验并本地导入。基于上一轮Redis校验脚本生成两个固定仓库脚本，仍保留TLS验证、对象大小限制、清单/config/blob/diffID校验。实际首次下载：PostgreSQL在清单读取时TLS UNEXPECTED_EOF；MinIO清单读取返回401。人工核对两脚本的repository token scope与目标仓库一致；未确证401根因，不将其称为私有仓库或标签不存在。

各有界重试一次后，两个仓库均在清单读取时TLS UNEXPECTED_EOF。未关闭TLS验证、替换来源或修改全局代理。未获得清单和镜像层的完整校验结果，未生成可导入归档，也未执行docker load。此状态不能证明固定MinIO标签及其ARM64平台可用，需网络恢复后实际查询。

本轮没有创建验收容器、网络或数据卷，未启动PostgreSQL／MinIO／API／Worker，不涉及旧容器清理。没有运行迁移、S3读写或生产配置验证；上一轮ARM64/SQLite运行通过不能替代本次结果。

## 仅准备，尚未运行

临时S3检查草稿拟使用原create_storage，验证上传/下载内容、exists/delete、目标multipart abort及相同前缀对照对象保护。该草稿仅编译检查通过，尚未配置安全的完整隔离运行入口、独立审查或真实协议验证，不能直接对现有环境运行。生成整栈脚本的两次工具载荷语法错误发生在执行前，未生成driver或启动任何资源；保留准备未完成状态，不包装为已就绪。

## 下一步

先恢复Docker Hub或已有代理到registry-1.docker.io的TLS连通，再取得并校验两镜像的官方ARM64清单、配置及每层摘要。之后完成仅使用唯一私网/一次性数据卷/临时凭据的运行入口，并审查清理失败路径，才执行迁移、API健康和S3适配器检查。用户对这两个固定镜像的下载/导入授权继续保留，无需因同一网络故障重复询问。

本批仅记录已执行失败，不改生产代码或依赖，无需重复上一轮测试；实际PostgreSQL／S3、目标部署架构、漏洞检查和音乐质量门槛仍未通过。
