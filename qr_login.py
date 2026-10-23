"""Session-bound QR login. Return a scannable image, never a platform cookie or service token."""
import base64
import io
import secrets
import threading
import time
from urllib.parse import urlsplit
import qrcode
from qrcode.image.svg import SvgPathImage
from flask import jsonify, session


class QRLogins:
    def __init__(self, call, engine, config_lock, clock=time.time):
        self.call=call;self.engine=engine;self.config_lock=config_lock;self.clock=clock
        self.entries={};self.lock=threading.Lock()

    def create(self,owner):
        with self.lock:
            self.entries={key:e for key,e in self.entries.items() if e['expires']>self.clock()}
            if len(self.entries)>=32:raise ValueError('扫码请求较多，请稍后重试')
            for entry in self.entries.values():
                if entry['owner']==owner and self.clock()-entry['created']<2:
                    raise ValueError('请稍候再刷新二维码')
        # Finish any in-flight old check before publishing the replacement QR.
        with self.config_lock:
            data=self.call('qr_login/netease','POST',timeout=(5,25)).json()
            key=data.get('key');url=data.get('url');parts=urlsplit(url or '')
            if not key or not isinstance(key,str) or len(key)>2048 or parts.scheme!='https' or parts.hostname!='music.163.com':
                raise ValueError('网易云未返回可用二维码，请稍后重试')
            now=self.clock()
            try:expires=min(now+300,float(data.get('expires_at') or now+300))
            except (TypeError,ValueError):expires=now+300
            if expires<=now:raise ValueError('二维码已过期，请重新生成')
            output=io.BytesIO();qrcode.make(url,image_factory=SvgPathImage,border=4).save(output)
            identity=secrets.token_urlsafe(24)
            entry=dict(owner=owner,key=key,created=now,expires=expires,status='waiting',checked=0,lock=threading.Lock())
            with self.lock:
                for old in self.entries.values():
                    if old['owner']==owner and old['status'] not in ('success','failed','expired'):old['status']='cancelled'
                self.entries[identity]=entry
        return dict(id=identity,qr_image='data:image/svg+xml;base64,'+base64.b64encode(output.getvalue()).decode(),
                    expires_in=max(1,int(expires-now)),poll_interval=2500)

    def get(self,identity,owner):
        with self.lock:entry=self.entries.get(identity)
        if not entry or entry['owner']!=owner:raise KeyError('二维码不存在或不属于当前登录，请重新生成')
        return entry

    def check(self,identity,owner):
        entry=self.get(identity,owner)
        with entry['lock']:
            now=self.clock()
            if entry['status'] in ('success','failed','expired','cancelled'):
                return self.view(entry)
            if now>=entry['expires']:
                entry['status']='expired';return self.view(entry)
            if now-entry['checked']<1.5:return self.view(entry)
            entry['checked']=now
            # The engine saves a successful cookie. Serialize with manual cookie edits.
            with self.config_lock:
                if entry['status']=='cancelled':return self.view(entry)
                result=self.call('qr_login/netease',params={'key':entry['key']},timeout=(5,25)).json()
                status=result.get('status')
                if status not in ('waiting','scanned','success','expired','failed'):
                    raise ValueError('网易云登录状态异常，请刷新二维码')
                if status=='success':
                    saved=(result.get('extra') or {}).get('cookie_saved')=='true'
                    configured=bool(self.call('cookies',timeout=(5,10)).json().get('netease')) if saved else False
                    if not saved or not configured:
                        raise ValueError('扫码已确认，但凭据保存未完成，请重新扫码')
                    self.engine._until=0
            entry['status']=status
            return self.view(entry)

    @staticmethod
    def view(entry):
        status=entry['status']
        message={'waiting':'请打开网易云音乐 App 扫描二维码','scanned':'已扫码，请在手机上确认登录',
                 'success':'登录成功，网易云凭据已自动保存','expired':'二维码已过期，请刷新后重新扫码',
                 'failed':'本次登录未完成，请刷新二维码重试','cancelled':'已停止检查此二维码'}[status]
        return dict(status=status,message=message)

    def cancel(self,identity,owner):
        entry=self.get(identity,owner)
        with entry['lock']:
            if entry['status']!='success':entry['status']='cancelled'


def register_qr_login(app,call,engine,config_lock):
    manager=QRLogins(call,engine,config_lock);app.extensions['qr_logins']=manager
    def owner():
        if 'qr_owner' not in session:session['qr_owner']=secrets.token_hex(24)
        return session['qr_owner']
    @app.post('/api/qr-login/netease')
    def qr_create():
        try:return jsonify(ok=True,**manager.create(owner()))
        except ValueError as error:return jsonify(ok=False,msg=str(error)),400
    @app.post('/api/qr-login/<identity>/check')
    def qr_check(identity):
        try:return jsonify(ok=True,**manager.check(identity,owner()))
        except KeyError:return jsonify(ok=False,msg='二维码不存在或已失效，请重新生成'),404
        except ValueError as error:return jsonify(ok=False,msg=str(error)),400
    @app.post('/api/qr-login/<identity>/cancel')
    def qr_cancel(identity):
        try:manager.cancel(identity,owner())
        except KeyError:pass
        return jsonify(ok=True)
