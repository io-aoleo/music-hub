"""可选真实引擎契约检查。先启动独立引擎，再设置 HUB_ENGINE_URL / HUB_ENGINE_TOKEN。"""
import os,tempfile,base64
from pathlib import Path
os.environ.update(HUB_TESTING="1",HUB_AUTH_REQUIRED="true",HUB_USER="integration",HUB_PASSWORD="integration-fixture")
tmp=tempfile.TemporaryDirectory()
os.environ["HUB_DATA_DIR"]=tmp.name
import app
client=app.app.test_client()
auth={"Authorization":"Basic "+base64.b64encode(b"integration:integration-fixture").decode()}
health=client.get("/healthz")
assert health.status_code==200,health.json
r=client.get("/music/",headers=auth,follow_redirects=True)
assert r.status_code==200,(r.status_code,r.headers)
assert b"Music Hub" in r.data
cookies=client.get("/music/cookies",headers=auth)
assert cookies.status_code==200,cookies.status_code
assert isinstance(cookies.json,dict)
r=client.post("/api/schedule",headers=auth,json=dict(enabled=True,cats=["流行","欧美"],mode="rotate",time="03:00"))
assert r.status_code==200,r.json
assert r.json["schedule"]["next_cats"]==["流行"]
assert len(r.json["schedule"]["preview"])==2
assert client.get("/music/cookies").status_code==401
print("PASS: real Go engine health, page and navigation, internal cookie contract, unified auth, rotation API")
