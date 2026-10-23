"""Persistent administrator account and cookie sessions, including legacy migration."""
import os
import re
import secrets
import sqlite3
import threading
import time
from datetime import timedelta
from contextlib import contextmanager
from pathlib import Path

from flask import jsonify, redirect, request, send_file, session
from werkzeug.security import check_password_hash, generate_password_hash


class Accounts:
    def __init__(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / 'accounts.sqlite3'
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS account (id INTEGER PRIMARY KEY CHECK(id=1), username TEXT, password TEXT, version TEXT, change_required INTEGER)')
            db.execute('CREATE TABLE IF NOT EXISTS secrets (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT)')
            db.execute('INSERT OR IGNORE INTO secrets VALUES (1, ?)', (secrets.token_hex(32),))
            self.secret = db.execute('SELECT value FROM secrets WHERE id=1').fetchone()[0]
        if os.name != 'nt':
            self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=15)
        try:
            with db: yield db
        finally:
            db.close()

    def get(self):
        with self.connect() as db:
            return db.execute('SELECT username, password, version, change_required FROM account WHERE id=1').fetchone()

    def create(self, username, password, change_required=False):
        with self.connect() as db:
            try:
                db.execute('INSERT INTO account VALUES (1, ?, ?, ?, ?)',
                           (username, generate_password_hash(password), secrets.token_hex(16), int(change_required)))
            except sqlite3.IntegrityError:
                return False
        return True

    def change(self, old_version, password):
        version = secrets.token_hex(16)
        with self.connect() as db:
            result = db.execute('UPDATE account SET password=?, version=?, change_required=0 WHERE id=1 AND version=?',
                                (generate_password_hash(password), version, old_version))
        return version if result.rowcount else None


def register_auth(app):
    required = os.environ.get('HUB_AUTH_REQUIRED', 'true').lower() == 'true'
    accounts = Accounts(os.environ.get('HUB_DATA_DIR', '/data/tasks'))
    app.extensions['accounts'] = accounts
    legacy_password = os.environ.get('HUB_PASSWORD', '')
    if legacy_password and not accounts.get():
        accounts.create(os.environ.get('HUB_USER', 'admin'), legacy_password, change_required=True)
    app.config.update(SECRET_KEY=accounts.secret, SESSION_COOKIE_NAME='music_hub_session',
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      SESSION_REFRESH_EACH_REQUEST=False,
                      SESSION_COOKIE_SECURE=os.environ.get('HUB_COOKIE_SECURE', 'false').lower() == 'true',
                      PERMANENT_SESSION_LIFETIME=timedelta(days=7), MAX_CONTENT_LENGTH=1024*1024)
    attempts = {}; attempt_lock = threading.Lock()

    def csrf():
        if 'csrf' not in session:
            session['csrf'] = secrets.token_hex(24)
        return session['csrf']

    def logged_in(account):
        return bool(account and session.get('version') == account[2])

    def credentials(account):
        auth = request.authorization
        return bool(account and auth and auth.type.lower() == 'basic' and
                    secrets.compare_digest((auth.username or '').encode(), account[0].encode()) and
                    check_password_hash(account[1], auth.password or ''))

    def login_session(account):
        session.clear(); session['version'] = account[2]; session.permanent = True
        return jsonify(ok=True, csrf=csrf(), change_required=bool(account[3]))

    @app.before_request
    def authenticate():
        if request.path == '/healthz':
            return None
        account = accounts.get()
        safe = request.method in ('GET', 'HEAD', 'OPTIONS')
        if not safe:
            origin = request.headers.get('Origin')
            from urllib.parse import urlsplit
            if origin and urlsplit(origin).netloc != request.host:
                return jsonify(ok=False, msg='请求来源不匹配'), 403
        # Public auth endpoints still require a same-session CSRF token for writes.
        public = request.path in ('/login', '/setup', '/api/auth/status', '/api/auth/login', '/api/auth/setup')
        basic = credentials(account) if required and not public else False
        if not safe and required and not basic:
            token = request.headers.get('X-CSRF-Token', '')
            if not secrets.compare_digest(token.encode(), session.get('csrf', '!').encode()):
                return jsonify(ok=False, msg='页面已过期，请刷新后重试'), 403
        if public or not required:
            return None
        if not logged_in(account) and not basic:
            if request.path.startswith('/api/') or request.path.startswith('/music/'):
                return jsonify(ok=False, msg='请先登录', login='/login' if account else '/setup'), 401
            return redirect('/login' if account else '/setup')
        if account[3] and request.path not in ('/api/auth/password', '/api/auth/logout'):
            if request.path.startswith('/api/'):
                return jsonify(ok=False, msg='请先设置自己的密码', setup='/setup'), 428
            return redirect('/setup')

    @app.after_request
    def private_response(response):
        if request.path != '/healthz':
            response.headers['Cache-Control'] = 'no-store'
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-Frame-Options'] = 'DENY'
            response.headers['Referrer-Policy'] = 'same-origin'
        return response

    @app.get('/login')
    @app.get('/setup')
    def login_page():
        return send_file(Path(app.root_path) / 'templates' / 'auth.html')

    @app.get('/api/auth/status')
    def auth_status():
        account = accounts.get(); authenticated = logged_in(account)
        return jsonify(ok=True, configured=bool(account), authenticated=authenticated,
                       username=account[0] if authenticated else '',
                       change_required=bool(account and account[3]) if authenticated else False,
                       auth_required=required, csrf=csrf())

    def data():
        body = request.get_json(silent=True)
        return body if isinstance(body, dict) else {}

    def valid_password(value):
        return isinstance(value, str) and 10 <= len(value) <= 128

    @app.post('/api/auth/setup')
    def setup():
        body = data(); username = body.get('username'); password = body.get('password')
        if accounts.get():
            return jsonify(ok=False, msg='管理员已经创建，请登录'), 409
        if not isinstance(username, str) or not re.fullmatch(r'[A-Za-z0-9_.@-]{1,64}', username):
            return jsonify(ok=False, msg='用户名须为 1～64 位字母、数字或 _.@-'), 400
        if not valid_password(password) or body.get('confirmation') != password:
            return jsonify(ok=False, msg='密码须为 10～128 位，且两次输入一致'), 400
        if not accounts.create(username, password):
            return jsonify(ok=False, msg='管理员已创建，请登录'), 409
        return login_session(accounts.get())

    @app.post('/api/auth/login')
    def login():
        ip = request.remote_addr or 'unknown'; now = time.monotonic()
        with attempt_lock:
            recent = [t for t in attempts.get(ip, []) if now-t < 300]
            if len(recent) >= 8:
                return jsonify(ok=False, msg='尝试次数过多，请 5 分钟后重试'), 429
            # Reserve before hashing to also limit concurrent attempts.
            attempts[ip] = recent + [now]
            if len(attempts) > 1000:
                for key in list(attempts):
                    if not attempts[key] or now-attempts[key][-1] > 300:
                        attempts.pop(key, None)
        body = data(); account = accounts.get()
        username = body.get('username', ''); password = body.get('password', '')
        if not isinstance(username, str) or not isinstance(password, str) or len(password)>128:
            return jsonify(ok=False, msg='用户名或密码错误'), 401
        if not account or username != account[0] or not check_password_hash(account[1], password):
            return jsonify(ok=False, msg='用户名或密码错误'), 401
        with attempt_lock:
            attempts.pop(ip, None)
        return login_session(account)

    @app.post('/api/auth/password')
    def password():
        body = data(); account = accounts.get(); password = body.get('password')
        old = body.get('old_password', '')
        if not account or not isinstance(old,str) or not check_password_hash(account[1], old):
            return jsonify(ok=False, msg='当前密码不正确'), 400
        if not valid_password(password) or password != body.get('confirmation') or check_password_hash(account[1], password):
            return jsonify(ok=False, msg='新密码须为 10～128 位，与旧密码不同且两次输入一致'), 400
        if not accounts.change(account[2], password):
            return jsonify(ok=False, msg='账号已更新，请重新登录'), 409
        return login_session(accounts.get())

    @app.post('/api/auth/logout')
    def logout():
        session.clear()
        return jsonify(ok=True)

    return required
