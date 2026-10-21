import unittest,tempfile,subprocess,sys,shutil,sqlite3,json
from pathlib import Path
from contextlib import closing
ROOT=Path(__file__).resolve().parent.parent
class ToolsTest(unittest.TestCase):
    def test_configure_generates_secrets_without_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);(base/"scripts").mkdir()
            shutil.copy2(ROOT/"scripts/configure.py",base/"scripts/configure.py")
            shutil.copy2(ROOT/".env.example",base/".env.example")
            p=subprocess.run([sys.executable,str(base/"scripts/configure.py")],capture_output=True)
            self.assertEqual(p.returncode,0,p.stderr)
            content=(base/".env").read_text(encoding="utf-8")
            self.assertNotIn("HUB_PASSWORD=\n",content)
            self.assertTrue((base/"data/music").is_dir())
            p=subprocess.run([sys.executable,str(base/"scripts/configure.py")],capture_output=True)
            self.assertNotEqual(p.returncode,0)
            self.assertEqual(content,(base/".env").read_text(encoding="utf-8"))
    def test_migration_copies_db_and_disables_only_new_schedule(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);tasks=base/"old-tasks";engine=base/"old-engine";tasks.mkdir();engine.mkdir()
            (tasks/"schedule.json").write_text('{"enabled":true,"cats":["流行"]}',encoding="utf-8")
            with closing(sqlite3.connect(engine/"settings.db")) as db:
                db.execute("create table sample(value text)");db.execute("insert into sample values ('fixture')");db.commit()
            target=base/"new-data"
            p=subprocess.run([sys.executable,str(ROOT/"scripts/migrate_legacy.py"),"--tasks",str(tasks),"--engine",str(engine),"--destination",str(target)],capture_output=True)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertFalse(json.loads((target/"tasks/schedule.json").read_text(encoding="utf-8"))["enabled"])
            self.assertTrue(json.loads((tasks/"schedule.json").read_text(encoding="utf-8"))["enabled"])
            with closing(sqlite3.connect(target/"engine/settings.db")) as db:self.assertEqual(db.execute("select value from sample").fetchone()[0],"fixture")
