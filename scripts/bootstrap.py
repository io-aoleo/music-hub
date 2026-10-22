"""Compose one-shot initialization. Never recursively changes existing NAS permissions."""
import os
import secrets
from pathlib import Path


def initialize():
    for name in ('/data/tasks', '/data/engine', '/music', '/shared'):
        path=Path(name);path.mkdir(parents=True,exist_ok=True)
        if path.stat().st_uid==0 and not any(path.iterdir()):
            os.chown(path,1000,1000)
            path.chmod(0o750)
    token_path=Path('/shared/engine-token')
    supplied=os.environ.get('HUB_ENGINE_TOKEN','').strip()
    token=supplied or (token_path.read_text().strip() if token_path.exists() else secrets.token_urlsafe(48))
    if len(token)<32: raise SystemExit('HUB_ENGINE_TOKEN 至少需要 32 位，或留空由程序自动生成')
    temporary=token_path.with_suffix('.tmp')
    temporary.write_text(token,encoding='utf-8');temporary.chmod(0o400);os.chown(temporary,1000,1000)
    temporary.replace(token_path)
    print('Music Hub 初始化完成；首次打开网页创建管理员。内部令牌已持久化。')


if __name__=='__main__': initialize()
