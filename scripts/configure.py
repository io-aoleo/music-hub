"""初始化本机配置。真实密码、令牌只写入被 Git 忽略的 .env。"""
from pathlib import Path
import argparse,secrets,os,re
parser=argparse.ArgumentParser(description="初始化 Music Hub 配置")
parser.add_argument("--username",default="admin")
args=parser.parse_args()
root=Path(__file__).resolve().parent.parent
target=root/".env"
if target.exists():raise SystemExit(".env 已存在，请直接编辑；不会覆盖现有配置")
if not re.fullmatch(r"[A-Za-z0-9_.@-]{1,64}",args.username):raise SystemExit("用户名仅支持字母、数字及 _.@-，长度 1～64")
text=(root/".env.example").read_text(encoding="utf-8")
text=text.replace("HUB_USER=admin","HUB_USER="+args.username)
text=text.replace("HUB_PASSWORD=\n","HUB_PASSWORD="+secrets.token_urlsafe(18)+"\n")
text=text.replace("HUB_ENGINE_TOKEN=\n","HUB_ENGINE_TOKEN="+secrets.token_urlsafe(32)+"\n")
with target.open("x",encoding="utf-8") as f:f.write(text)
if os.name!="nt":target.chmod(0o600)
for name in ("tasks","engine","music"):(root/"data"/name).mkdir(parents=True,exist_ok=True)
print("已创建 .env 和 data 目录。打开本机 .env 查看或修改登录密码，然后 docker compose up -d --build")
