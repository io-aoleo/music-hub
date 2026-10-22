"""Native search, shared storage, settings and persistent batch downloads."""
import os, threading
from html.parser import HTMLParser
from pathlib import Path
import requests
from flask import jsonify, request
from download_queue import DownloadQueue,DownloadFailure
from storage import MusicStorage

class SearchParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.songs=[]
    def handle_starttag(self, tag, attrs):
        attributes=dict(attrs)
        if tag=='li' and 'song-card' in attributes.get('class','').split():
            song={key:attributes.get('data-'+key,'') for key in ('id','source','name','artist','album','cover','duration','extra')}
            if song['id'] and song['source']: self.songs.append(song)

def register_features(app,engine):
    config_lock=threading.RLock(); storage=MusicStorage()
    app.extensions['music_storage']=storage
    def call(path,method='GET',**kwargs):
        with requests.Session() as client:
            client.trust_env=False
            response=client.request(method,engine.base_url+'/music/'+path,headers=engine.headers(),timeout=(5,150),**kwargs)
            response.raise_for_status()
            return response
    def current_path(settings):
        path=settings.get('downloadDir','/music')
        return '/music' if path in ('data/downloads','/home/appuser/data/downloads') else path
    def download(song):
        try:
            with config_lock: storage.check(current_path(call('settings').json()))
        except (ValueError,OSError):
            raise DownloadFailure('下载目录不可访问或不可写，请在「路径与 Token」检查目录权限') from None
        try:
            return call('download','POST',params={**song,'save_local':'1'}).json()
        except requests.HTTPError as error:
            status=error.response.status_code if error.response is not None else 502
            message={401:'平台登录或内部服务认证失效，请检查 Token / Cookie',403:'平台拒绝下载，请检查账号权限或更新 Cookie',404:'歌曲资源不可用，请尝试其他音乐来源',429:'平台请求限流，请稍后重试'}.get(status,'平台未能返回可下载资源，请更新 Cookie、稍后重试或更换来源')
            raise DownloadFailure(message) from None
        except requests.Timeout:
            raise DownloadFailure('音乐服务请求超时，请稍后重试') from None
        except requests.ConnectionError:
            raise DownloadFailure('无法连接音乐服务，请检查服务状态后重试') from None
    queue=DownloadQueue(Path(os.environ.get('HUB_DATA_DIR','/data/tasks'))/'downloads.sqlite3',download,
                        start=os.environ.get('HUB_TESTING',os.environ.get('MUSIC_WEBUI_TESTING'))!='1')
    app.extensions['downloads']=queue
    @app.errorhandler(requests.RequestException)
    def upstream_error(error):
        return jsonify(ok=False,msg='音乐服务暂时不可用，请稍后重试'),502
    @app.get('/api/search')
    def search():
        query=request.args.get('q','').strip();source=request.args.get('source','netease')
        if not query or len(query)>300: return jsonify(ok=False,msg='请输入 1～300 字的歌曲或歌手名称'),400
        if source not in ('netease','qq','kuwo','kugou','migu'): return jsonify(ok=False,msg='音乐来源无效'),400
        response=call('search',params={'q':query,'sources':source,'type':'song'})
        parser=SearchParser();parser.feed(response.text)
        return jsonify(ok=True,songs=parser.songs)
    @app.route('/api/storage',methods=['GET','POST'])
    def storage_api():
        try:
            if request.method=='POST':
                body=request.get_json(silent=True)
                if not isinstance(body,dict): raise ValueError('请求格式错误')
                path=body.get('path');storage.check(path,create=True)
            else: path=request.args.get('path','/music')
            return jsonify(ok=True,**storage.browse(path))
        except (ValueError,OSError) as error:
            message=str(error) if isinstance(error,ValueError) else '目录无法访问，请检查挂载路径和 UID 1000 的权限'
            return jsonify(ok=False,msg=message,mapping={'container':'/music','host':storage.host_path}),400
    @app.route('/api/preferences',methods=['GET','POST'])
    def preferences():
        with config_lock:
            settings=call('settings').json();cookies=call('cookies').json()
            if request.method=='GET':
                return jsonify(ok=True,downloadDir=current_path(settings),tokens={k:bool(v) for k,v in cookies.items()},mapping={'container':'/music','host':storage.host_path})
            body=request.get_json(silent=True)
            if not isinstance(body,dict): return jsonify(ok=False,msg='请求格式错误'),400
            try:
                path=body.get('downloadDir');storage.check(path)
                tokens=body.get('tokens',{})
                if not isinstance(tokens,dict) or any(k not in ('netease','qq','kuwo','kugou','migu') or not isinstance(v,str) or len(v)>16000 for k,v in tokens.items()):
                    raise ValueError('Token 格式无效')
            except (ValueError,OSError) as error:
                return jsonify(ok=False,msg=str(error) if isinstance(error,ValueError) else '目录无法访问，请检查挂载和权限'),400
            settings.update(downloadDir=path.strip(),downloadToLocal=True)
            call('settings','POST',json=settings)
            if tokens:
                cookies.update(tokens);call('cookies','POST',json=cookies);engine._until=0
            return jsonify(ok=True,msg='设置已保存',downloadDir=path.strip())
    @app.route('/api/downloads',methods=['GET','POST'])
    def downloads():
        if request.method=='GET': return jsonify(ok=True,**queue.list())
        body=request.get_json(silent=True)
        if not isinstance(body,dict): return jsonify(ok=False,msg='请求格式错误'),400
        try:
            songs=DownloadQueue.validate(body.get('songs') if 'songs' in body else [body])
            with config_lock: storage.check(current_path(call('settings').json()))
            result=queue.enqueue(songs)
        except (ValueError,OSError) as error:
            return jsonify(ok=False,msg=str(error) if isinstance(error,ValueError) else '音乐目录不可写，请检查挂载和目录权限'),400
        return jsonify(ok=True,id=result['ids'][0],**result),202
    @app.post('/api/downloads/<job_id>/<action>')
    def download_action(job_id,action):
        if action not in ('retry','cancel'): return jsonify(ok=False,msg='不支持此操作'),400
        try: queue.action(job_id,action)
        except KeyError: return jsonify(ok=False,msg='任务不存在'),404
        except ValueError as error: return jsonify(ok=False,msg=str(error)),409
        return jsonify(ok=True)
