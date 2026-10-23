import os, sys, tempfile, unittest, json, threading
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent.parent))
temp=tempfile.TemporaryDirectory()
os.environ.update(HUB_DATA_DIR=temp.name,HUB_TESTING="1",HUB_AUTH_REQUIRED="false")
import app as m

def job():
    return dict(id=42,cats=["流行"],per=1,workers=2,target=0,tag="测试",status="queued",
                saved=0,skip=0,fail=0,att=0,cur="",stop=False,active={},submitted=0,processed=0)

class DetailsTest(unittest.TestCase):
    def test_storage_failure_stops_before_downloading(self):
        j=job();m.JOBS.append(j)
        with patch.object(m.engine,'check_storage',side_effect=ValueError('音乐目录不可写')),patch.object(m,'search_pl') as search:
            m.run_job(j)
        self.assertEqual(j['status'],'error');search.assert_not_called()
    def setUp(self):
        storage_check=patch.object(m.engine,"check_storage")
        storage_check.start();self.addCleanup(storage_check.stop)
        m.JOBS.clear();m.SEEN.clear();m.DONE.clear()
        self.client=m.app.test_client()
    def test_old_job_and_missing_job(self):
        m.JOBS.append(dict(id=1,status="done",saved=5,started="2026-10-21 01:00:00",finished="2026-10-21 01:01:30"))
        data=self.client.get("/api/jobs/1").json["job"]
        self.assertEqual(data["elapsed"],90)
        self.assertEqual(data["active"],[])
        self.assertNotIn("submitted",data)
        self.assertEqual(self.client.get("/api/jobs/999").status_code,404)
    def test_live_details(self):
        j=job();j.update(status="running",submitted=5,processed=2,active={"a":dict(name="歌曲",since=m.time.time()-3)})
        m.JOBS.append(j)
        data=self.client.get("/api/jobs/42").json["job"]
        self.assertEqual(data["queued"],2)
        self.assertGreaterEqual(data["active"][0]["elapsed"],3)
        self.assertIsInstance(j["active"],dict)
    def test_login_failure_is_finished(self):
        j=job();m.JOBS.append(j)
        with patch.object(m,"mdl_login",side_effect=RuntimeError("secret credential")):
            m.run_job(j)
        self.assertEqual(j["status"],"error");self.assertTrue(j["finished"])
        self.assertEqual(j["active"],{})
        self.assertNotIn("secret credential",self.client.get("/api/jobs/42").get_data(as_text=True))
    def test_success_records_playlist_and_counts(self):
        j=job();m.JOBS.append(j)
        response=type("Response",(),{"read":lambda _:b'{"saved":true}'})()
        with patch.object(m,"mdl_login",return_value="local"),patch.object(m,"search_pl",return_value=[("p","测试歌单",10)]),patch.object(m,"pl_ids",return_value=["s"]),patch.object(m,"detail",return_value=[{"id":"s","name":"测试歌曲"}]),patch.object(m.U,"urlopen",return_value=response),patch.object(m.time,"sleep"):
            m.run_job(j)
        self.assertEqual(j["status"],"done");self.assertEqual(j["saved"],1)
        self.assertEqual(j["submitted"],1);self.assertEqual(j["processed"],1)
        self.assertEqual(j["playlist_name"],"测试歌单");self.assertEqual(j["active"],{})
        self.assertTrue(j["finished"])
    def test_active_song_visible_while_worker_runs(self):
        j=job();j["status"]="running";m.JOBS.append(j)
        entered=threading.Event();release=threading.Event()
        def block(*args):entered.set();release.wait(2)
        with patch.object(m,"_download_one",side_effect=block):
            worker=threading.Thread(target=m.download_one,args=(j,{"id":1,"name":"正在下载"},{}))
            worker.start()
            try:
                self.assertTrue(entered.wait(1))
                self.assertEqual(self.client.get("/api/jobs/42").json["job"]["active"][0]["name"],"正在下载")
            finally:release.set();worker.join()
        self.assertEqual(j["processed"],1);self.assertFalse(j["active"])
    def test_no_results_and_stop(self):
        for stopped,expected in [(False,"noresult"),(True,"stopped")]:
            j=job();j["stop"]=stopped
            with patch.object(m,"mdl_login",return_value="local"),patch.object(m,"search_pl",return_value=[]):
                m.run_job(j)
            self.assertEqual(j["status"],expected);self.assertTrue(j["finished"])
    def test_log_id_validation_and_queue_blocks_second_start(self):
        self.assertEqual(self.client.get("/api/log?job=../jobs").status_code,400)
        m.JOBS.append(job())
        self.assertTrue(m.is_running())
        self.assertFalse(self.client.post("/api/start",json={"cats":["流行"]}).json["ok"])

if __name__=="__main__":unittest.main()
