"""为迁移后的大型音乐库建立轻量索引；不读取音频内容，不修改音乐文件。"""
import argparse,base64,os,sqlite3,time
from pathlib import Path
from datetime import datetime,timezone
from contextlib import closing
AUDIO={".aac",".flac",".m4a",".mp3",".ogg",".wav",".wma"}

def seed_index(database,music):
    root=Path(music).resolve()
    if not root.is_dir() or not Path(database).is_file():raise ValueError("数据库或音乐目录不存在")
    rows=[];now=datetime.now(timezone.utc).isoformat(" ")
    for folder,dirs,files in os.walk(root,followlinks=False):
        for filename in files:
            path=Path(folder)/filename;ext=path.suffix.lower()
            if ext not in AUDIO or path.is_symlink():continue
            stat=path.stat();rel=path.relative_to(root).as_posix()
            title=path.stem;artist="Unknown"
            if " - " in title:artist,title=title.split(" - ",1)
            track_id=base64.urlsafe_b64encode(rel.encode()).decode().rstrip("=")
            modified=datetime.fromtimestamp(stat.st_mtime,timezone.utc).isoformat(" ")
            rows.append((track_id,rel,title,artist,"",0,stat.st_size,ext,"",0,
                         int(path.with_suffix(".lrc").is_file()),modified,now))
    with closing(sqlite3.connect(database,timeout=30)) as db:
        exists=db.execute("select 1 from sqlite_master where type='table' and name='local_music_index'").fetchone()
        if not exists:raise ValueError("请先让下载引擎初始化一次数据库")
        before=db.execute("select count(*) from local_music_index").fetchone()[0]
        # 精细元数据可能正在后台补全，已有行绝不覆盖。
        with db:
            db.executemany("""INSERT OR IGNORE INTO local_music_index
              (id,rel_path,name,artist,album,duration,size,ext,cover,has_cover,has_lyric,mod_time,scanned_at)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",rows)
        after=db.execute("select count(*) from local_music_index").fetchone()[0]
    return {"audio_files":len(rows),"index_added":after-before,"index_total":after}

if __name__=="__main__":
    parser=argparse.ArgumentParser(description="从文件名快速建立本地音乐索引，后台扫描随后补全歌词、封面、时长")
    parser.add_argument("--database",required=True,type=Path)
    parser.add_argument("--music",required=True,type=Path)
    args=parser.parse_args();start=time.monotonic()
    print({**seed_index(args.database,args.music),"seconds":round(time.monotonic()-start,2)})
