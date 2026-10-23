import threading
import unittest
from unittest.mock import MagicMock
from qr_login import QRLogins


class QRLoginTest(unittest.TestCase):
    def setUp(self):
        self.now=1000.;self.engine=MagicMock();self.status='waiting';self.saved=True;self.calls=[]
        def call(path,method='GET',**kwargs):
            self.calls.append((path,method,kwargs));result=MagicMock()
            if method=='POST':data={'key':'provider-key-private','url':'https://music.163.com/login?codekey=fixture','expires_at':1300}
            elif path=='cookies':data={'netease':'private-cookie-value'}
            else:data={'status':self.status,'cookie':'private-cookie-value','key':'provider-key-private','extra':{'cookie_saved':'true' if self.saved else 'false'}}
            result.json.return_value=data;return result
        self.call=call;self.manager=QRLogins(call,self.engine,threading.RLock(),clock=lambda:self.now)

    def test_qr_generation_and_success_never_exposes_cookie(self):
        created=self.manager.create('owner');self.assertTrue(created['qr_image'].startswith('data:image/svg+xml;base64,'))
        self.assertNotIn('provider-key-private',str(created));self.assertEqual(created['expires_in'],300)
        identity=created['id'];self.assertEqual(self.manager.check(identity,'owner')['status'],'waiting')
        self.now+=2;self.status='scanned';self.assertEqual(self.manager.check(identity,'owner')['status'],'scanned')
        self.now+=2;self.status='success';result=self.manager.check(identity,'owner')
        self.assertEqual(result['status'],'success');self.assertNotIn('private-cookie',str(result));self.assertNotIn('provider-key',str(result));self.assertEqual(self.engine._until,0)

    def test_ownership_expiry_cancel_and_refresh(self):
        identity=self.manager.create('owner')['id']
        with self.assertRaises(KeyError):self.manager.check(identity,'other')
        self.manager.cancel(identity,'owner');self.assertEqual(self.manager.check(identity,'owner')['status'],'cancelled')
        self.now+=3;identity=self.manager.create('owner')['id'];self.now+=301
        before=len(self.calls);self.assertEqual(self.manager.check(identity,'owner')['status'],'expired');self.assertEqual(len(self.calls),before)

    def test_polling_is_throttled_and_missing_persistence_is_not_success(self):
        identity=self.manager.create('owner')['id'];self.manager.check(identity,'owner');before=len(self.calls)
        self.manager.check(identity,'owner');self.assertEqual(len(self.calls),before)
        self.now+=2;self.status='success';self.saved=False
        with self.assertRaises(ValueError):self.manager.check(identity,'owner')

    def test_creation_limit_and_refresh_invalidates_old_code(self):
        old=self.manager.create('owner')['id']
        with self.assertRaises(ValueError):self.manager.create('owner')
        self.now+=3;self.manager.create('owner')
        self.assertEqual(self.manager.check(old,'owner')['status'],'cancelled')
