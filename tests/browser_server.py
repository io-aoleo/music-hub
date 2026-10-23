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
qr_sessions={}
class Provider(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,body,kind='application/json'):
        body=body.encode();self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if self.path.startswith('/music/qr_login/netease'):
            from urllib.parse import urlsplit,parse_qs
            key=parse_qs(urlsplit(self.path).query)['key'][0];entry=qr_sessions[key];entry['checks']+=1
            status='expired' if entry['expired'] else 'scanned' if entry['checks']==1 else 'success'
            result={'status':status,'key':key}
            if status=='success':
                cookies['netease']='fixture-private-platform-cookie';result.update(cookie=cookies['netease'],extra={'cookie_saved':'true'})
            return self.reply(json.dumps(result))
        if self.path.startswith('/music/search'):
            return self.reply(''.join('<li class="song-card" data-id="%s" data-source="netease" data-name="测试歌曲 %s" data-artist="测试歌手" data-album="测试专辑"></li>'%(i,i) for i in range(3)),'text/html; charset=utf-8')
        data=settings if self.path.startswith('/music/settings') else cookies if self.path.startswith('/music/cookies') else {'status':'ok'}
        self.reply(json.dumps(data))
    def do_POST(self):
        if self.path.startswith('/music/qr_login/netease'):
            key='fixture-'+str(len(qr_sessions)+1);qr_sessions[key]={'checks':0,'expired':len(qr_sessions)==1}
            return self.reply(json.dumps({'key':key,'url':'https://music.163.com/login?codekey='+key,'expires_at':time.time()+300}))
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
def search_fixture(query,source,page,size):
    total=45 if query=='分页' else 3
    songs=[dict(id=('page-' if query=='分页' else '')+str(i),source=source,name='测试歌曲 '+str(i),artist='测试歌手',album='测试专辑',extra='{}') for i in range((page-1)*size,min(page*size,total))]
    return dict(songs=songs,page=page,page_size=size,total=total,total_pages=max(1,(total+size-1)//size),has_more=page*size<total)
app.extensions['provider_search'].search=search_fixture
app.run(host='127.0.0.1',port=int(os.environ.get('BROWSER_TEST_PORT','18985')),threaded=True,use_reloader=False)
