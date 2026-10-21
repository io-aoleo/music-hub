import unittest,tempfile,sqlite3,importlib.util
from pathlib import Path
from contextlib import closing
spec=importlib.util.spec_from_file_location("seed",Path(__file__).resolve().parent.parent/"scripts/seed_music_index.py")
seed=importlib.util.module_from_spec(spec);spec.loader.exec_module(seed)
class SeedIndexTest(unittest.TestCase):
    def test_seed_without_audio_decoding_and_preserve_existing_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);music=root/"music";music.mkdir();song=music/"歌手 - 歌曲.mp3";song.write_bytes(b"fixture")
            dbpath=root/"settings.db"
            with closing(sqlite3.connect(dbpath)) as db:
                db.execute("""create table local_music_index
                 (id text primary key,rel_path text,name text,artist text,album text,duration integer,
                  size integer,ext text,cover text,has_cover integer,has_lyric integer,mod_time text,scanned_at text)""")
                db.commit()
            result=seed.seed_index(dbpath,music);self.assertEqual(result["index_added"],1)
            with closing(sqlite3.connect(dbpath)) as db:
                self.assertEqual(db.execute("select name,artist from local_music_index").fetchone(),("歌曲","歌手"))
                db.execute("update local_music_index set name='准确元数据'");db.commit()
            self.assertEqual(seed.seed_index(dbpath,music)["index_added"],0)
            with closing(sqlite3.connect(dbpath)) as db:self.assertEqual(db.execute("select name from local_music_index").fetchone()[0],"准确元数据")
            self.assertEqual(song.read_bytes(),b"fixture")
