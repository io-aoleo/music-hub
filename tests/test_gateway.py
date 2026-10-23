import base64,json,threading,unittest,os,tempfile
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
from flask import Flask
from gateway import register_gateway
from engine_client import EngineClient

class FakeEngine(BaseHTTPRequestHandler):
    seen=[]
    def log_message(self,*args):pass
    def do_GET(self):
        type(self).seen.append(dict(self.headers))
        if self.path=="/music/redirect":
            data=b"redirect-body"
            self.send_response(301);self.send_header("Location","/music/")
            self.send_header("Content-Length",str(len(data)));self.end_headers();self.wfile.write(data)
            return
        if self.path.startswith("/music/cookies"):
            data=b'{"netease":"fixture-cookie"}'
        elif self.path.startswith("/music/healthz"):
            data=b'{"status":"ok"}'
        else:
            data=b"audio-bytes"
        self.send_response(206 if self.headers.get("Range") else 200)
        self.send_header("Content-Type","application/octet-stream")
        self.send_header("Content-Length",str(len(data)))
        if self.headers.get("Range"):self.send_header("Content-Range","bytes 0-10/100")
        self.send_header("Set-Cookie","one=1; Path=/music")
        self.send_header("Set-Cookie","two=2; Path=/music")
        self.end_headers();self.wfile.write(data)

class GatewayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(("127.0.0.1",0),FakeEngine)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def setUp(self):
        self.token="t"*43
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        with patch.dict(os.environ,{"HUB_DATA_DIR":self.temp.name,"HUB_AUTH_REQUIRED":"true","HUB_USER":"admin","HUB_PASSWORD":"fixture-password","HUB_ENGINE_TOKEN":self.token,"HUB_ENGINE_URL":"http://127.0.0.1:"+str(self.server.server_port),"HUB_TESTING":"0"}):
            self.engine=EngineClient()
            app=Flask("test-gateway");register_gateway(app,self.engine)
            store=app.extensions['accounts'];store.change(store.get()[2],'fixture-password')
            app.add_url_rule("/api/action",view_func=lambda:("ok",200),methods=["POST"])
            self.c=app.test_client()
        self.auth={"Authorization":"Basic "+base64.b64encode(b"admin:fixture-password").decode()}
        FakeEngine.seen.clear()
    def test_protects_all_routes_but_health(self):
        self.assertEqual(self.c.get("/music/").status_code,401)
        self.assertEqual(self.c.get("/healthz").status_code,200)
        self.assertEqual(self.c.get("/music/",headers=self.auth).headers['Location'],'/')
    def test_audio_range_and_multiple_cookies(self):
        r=self.c.get("/music/download?id=123",headers={**self.auth,"Range":"bytes=0-10","X-Music-Hub-Token":"attacker"},buffered=True)
        self.assertEqual(r.status_code,206);self.assertEqual(r.data,b"audio-bytes")
        self.assertEqual(r.headers["Content-Range"],"bytes 0-10/100")
        self.assertEqual(len(r.headers.getlist("Set-Cookie")),2)
        self.assertNotIn("Authorization",FakeEngine.seen[-1])
        self.assertEqual(FakeEngine.seen[-1]["X-Music-Hub-Token"],self.token)
    def test_cross_origin_write_rejected(self):
        self.assertEqual(self.c.post("/api/action",headers={**self.auth,"Origin":"http://evil.test"}).status_code,403)
    def test_redirect_body_is_preserved_after_requests_consumes_raw(self):
        r=self.c.get("/music/redirect",headers=self.auth,buffered=True)
        self.assertEqual(r.status_code,301)
        self.assertEqual(r.data,b"redirect-body")
        self.assertEqual(r.headers["Content-Length"],str(len(b"redirect-body")))
        self.assertEqual(r.headers["Location"],"/music/")
    def test_cookie_client_internal_auth(self):
        self.assertEqual(self.engine.netease_cookie(),"fixture-cookie")
        self.assertEqual(FakeEngine.seen[-1]["X-Music-Hub-Token"],self.token)
    def test_disabled_gateway_auth_preserves_original_engine_auth(self):
        with patch.dict(os.environ,{"HUB_AUTH_REQUIRED":"false"}):
            app=Flask("test-public");register_gateway(app,self.engine)
        c=app.test_client()
        self.assertEqual(c.get("/music/test",headers={"X-Music-Hub-Token":self.token}).status_code,200)
        self.assertNotIn("X-Music-Hub-Token",FakeEngine.seen[-1])
    def test_fresh_start_requires_web_setup(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ,{"HUB_DATA_DIR":folder,"HUB_AUTH_REQUIRED":"true","HUB_PASSWORD":"","HUB_TESTING":"0","MUSIC_WEBUI_TESTING":"0"}):
                app=Flask('fresh');register_gateway(app,self.engine)
            client=app.test_client()
            self.assertEqual(client.get('/').headers['Location'],'/setup')
            self.assertNotIn('WWW-Authenticate',client.get('/api/jobs').headers)
