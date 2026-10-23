import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from flask import Flask
from auth import Accounts,register_auth


class AuthTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.env=patch.dict(os.environ,{'HUB_DATA_DIR':self.temp.name,'HUB_AUTH_REQUIRED':'true','HUB_PASSWORD':'','HUB_TESTING':'1'})
        self.env.start();self.addCleanup(self.env.stop)
        self.app=self.make_app();self.client=self.app.test_client()

    def make_app(self):
        app=Flask(__name__);register_auth(app)
        app.add_url_rule('/',endpoint='home',view_func=lambda:'private')
        app.add_url_rule('/api/private',endpoint='private',view_func=lambda:({'ok':True},200),methods=['GET','POST'])
        return app

    def post(self,path,body,client=None):
        client=client or self.client
        csrf=client.get('/api/auth/status').json['csrf']
        return client.post(path,json=body,headers={'X-CSRF-Token':csrf})

    def setup(self):
        return self.post('/api/auth/setup',{'username':'admin','password':'a-long-password','confirmation':'a-long-password'})

    def test_first_run_redirect_and_password_required(self):
        self.assertEqual(self.client.get('/').headers['Location'],'/setup')
        self.assertEqual(self.client.get('/api/private').status_code,401)
        for body in [{'username':'admin','password':'short','confirmation':'short'}, {'username':'admin','password':'long-password','confirmation':'different'}]:
            self.assertEqual(self.post('/api/auth/setup',body).status_code,400)
        self.assertEqual(self.setup().status_code,200)
        self.assertEqual(self.client.get('/').data,b'private')
        self.assertEqual(self.setup().status_code,409)
        record=self.app.extensions['accounts'].get()
        self.assertNotIn('a-long-password',record[1])

    def test_csrf_and_origin(self):
        self.setup()
        self.assertEqual(self.client.post('/api/private',json={}).status_code,403)
        token=self.client.get('/api/auth/status').json['csrf']
        self.assertEqual(self.client.post('/api/private',json={},headers={'X-CSRF-Token':token,'Origin':'https://evil.test'}).status_code,403)
        self.assertEqual(self.post('/api/private',{}).status_code,200)

    def test_session_and_account_survive_restart(self):
        self.setup();cookie=self.client.get_cookie('music_hub_session')
        fresh=self.make_app().test_client();fresh.set_cookie('music_hub_session',cookie.value)
        self.assertEqual(fresh.get('/api/private').status_code,200)
        self.assertTrue(fresh.get('/api/auth/status').json['configured'])
        self.assertNotIn('Set-Cookie',fresh.get('/api/private').headers)

    def test_password_change_revokes_other_sessions(self):
        self.setup();other=self.app.test_client()
        self.assertEqual(self.post('/api/auth/login',{'username':'admin','password':'a-long-password'},other).status_code,200)
        self.assertEqual(self.post('/api/auth/password',{'old_password':'wrong','password':'a-new-password','confirmation':'a-new-password'}).status_code,400)
        self.assertEqual(self.post('/api/auth/password',{'old_password':'a-long-password','password':'a-new-password','confirmation':'a-new-password'}).status_code,200)
        self.assertEqual(other.get('/api/private').status_code,401)
        self.assertEqual(self.client.get('/api/private').status_code,200)
        self.assertEqual(self.post('/api/auth/logout',{}).status_code,200)
        self.assertEqual(self.client.get('/api/private').status_code,401)
        self.assertEqual(self.post('/api/auth/login',{'username':'admin','password':'a-new-password'}).status_code,200)

    def test_legacy_password_requires_change_and_is_not_reimported(self):
        with patch.dict(os.environ,{'HUB_PASSWORD':'legacy-password'}): app=self.make_app()
        client=app.test_client()
        response=self.post('/api/auth/login',{'username':'admin','password':'legacy-password'},client)
        self.assertTrue(response.json['change_required'])
        self.assertEqual(client.get('/api/private').status_code,428)
        self.assertEqual(self.post('/api/auth/password',{'old_password':'legacy-password','password':'new-password-123','confirmation':'new-password-123'},client).status_code,200)
        with patch.dict(os.environ,{'HUB_PASSWORD':'legacy-password'}): app=self.make_app()
        client=app.test_client()
        self.assertEqual(self.post('/api/auth/login',{'username':'admin','password':'legacy-password'},client).status_code,401)
        self.assertEqual(self.post('/api/auth/login',{'username':'admin','password':'new-password-123'},client).status_code,200)

    def test_concurrent_setup_has_one_winner(self):
        store=Accounts(self.temp.name);results=[]
        def create(): results.append(store.create('admin','strong-password'))
        threads=[threading.Thread(target=create) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(sorted(results),[False,True])

    def test_login_rate_limit(self):
        self.setup()
        for _ in range(8): self.assertEqual(self.post('/api/auth/login',{'username':'admin','password':'wrong'}).status_code,401)
        self.assertEqual(self.post('/api/auth/login',{'username':'admin','password':'wrong'}).status_code,429)
