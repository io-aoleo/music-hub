# Music Hub

在 NAS 上搜索音乐、跨页选歌、批量下载，按每日／每周／每月计划补充曲库。网页、下载引擎和初始化整合在一个容器中。

[源码与完整文档](https://github.com/io-aoleo/music-hub) · [版本与离线包](https://github.com/io-aoleo/music-hub/releases) · [飞牛图文教程](https://club.fnnas.com/forum.php?mod=viewthread&tid=75595)

![分页搜索与跨页多选](https://raw.githubusercontent.com/io-aoleo/music-hub/2420cd6/docs/images/community/03-search-batch.jpg)

## 镜像与架构

- Docker Hub：`ioaoleo/music-hub:1.0.0`，或持续更新的 `ioaoleo/music-hub:latest`。
- 备用 GHCR：`ghcr.io/io-aoleo/music-hub:1.0.0`，或 `ghcr.io/io-aoleo/music-hub:latest`。
- 支持 Linux AMD64 / ARM64，按设备自动选择架构。两个仓库的用户名不同，请按完整地址填写。
- 公开镜像无需登录即可拉取。实际可用性、速度和匿名限额取决于网络与镜像仓库。

## Docker Compose 安装

需要 Docker Engine 和 Compose v2。下载项目编排：

```sh
mkdir -p music-hub && cd music-hub
curl -fsSLo compose.yaml https://raw.githubusercontent.com/io-aoleo/music-hub/main/compose.yaml
```

在同目录创建 `.env`，填写自己的宿主机绝对目录；下面的飞牛路径只是示例：

```dotenv
MUSIC_HUB_IMAGE=ioaoleo/music-hub:1.0.0
ENGINE_DOWNLOAD_PATH=/vol1/1000/music
HUB_PORT=9985
```

```sh
docker compose up -d
docker compose ps -a
```

飞牛也可在 Docker → Compose 中导入同一个目录启动。正常运行只有 `music-hub-hub-1` 一个容器，健康状态为 healthy；不用单独部署引擎、挂载 Docker Socket 或使用 privileged。

打开 `http://你的设备地址:9985`，首次设置管理员用户名和至少 10 位密码，没有通用默认密码。

## 目录与平台登录

宿主机 `/vol1/1000/music` 挂载到容器 `/music`；网页下载路径填写 `/music` 或其子目录。音乐目录需允许 UID 1000 写入，页面提供实际写入检查。

网页「路径与 Token」可生成宿主机目录配置；应用挂载变更需要更新原项目 `.env` 并重新创建容器，单纯重启不会更换挂载。更换目录不自动搬迁旧文件。

网易云支持在「路径与 Token」扫码并在手机确认后自动保存平台 Cookie，其他平台可填写 Cookie。管理员密码、音乐平台凭据和内部 Token 分别管理。账号权限、资源可用性和平台限流可能影响下载结果。

## 搜索、批量与定时下载

搜索支持网易云、QQ 音乐、酷我、酷狗、咪咕。每页 20 或 50 首，支持跳页和跨页保留勾选，每次最多提交 200 首。下载中心可以查看队列、取消等待项和重试失败项；关闭网页不影响后台运行。

定时下载在「批量与定时」中设置：依次勾选音乐类型，设置每类歌单数和并发，在「定时任务 · 北京时间」勾选启用，设置每日／每周／每月、时间、定时目标和类型轮换模式，最后点击「保存修改」。例如每天 12:00、目标 100、流行 → 欧美 → 粤语，每次一种依次轮换。0 表示目标不限，跳过的重复歌曲不计入新增下载数，并发可能略超目标，资源不足可能达不到目标。

保存计划不会立即下载；容器需要保持运行，浏览器可以关闭。已有歌单任务运行时不会叠加执行，也不会集中补跑所有错过的日期。停用时取消启用并保存。完整步骤见源码 README 和飞牛图文教程。

## 升级与备份

备份 `.env`、账号／任务／引擎数据卷和音乐目录，保留原 Compose 项目名与所有目录映射。固定版本用户先修改镜像版本，再执行：

```sh
docker compose pull
docker compose up -d
```

Docker Hub 不通时可仅将 `MUSIC_HUB_IMAGE` 改为相应 GHCR 地址再执行上述命令。不要用 `docker compose down -v` 升级，它会删除命名卷数据。

发布页中的 AMD64 离线包使用 GHCR 镜像名，离线导入请按发布说明选择镜像名，不要给 ARM64 设备导入 AMD64 包。

公共镜像只包含应用与运行依赖。个人账号、平台 Cookie、Token、任务和音乐来自各自实例的数据挂载，不随镜像分发。反馈时不要附带密码或凭据。

AGPL-3.0。引擎基于 Go Music DL；完整许可、来源和使用说明见源码仓库。
