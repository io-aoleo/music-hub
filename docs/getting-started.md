# 从零启动与升级

## 首次启动

需要 Docker Engine 和 Docker Compose v2。无需在宿主机安装 Python 或 Go，无需提前生成管理员密码或内部 Token。

```sh
git clone https://github.com/io-aoleo/music-hub.git
cd music-hub
docker compose up -d --build
```

打开 `http://设备地址:9985`，按网页提示创建用户名和密码（10～128 位），然后确认音乐目录和写入权限。平台 Cookie 可按需填写；未配置时，部分平台或歌曲的可用性会受限制。

首次构建需要联网拉取基础镜像和依赖。容器启动后可通过 `docker compose ps -a` 查看初始化和健康状态：`init` 正常退出 0，`engine` 和 `hub` 为 healthy。网页账号保存在任务数据卷，密码只保存哈希。没有通用默认密码。

## 飞牛 / NAS 路径映射

默认音乐写入项目下 `./data/music`。Hub 和引擎挂载同一个目录，容器内统一叫 `/music`。

要使用 NAS 现有目录，在项目目录创建 `.env`，填写自己的真实目录，例如：

```dotenv
ENGINE_DOWNLOAD_PATH=/vol1/1000/music
HUB_PORT=9985
```

然后执行：

```sh
docker compose up -d --build
```

页面「路径与 Token」会显示配置的宿主机路径和容器路径，并以运行用户测试写入。这里的宿主机路径是 Compose 配置值；相对路径相对于 Compose 项目目录。更改 `.env` 后需重新创建容器，单纯刷新页面或 `docker compose restart` 不会更新挂载。

- `/music` 是容器路径；不要把 `/vol1/...` 填入网页下载路径。
- 网页可浏览、创建并选择 `/music` 内的子目录，例如 `/music/华语`。
- 系统拒绝 `..` 和指向挂载范围外的符号链接。
- 两个长期服务都使用 UID 1000。已有 NAS 目录需要授予该 UID 读取、创建和写入权限，且不能以只读方式挂载。
- 初始化服务只设置新建空目录的所有者，不递归修改已有音乐库权限。已有 ACL 或其他 UID 的目录需在 NAS 权限管理中调整。
- 页面检查可写后再保存；批量任务提交与歌曲下载也会检查目录。

账号、任务历史和引擎配置默认使用 Docker 命名卷，音乐使用上述可见目录。不要执行 `docker compose down -v`，该命令会删除账号、任务和引擎配置的数据卷。普通 `docker compose down` / `up` 保留数据。

## 批量下载

搜索结果支持单曲下载、勾选多首、全选当前页；可跨关键词和来源累计选择，每次最多提交 200 首，队列最多等待 1000 首。平台已在等待或执行的同一首歌曲会去重。下载中心显示等待、执行、成功、失败和中断数量，最近 200 条详细记录，以及取消等待项、失败重试操作。

队列使用 SQLite 持久化，默认 2 个下载工作线程。重启后未执行的项目继续排队，正在执行的项目标记中断，由用户确认重试。已下载文件由引擎去重。正在执行的网络请求不会伪装成已取消，需要等待完成或超时。

「批量与定时」保留按类型搜索歌单、下载配额、轮换、任务历史、日志与目标编辑。所有操作都在 Hub 中完成，不要求打开引擎项目的界面。

## 旧版升级

先备份任务目录、引擎数据目录、Compose / `.env`。升级时保留原来的 `HUB_TASKS_PATH`、`ENGINE_DATA_PATH`、`ENGINE_DOWNLOAD_PATH`，避免切换到新的空数据卷。

```sh
git pull
docker compose up -d --build
```

旧版 `.env` 中的 `HUB_USER` / `HUB_PASSWORD` 仅在尚无本地账号时迁移一次。升级后先用旧账号登录，网页会要求输入旧密码并设置新密码。完成后可从 `.env` 删除 `HUB_PASSWORD`；后续启动不会用旧环境变量覆盖数据库里的密码。旧历史、轮换计划、去重记录和平台 Cookie 保留。

旧版 `data/downloads` 默认路径通过引擎已有链接映射到 `/music`。如果以前使用自定义绝对路径，请在升级后进入设置，选择实际音乐挂载范围内的路径。仓库另有 `scripts/migrate_legacy.py` 用于旧的分离部署；迁移前停止旧调度器，避免重复下载。

## 密码修改与找回

登录后在设置中修改密码，需要输入当前密码，其他设备的旧登录立即失效。忘记密码时，在有权管理 Docker 的终端运行：

```sh
docker compose exec hub python scripts/reset_password.py
```

按终端提示输入两次新密码。该操作不删除账号、平台 Cookie、音乐、任务或计划。

## 访问与配置

统一入口为 9985，引擎不对宿主机公开端口。网页登录使用 HttpOnly / SameSite 会话 Cookie，写操作使用 CSRF Token；内部服务 Token 自动生成并保存在共享配置卷，不传给浏览器。

外网使用已有反向代理提供 HTTPS；仅通过 HTTPS 访问时可在 `.env` 设置 `HUB_COOKIE_SECURE=true`。如设置为 true 后仍通过 HTTP 打开，浏览器不会发送登录 Cookie，请改用 HTTPS 或恢复此值。不要直接开放尚未创建管理员的首次安装入口。

`.env.example` 提供端口、镜像源和挂载变量示例。普通安装无需运行 `scripts/configure.py`；该脚本保留供旧流程兼容。仅排障的私有环境可显式关闭 `HUB_AUTH_REQUIRED`，公开部署保持 true。

## 验证

```sh
python -m unittest discover -s tests -v
node tests/test_ui.cjs
docker compose config --quiet
```

浏览器端到端测试使用 `tests/browser_server.py`（真实 Hub 和本地确定性音乐服务），另一个终端运行 `node tests/browser_flow.cjs`。需要 Playwright；可用 `PLAYWRIGHT_MODULE`、`BROWSER_EXECUTABLE` 指定现有安装。覆盖首次创建管理员、登录退出、CSRF、创建目录、批量下载、页面重载和手机布局。真实音乐平台需要另外联网验证。
