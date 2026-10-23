import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from download_queue import DownloadQueue,DownloadFailure

class QueueTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'downloads.sqlite3'
        self.queue=DownloadQueue(self.path,lambda song:{'saved':True},start=False)
        self.song={'id':'1','source':'netease','name':'Track'}
    def test_batch_validation_atomic_and_deduplication(self):
        result=self.queue.enqueue([self.song,self.song,{**self.song,'id':'2'}])
        self.assertEqual((result['added'],result['duplicates']),(2,1))
        with self.assertRaises(ValueError): self.queue.enqueue([self.song,{'source':'invalid','id':'3'}])
        self.assertEqual(len(self.queue.list()['downloads']),2)
    def test_restart_persists_queue_and_marks_running_interrupted(self):
        result=self.queue.enqueue([self.song,{**self.song,'id':'2'}]);first=result['ids'][0]
        with self.queue.connect() as db: db.execute("UPDATE downloads SET status='running' WHERE id=?",(first,))
        restarted=DownloadQueue(self.path,lambda song:{'saved':True},start=False)
        self.assertEqual(restarted.list()['counts'],{'interrupted':1,'queued':1})
        restarted.action(first,'retry')
        while restarted.run_once(): pass
        self.assertEqual(restarted.list()['counts'],{'done':2})
    def test_cancel_and_retry(self):
        key=self.queue.enqueue([self.song])['ids'][0]
        self.queue.action(key,'cancel');self.assertFalse(self.queue.run_once())
        self.queue.action(key,'retry');self.assertTrue(self.queue.run_once())
        self.assertEqual(self.queue.list()['downloads'][0]['attempts'],1)
    def test_retry_does_not_duplicate_an_active_song(self):
        first=self.queue.enqueue([self.song])['ids'][0];self.queue.action(first,'cancel')
        self.queue.enqueue([self.song])
        with self.assertRaises(ValueError):self.queue.action(first,'retry')
    def test_failed_download_does_not_block_following_song(self):
        def download(song):
            if song['id']=='1': raise RuntimeError('sensitive upstream error')
            return {'saved':True}
        self.queue.download=download;self.queue.enqueue([self.song,{**self.song,'id':'2'}])
        self.queue.run_once();self.queue.run_once()
        self.assertEqual(self.queue.list()['counts'],{'error':1,'done':1})
        self.assertNotIn('sensitive',str(self.queue.list()))
    def test_workers_claim_each_song_once(self):
        seen=[];errors=[];self.queue.download=lambda song: seen.append(song['id']) or {'saved':True}
        self.queue.enqueue([{**self.song,'id':str(i)} for i in range(30)])
        def consume():
            try:
                while self.queue.run_once(): pass
            except Exception as error:errors.append(error)
        threads=[threading.Thread(target=consume) for _ in range(4)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(len(seen),30);self.assertEqual(len(set(seen)),30)
        self.assertEqual(errors,[], 'Background worker errors must fail the concurrency test')
    def test_safe_provider_errors_are_actionable(self):
        def fail(song):raise DownloadFailure('平台请求限流，请稍后重试')
        self.queue.download=fail;self.queue.enqueue([self.song]);self.queue.run_once()
        self.assertIn('限流',self.queue.list()['downloads'][0]['message'])
