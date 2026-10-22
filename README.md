# Music Hub

把音乐任务中心与 Go Music DL 下载引擎整合成一个项目。一个 Git 仓库、一份 Compose、一个浏览器入口。

- 任务中心：`http://NAS地址:9985/`
- 搜索、批量下载、定时任务、目录和平台设置：全部在同一 Hub 界面。
- 下载引擎没有宿主机端口映射，无需单独部署原 9981 项目。

## 启动

需要 Docker Compose v2，无需在宿主机安装 Python 或 Go。

```sh
git clone https://github.com/io-aoleo/music-hub.git
cd music-hub
docker compose up -d --build
```

打开 `http://设备地址:9985`，首次创建管理员密码，再确认音乐目录和平台 Cookie。
没有通用默认密码；内部服务 Token 自动生成并持久保存。提供正式登录页，旧版账号升级后会引导设置自己的密码。

音乐默认保存到项目目录 `./data/music`。使用飞牛已有音乐目录时，在 `.env` 填写自己的 `ENGINE_DOWNLOAD_PATH=/你的音乐目录` 后启动。
网页显示实际配置映射，可浏览、创建并选择 `/music` 子目录，保存前检查读写权限。

搜索结果支持勾选、全选和批量下载。下载队列、结果持久保存，支持取消等待项和失败重试；任务和设置均在 Hub 界面内完成。

完整的 **NAS 路径映射、权限处理、旧版升级、密码找回、HTTPS 与验证说明**见 [开箱即用指南](docs/getting-started.md)。

## 任务编辑

- **定时任务**：载入已保存计划，修改类型、时间、配额、歌单数、并发，点击“保存修改”。
- **运行中的任务**：在详情中修改本次下载目标。0 表示不限；修改即时生效，已发出的请求仍会完成。
- **历史任务**：点击历史记录，再点“载入参数修改”，调整后“立即开始”。生成新任务，保留原记录。
- 类型和并发在单次任务启动时确定，需通过新任务调整。

## 类型轮换

多选类型默认按点击顺序轮换，每次定时执行一种。例如每日选择“流行 → 欧美 → 粤语”：

今天流行，明天欧美，后天粤语，第四天重新流行。

页面展示接下来几次的实际日期、时间和类型，时间统一为北京时间。
每周、每月计划也在每次执行时换下一种。只有成功创建定时任务后才推进轮次；
服务离线或已有任务占用时不跳过类型，恢复后执行一次到期任务，不集中补跑全部错过的日期。
手动任务不推进轮次。修改时间、目标时保留下一类型；勾选“从第一种重新轮换”才重置。
若选择“每次全部类型”，每次会处理所有勾选类型。

## 旧数据迁移

迁移工具只创建副本，不覆盖旧数据，也不移动音乐文件。迁移前先停止旧任务，避免迁移后出现两个调度器同时下载。

```sh
python scripts/migrate_legacy.py \
  --tasks /vol1/1000/music_webui/data \
  --engine /home/sqal/go-music-dl/data \
  --destination /你的新目录/music-hub/data
```

在 `.env` 中配置：

```dotenv
HUB_TASKS_PATH=/你的新目录/music-hub/data/tasks
ENGINE_DATA_PATH=/你的新目录/music-hub/data/engine
ENGINE_DOWNLOAD_PATH=/你的旧音乐目录
```

SQLite 使用 backup API 复制一致性快照，任务历史、日志、下载去重记录和引擎配置保留。
迁移副本的计划默认停用。启动新服务后核对音乐设置，将下载目录改为 `/music`，确认轮换预览后再启用。
旧计划没有时区标记时，保留页面时分设置并按北京时间重新计算下次执行时间。
旧引擎如果还有数据目录以外的自定义文件、WebDAV 配置或绝对路径，需要一并核对挂载。

旧 9985 与新项目不能同时绑定相同端口。可先设置 `HUB_PORT=9986` 验证新项目，再切换。
本仓库的生成和推送不会自动停止现有服务。

## 配置分工

`.env.example` 是字段模板，`.env` 只留本机。

- HUB_*：Python 网关、账号、任务目录、对外端口、内部访问地址和内部令牌。
- ENGINE_*：Compose 构建及引擎数据、音乐挂载位置。
- MUSIC_DL_*：只由 Compose 传入 Go 服务，沿用上游配置名称。
- TZ：两个容器统一使用北京时间。

初始化服务自动生成内部令牌，Hub 和引擎从只读共享配置卷读取；旧版 HUB_ENGINE_TOKEN 可迁移复用，浏览器不接收这个令牌。
任务服务通过内部 API 读取 Cookie、发起下载，不直接打开引擎 SQLite。
管理员密码以哈希形式保存在任务数据卷，登录会话重启后仍有效。网页写操作使用 CSRF Token。
生产部署建议保持默认鉴权开启。

## 代码结构

```text
app.py                    任务执行、状态、编辑 API、定时调度
engine_client.py          下载引擎内部接口适配与 Cookie 缓存
gateway.py                统一鉴权、网页与音频流转发、健康检查
templates/                统一音乐界面、首次设置与登录
static/hub.js             搜索、多选下载、目录浏览和设置
auth.py                   管理员迁移、密码和 Cookie 会话
download_queue.py         SQLite 持久化批量下载队列
storage.py                目录映射、边界与写入检测
vendor/go-music-dl/        可从源码构建的 Go 下载引擎，保留上游许可
scripts/                  初始化配置、旧数据迁移
tests/                    任务、轮换、网关与前端回归检查
docs/architecture.md      模块边界、数据流和运行约束
compose.yaml              两个服务，一次部署
```

## 开发和验证

```sh
python -m venv .venv
# 激活虚拟环境后：
pip install -r requirements.txt
python -m unittest discover -s tests -v
node tests/test_ui.cjs

cd vendor/go-music-dl
go test ./internal/web -run 'TestHubInternalToken|TestAllowSaveLocal|TestAuth' -count=1
go build ./cmd/music-dl
```

Python 任务状态保存在内存及原子更新的 JSON 文件中，当前必须使用一个 Gunicorn worker。
默认一个 worker、16 个请求线程；调度与任务下载线程在该 worker 内共享状态。
不要直接增加 worker 数量，否则会重复运行调度器。增加实例前应迁移到 SQLite/PostgreSQL 持久化任务队列并拆出独立调度进程。

更换下载引擎时主要修改 engine_client.py；修改任务页面不需要重编译 Go。
如依赖下载较慢，可在 .env 使用 `ENGINE_GOPROXY=https://goproxy.cn,direct`。
其他网络环境可改为 `https://proxy.golang.org,direct`。Go 构建只下载服务用到的依赖，不预下载桌面版全部依赖。

可选 CI 模板在 `docs/checks.workflow.yml`。账号具有 GitHub Actions 工作流写入权限时，
将它放到 `.github/workflows/check.yml` 即可启用；手动验证命令不依赖 CI。

## 开源来源

下载引擎基于 [guohuiyuan/go-music-dl](https://github.com/guohuiyuan/go-music-dl)，
本仓库保留部署时源码快照及本地修改，不声称该快照等同于上游某个未修改提交。
详见 [NOTICE](NOTICE) 和 [LICENSE](LICENSE)；整合代码按 AGPL-3.0 发布。

Alpine 依赖源可通过 `ENGINE_APK_MIRROR` 配置；可按网络情况配置阿里云镜像，以加快 FFmpeg 依赖安装。

迁移大型音乐库且原索引为空时，可在引擎初始化数据库后运行：

python scripts/seed_music_index.py --database data/engine/settings.db --music 你的音乐目录

该工具只从文件名和文件属性生成轻量索引，不解码或修改音频，不覆盖已有元数据；封面、时长等详细信息由引擎后台补全。
