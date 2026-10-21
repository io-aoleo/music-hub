"""离线迁移旧数据：只写入新的空目录，不修改或覆盖旧服务数据。"""
import argparse,sqlite3,shutil,json
from contextlib import closing
from pathlib import Path
p=argparse.ArgumentParser(description="将旧 music-webui 与 go-music-dl 数据复制到 Music Hub")
p.add_argument("--tasks",required=True,type=Path,help="旧 music-webui/data")
p.add_argument("--engine",required=True,type=Path,help="旧 go-music-dl/data")
p.add_argument("--destination",required=True,type=Path,help="新的 Music Hub data 目录，必须为空")
a=p.parse_args()
if not a.tasks.is_dir() or not a.engine.is_dir():p.error("旧数据目录不存在")
dest=a.destination.resolve()
if dest==a.tasks.resolve() or dest==a.engine.resolve():p.error("目标不能是旧目录")
if dest.is_relative_to(a.tasks.resolve()) or dest.is_relative_to(a.engine.resolve()):p.error("目标不能位于旧目录内")
if dest.exists() and any(dest.iterdir()):p.error("目标目录非空，已停止以避免覆盖")
dest.mkdir(parents=True,exist_ok=True)
shutil.copytree(a.tasks,dest/"tasks")
(dest/"engine").mkdir()
for source in a.engine.iterdir():
    if source.suffix in (".db",".sqlite",".sqlite3") and source.is_file():
        # SQLite backup API 一致性复制，不直接复制正在写入的 WAL 文件。
        with closing(sqlite3.connect(source.resolve().as_uri()+"?mode=ro",uri=True)) as src:
            with closing(sqlite3.connect(dest/"engine"/source.name)) as dst:src.backup(dst)
# 旧下载文件不自动复制或移动；使用 ENGINE_DOWNLOAD_PATH 绑定旧音乐目录。
schedule=dest/"tasks"/"schedule.json"
if schedule.exists():
    s=json.loads(schedule.read_text(encoding="utf-8"));s["enabled"]=False
    schedule.write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding="utf-8")
print("迁移副本已创建，定时任务默认停用。设置音乐挂载目录并核对后，再在新页面启用。")
