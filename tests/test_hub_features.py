import os
import tempfile
import unittest
import time
from unittest.mock import MagicMock,patch
from flask import Flask
from hub_features import register_features

class FeaturesTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.env=patch.dict(os.environ,{'HUB_DATA_DIR':self.temp.name,'HUB_MUSIC_ROOT':self.temp.name,'HUB_MUSIC_HOST_PATH':'/nas/music','HUB_TESTING':'1'})
        self.env.start();self.addCleanup(self.env.stop)
        self.engine=MagicMock(base_url='http://engine:9981');self.app=Flask(__name__)
        register_features(self.app,self.engine);self.client=self.app.test_client()
        self.app.secret_key='fixture-secret'
        provider_patch=patch.object(self.app.extensions['provider_search'],'get',return_value={'code':200,'result':{'songCount':1,'songs':[{'id':1,'name':'A & B'}]}})
        provider_patch.start();self.addCleanup(provider_patch.stop)
        self.settings={'downloadDir':'/music','webdavUrl':'https://example.test','webdavPassword':''}
        self.cookies={'netease':'private-value','qq':'keep-this'};self.sent=[]
        def request(method,url,**kwargs):
            result=MagicMock()
            if url.endswith('/settings'):
                result.json.return_value=dict(self.settings)
                if method=='POST': self.sent.append(('settings',kwargs['json']))
            elif url.endswith('/cookies'):
                result.json.return_value=dict(self.cookies)
                if method=='POST': self.sent.append(('cookies',kwargs['json']))
            elif url.endswith('/search'):
                result.text='<li class="song-card" data-id="1" data-source="netease" data-name="A &amp; B"></li>'
            elif url.endswith('/qr_login/netease'):
                result.json.return_value={'key':'fixture-provider-key','url':'https://music.163.com/login?codekey=fixture','expires_at':time.time()+300} if method=='POST' else {'status':'waiting'}
            elif url.endswith('/download'):result.json.return_value={'saved':True}
            return result
        self.mock=patch('hub_features.requests.Session');self.mock.start().return_value.__enter__.return_value.request.side_effect=request
        self.addCleanup(self.mock.stop)
    def test_search_and_masked_preferences(self):
        self.assertEqual(self.client.get('/api/search?q=test').json['songs'][0]['name'],'A & B')
        data=self.client.get('/api/preferences');self.assertNotIn('private-value',data.text)
        self.assertEqual(data.json['mapping']['host'],'/nas/music')
        self.assertTrue(data.json['tokens']['netease'])
    def test_search_pagination_validation_and_dispatch(self):
        for query in ['page=0','page=-1','page=1001','page=hello','page_size=0','page_size=51','page_size=bad']:
            self.assertEqual(self.client.get('/api/search?q=test&'+query).status_code,400)
        provider=self.app.extensions['provider_search']
        with patch.object(provider,'search',return_value={'songs':[],'page':2,'page_size':50,'total':60,'total_pages':2,'has_more':False}) as search:
            result=self.client.get('/api/search?q=test&source=qq&page=2&page_size=50')
        search.assert_called_once_with('test','qq',2,50);self.assertFalse(result.json['has_more'])
    def test_qr_routes_bind_login_challenge_to_browser_session(self):
        created=self.client.post('/api/qr-login/netease',json={})
        self.assertEqual(created.status_code,200);identity=created.json['id']
        self.assertNotIn('fixture-provider-key',created.text)
        other=self.app.test_client()
        self.assertEqual(other.post('/api/qr-login/'+identity+'/check',json={}).status_code,404)
        self.assertEqual(self.client.post('/api/qr-login/'+identity+'/check',json={}).json['status'],'waiting')
        self.client.post('/api/qr-login/'+identity+'/cancel',json={})
        self.assertEqual(self.client.post('/api/qr-login/'+identity+'/check',json={}).json['status'],'cancelled')
    def test_create_browse_save_and_preserve_settings(self):
        self.assertEqual(self.client.post('/api/storage',json={'path':'/music/华语'}).status_code,200)
        response=self.client.post('/api/preferences',json={'downloadDir':'/music/华语','tokens':{'netease':'new'}})
        self.assertEqual(response.status_code,200)
        self.assertEqual(dict(self.sent)['cookies'],{'netease':'new','qq':'keep-this'})
        self.assertEqual(dict(self.sent)['settings']['webdavUrl'],'https://example.test')
    def test_validation_does_not_modify_preferences(self):
        for path in ['/tmp','/music/../etc','/music/nonexistent']:
            self.assertEqual(self.client.post('/api/preferences',json={'downloadDir':path}).status_code,400)
        self.assertEqual(self.sent,[])
    def test_batch_background_download_no_navigation(self):
        song={'id':'1','source':'netease','name':'Track'}
        response=self.client.post('/api/downloads',json={'songs':[song,song,{**song,'id':'2'}]})
        self.assertEqual(response.status_code,202);self.assertEqual(response.json['added'],2)
        self.assertEqual(response.json['duplicates'],1);self.assertNotIn('Location',response.headers)
        queue=self.app.extensions['downloads']
        while queue.run_once():pass
        self.assertEqual(self.client.get('/api/downloads').json['counts'],{'done':2})
    def test_unwritable_directory_blocks_enqueue(self):
        with patch.object(self.app.extensions['music_storage'],'check',side_effect=ValueError('音乐目录不可写')):
            response=self.client.post('/api/downloads',json={'id':'1','source':'netease'})
        self.assertEqual(response.status_code,400)
        self.assertEqual(self.client.get('/api/downloads').json['downloads'],[])
