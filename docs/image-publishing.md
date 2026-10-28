# 维护者：发布容器镜像

GitHub Actions 的 `Docker image` 流程先运行测试、Compose 配置检查和真实容器生命周期检查，再构建 Linux AMD64 / ARM64 镜像。PR 只验证，不上传。

## GHCR

默认发布到 `ghcr.io/io-aoleo/music-hub`，使用当前工作流的 `GITHUB_TOKEN`。不需要 Google 或浏览器登录数据。

## Docker Hub 同步发布

先在自己的 Docker Hub 命名空间创建公开的 `music-hub` 仓库，再在 GitHub 仓库 **Settings → Secrets and variables → Actions** 配置：

- Repository variable `DOCKERHUB_USERNAME`：有权推送该仓库的 Docker Hub 用户名。
- Repository variable `DOCKERHUB_IMAGE`：完整镜像名称，例如 `你的用户名/music-hub`，不含标签。
- Repository secret `DOCKERHUB_TOKEN`：该账户具备目标仓库写权限的访问令牌。不要填写到源码、Compose 或 Issue 中。

未设置 `DOCKERHUB_IMAGE` 时仅发布 GHCR；设置后同一次构建同时上传两个仓库。如果 Docker Hub 认证失败，工作流会报错，不会把同步失败当作成功。

配置好后手动运行 `Docker image` 工作流可发布当前默认分支。默认分支发布 `latest` 和提交标签；推送 `v1.0.0` 这样的版本标签会发布 `1.0.0`。不要为重新发布而移动已有版本标签。

对已有版本，保留原有多架构索引、各架构清单和镜像层进行仓库间复制，不要用当前分支重新构建并冒充旧版本。复制后检查标签与 AMD64 / ARM64 架构，并在未登录状态下验证可读取镜像清单，再更新面向用户的部署文档。

发布令牌只用于上传，不会作为 Docker 构建参数或镜像内容。运行时账号、音乐平台凭据、任务数据库和下载文件来自各自设备的数据挂载，不随公共镜像发布。
