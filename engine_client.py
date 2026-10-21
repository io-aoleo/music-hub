"""下载引擎适配层：业务代码只依赖这里，不依赖 Go 的数据库或管理员密码。"""
import os,time,threading
import requests

class EngineClient:
    def __init__(self):
        self.base_url=os.environ.get("HUB_ENGINE_URL","http://engine:9981").rstrip("/")
        self.token=os.environ.get("HUB_ENGINE_TOKEN","")
        self._cookie="";self._until=0;self._lock=threading.Lock()
    def headers(self):
        return {"X-Music-Hub-Token":self.token,"Origin":self.base_url,
                "Referer":self.base_url+"/music/","X-Requested-With":"XMLHttpRequest",
                "Accept":"application/json"}
    def netease_cookie(self):
        explicit=os.environ.get("HUB_NETEASE_COOKIE","")
        if explicit:return explicit
        with self._lock:
            if time.monotonic()<self._until:return self._cookie
            try:
                with requests.Session() as client:
                    client.trust_env=False
                    r=client.get(self.base_url+"/music/cookies",headers=self.headers(),timeout=8)
                    r.raise_for_status()
                    self._cookie=r.json().get("netease","")
                self._until=time.monotonic()+30
            except (requests.RequestException,ValueError):
                # 不在异常或日志中打印 Cookie、内部令牌、响应体。
                self._until=time.monotonic()+5
            return self._cookie
    def healthy(self):
        try:
            with requests.Session() as client:
                client.trust_env=False
                r=client.get(self.base_url+"/music/healthz",timeout=3)
                return r.status_code==200 and r.json().get("status")=="ok"
        except (requests.RequestException,ValueError):return False
