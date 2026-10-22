"""Local browser regression fixture; real Hub with a deterministic fake music provider."""
import json
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
root=Path(tempfile.mkdtemp(prefix='music-hub-browser-'))
(root/'music').mkdir()
settings={'downloadDir':'/music','downloadToLocal':True}
cookies={}
class Provider(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,body,kind='application/json'):
        body=body.encode();self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if self.path.startswith('/music/search'):
            return self.reply(''.join('<li class="song-card" data-id="%s" data-source="netease" data-name="测试歌曲 %s" data-artist="测试歌手" data-album="测试专辑"></li>'%(i,i) for i in range(3)),'text/html; charset=utf-8')
        data=settings if self.path.startswith('/music/settings') else cookies if self.path.startswith('/music/cookies') else {'status':'ok'}
        self.reply(json.dumps(data))
    def do_POST(self):
        if self.path.startswith('/music/download'):
            time.sleep(.4);return self.reply('{"saved":true}')
        body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
        if self.path.startswith('/music/settings'):settings.update(body)
        else:cookies.update(body)
        self.reply(json.dumps(settings if self.path.startswith('/music/settings') else {'status':'ok'}))
provider=ThreadingHTTPServer(('127.0.0.1',0),Provider)
threading.Thread(target=provider.serve_forever,daemon=True).start()
os.environ.update(HUB_DATA_DIR=str(root/'tasks'),HUB_MUSIC_ROOT=str(root/'music'),HUB_MUSIC_HOST_PATH=str(root/'music'),HUB_ENGINE_URL='http://127.0.0.1:'+str(provider.server_port),HUB_ENGINE_TOKEN='browser-fixture-internal-token-0000000000',HUB_PASSWORD='',HUB_AUTH_REQUIRED='true',HUB_TESTING='0')
os.environ.pop('HUB_ENGINE_TOKEN_FILE',None)
from app import app
app.run(host='127.0.0.1',port=int(os.environ.get('BROWSER_TEST_PORT','18985')),threaded=True,use_reloader=False)
