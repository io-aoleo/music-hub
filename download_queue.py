"""Bounded, persistent single/batch download queue. One process, multiple threads."""
import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from contextlib import contextmanager

class DownloadFailure(Exception):
    """Only messages deliberately sanitized by the service adapter belong here."""
    pass

class DownloadQueue:
    def __init__(self, path, download, workers=2, start=True):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        self.download = download
        self.condition = threading.Condition()
        self.db_lock = threading.RLock()
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS downloads (id TEXT PRIMARY KEY, song TEXT NOT NULL, status TEXT NOT NULL, message TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0)')
            db.execute("UPDATE downloads SET status='interrupted', message='服务重启中断，请点击重试', updated=? WHERE status='running'", (time.time(),))
        if os.name!='nt':self.path.chmod(0o600)
        if start:
            for _ in range(workers):
                threading.Thread(target=self.loop, daemon=True).start()

    @contextmanager
    def connect(self):
        # The supported runtime is one process. Serialize its short transactions
        # so workers do not exhaust SQLite's busy timeout on a slow NAS disk.
        # Network downloads run after the claiming transaction has released this lock.
        with self.db_lock:
            db = sqlite3.connect(self.path, timeout=20)
            db.row_factory = sqlite3.Row
            try:
                with db: yield db
            finally:
                db.close()

    @staticmethod
    def validate(songs):
        if not isinstance(songs, list) or not 1 <= len(songs) <= 200:
            raise ValueError('每次请选择 1～200 首歌曲')
        result = []
        for item in songs:
            if not isinstance(item, dict) or item.get('source') not in ('netease','qq','kuwo','kugou','migu'):
                raise ValueError('歌曲来源无效')
            if not isinstance(item.get('id'), (str, int)) or not str(item['id']).strip():
                raise ValueError('歌曲编号无效')
            song = {}
            for key in ('id','source','name','artist','album','cover','extra'):
                value = item.get(key, '')
                if not isinstance(value, (str,int)) or len(str(value)) > (16000 if key=='extra' else 2000):
                    raise ValueError('歌曲信息格式无效')
                song[key] = str(value)
            result.append(song)
        return result

    def enqueue(self, songs):
        songs = self.validate(songs)
        ids=[]; added=0
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            active = db.execute("SELECT id,song FROM downloads WHERE status IN ('queued','running')").fetchall()
            if len(active)+len(songs)>1000:
                raise ValueError('待处理歌曲超过 1000 首，请等待队列完成后再添加')
            existing = {(json.loads(j['song'])['source'], json.loads(j['song'])['id']):j['id'] for j in active}
            for song in songs:
                key = (song['source'],song['id'])
                if key in existing:
                    ids.append(existing[key]); continue
                job_id=uuid.uuid4().hex; now=time.time()
                db.execute('INSERT INTO downloads VALUES (?,?,?,?,?,?,0)',
                           (job_id,json.dumps(song,ensure_ascii=False),'queued','等待下载',now,now))
                existing[key]=job_id; ids.append(job_id); added+=1
        with self.condition:
            self.condition.notify_all()
        return {'ids':ids,'added':added,'duplicates':len(songs)-added}

    def list(self, limit=200):
        with self.connect() as db:
            rows=db.execute('SELECT * FROM downloads ORDER BY created DESC LIMIT ?', (limit,)).fetchall()
            counts=dict(db.execute('SELECT status, count(*) FROM downloads GROUP BY status').fetchall())
        return {'downloads':[{**dict(row),'song':json.loads(row['song'])} for row in rows], 'counts':counts}

    def action(self, job_id, action):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT status,song FROM downloads WHERE id=?',(job_id,)).fetchone()
            if not row: raise KeyError('任务不存在')
            status=row['status']
            if action=='cancel' and status=='queued':
                next_status,message='cancelled','已取消'
            elif action=='retry' and status in ('error','interrupted','cancelled'):
                song=json.loads(row['song'])
                active=db.execute("SELECT song FROM downloads WHERE status IN ('queued','running') AND id<>?",(job_id,)).fetchall()
                if any((other['source'],other['id'])==(song['source'],song['id']) for other in (json.loads(r['song']) for r in active)):
                    raise ValueError('同一首歌曲已在队列中，请等待现有任务完成')
                next_status,message='queued','等待重试'
            else:
                raise ValueError('任务状态已改变；正在下载的歌曲需等待当前请求结束')
            db.execute('UPDATE downloads SET status=?,message=?,updated=? WHERE id=?',
                       (next_status,message,time.time(),job_id))
        with self.condition:
            self.condition.notify_all()

    def run_once(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT id,song FROM downloads WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if not row: return False
            job_id=row['id']; song=json.loads(row['song'])
            db.execute("UPDATE downloads SET status='running',message='正在下载…',attempts=attempts+1,updated=? WHERE id=?",(time.time(),job_id))
        try:
            result=self.download(song)
            skipped=bool(result.get('skipped'))
            ok=skipped or result.get('saved') or result.get('status')=='ok'
            status='done' if ok else 'error'
            message='已存在，跳过下载' if skipped else '已保存到音乐目录' if ok else '下载失败，请检查平台 Token 或歌曲是否可用'
        except DownloadFailure as error:
            status,message='error',str(error)
        except Exception:
            status,message='error','下载失败，请检查网络、平台 Token 和目录写入权限'
        with self.connect() as db:
            db.execute('UPDATE downloads SET status=?,message=?,updated=? WHERE id=?',(status,message,time.time(),job_id))
        return True

    def loop(self):
        while True:
            try:
                if self.run_once(): continue
            except sqlite3.Error:
                pass
            with self.condition:
                self.condition.wait(timeout=3)
