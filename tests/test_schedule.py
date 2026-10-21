import unittest,json
from pathlib import Path
from unittest.mock import patch
from datetime import datetime
from test_details import m,job

class ScheduleTest(unittest.TestCase):
    def setUp(self):
        m.JOBS.clear()
        Path(m.SCF).unlink(missing_ok=True)
        self.c=m.app.test_client()
    def save(self,**overrides):
        d=dict(enabled=True,cats=["流行","欧美","粤语"],time="03:15",freq="daily",target=50,per=2,workers=2,mode="rotate",weekday=0,day=1)
        d.update(overrides)
        r=self.c.post("/api/schedule",json=d)
        self.assertEqual(r.status_code,200,r.json)
        return r.json["schedule"]
    def test_daily_rotation_and_restart_persistence(self):
        self.save()
        observed=[]
        for _ in range(4):
            s=m.load_sched()
            with patch.object(m,"make_job",side_effect=lambda cats,*args:observed.append(cats) or {"id":1}):
                m.scheduler_tick(s["next"])
            # 下一次不在本轮重复触发，重读文件模拟进程重启恢复位置。
            self.assertGreater(m.load_sched()["next"],s["next"])
            self.assertIsNone(m.scheduler_tick(s["next"]))
        self.assertEqual(observed,[["流行"],["欧美"],["粤语"],["流行"]])
    def test_edit_preserves_cursor_and_reset_is_explicit(self):
        self.save()
        s=m.load_sched();s["rotation_index"]=1;m.save_sched(s)
        updated=self.save(target=80,time="04:20")
        self.assertEqual(updated["next_cats"],["欧美"])
        self.assertEqual(updated["target"],80)
        self.assertEqual(self.save(reset_rotation=True)["next_cats"],["流行"])
    def test_all_mode_and_preview_timezone(self):
        s=self.save(mode="all")
        self.assertEqual(s["next_cats"],["流行","欧美","粤语"])
        self.assertIn("03:15",s["preview"][0]["time"])
        a=datetime(2026,10,21,1,0,tzinfo=m.APP_TZ)
        nxt=m.compute_next(dict(freq="daily",hour=3,minute=15),a)
        self.assertEqual(datetime.fromtimestamp(nxt,m.APP_TZ).hour,3)
        self.assertEqual(datetime.fromtimestamp(nxt,m.timezone.utc).hour,19)
    def test_busy_does_not_advance_cursor(self):
        s=self.save();m.JOBS.append(job())
        with patch.object(m,"make_job") as create:
            self.assertIsNone(m.scheduler_tick(s["next"]))
            create.assert_not_called()
        self.assertEqual(m.load_sched()["rotation_index"],0)
    def test_bad_input_does_not_overwrite_plan(self):
        s=self.save();before=Path(m.SCF).read_text(encoding="utf-8")
        for d in ({"time":"24:00"},{"workers":20},{"cats":"流行"},{"target":-1},{"mode":"bad"}):
            self.assertEqual(self.c.post("/api/schedule",json=d).status_code,400)
        self.assertEqual(Path(m.SCF).read_text(encoding="utf-8"),before)
    def test_running_target_edit_and_history_protection(self):
        j=job();j.update(status="running");m.JOBS.append(j)
        self.assertTrue(self.c.patch("/api/jobs/42",json={"target":100}).json["ok"])
        self.assertEqual(j["target"],100)
        self.assertEqual(self.c.patch("/api/jobs/42",json={"cats":["欧美"]}).status_code,400)
        j["status"]="done"
        self.assertEqual(self.c.patch("/api/jobs/42",json={"target":200}).status_code,409)
        self.assertEqual(j["target"],100)
    def test_legacy_plan_migrates_clock_preserving_settings(self):
        legacy=dict(enabled=True,cats=["华语经典"],hour=15,minute=45,per=6,workers=2,target=100,next=1)
        Path(m.SCF).write_text(json.dumps(legacy))
        s=m.load_sched()
        self.assertEqual(s["clock_timezone"],"Asia/Shanghai")
        self.assertEqual(s["target"],100)
        self.assertEqual(s["cats"],["华语经典"])
        self.assertGreater(s["next"],1)
    def test_weekly_and_monthly_preview_moves_forward(self):
        for freq in ("weekly","monthly"):
            s=self.save(freq=freq)
            stamps=[x["time"] for x in s["preview"]]
            self.assertEqual(len(set(stamps)),3)
    def test_empty_selection_rejected_when_enabled(self):
        self.assertEqual(self.c.post("/api/schedule",json={"enabled":True,"cats":[]}).status_code,400)
