import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import ariadne

class LauncherSafetyTests(unittest.TestCase):
    def test_connection_context_closes_windows_file_handle(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            mapping=dict(ROOT=root,DB_DIR=root/'db',DB_PATH=root/'db/ariadne.sqlite',INBOX_DIR=root/'inbox',CUSTODY_DIR=root/'custody',ARTIFACTS_DIR=root/'artifacts',CONFIG_DIR=root/'config',TORCH_CONFIG=root/'config/torches.json',REPORT_PATH=root/'artifacts/latest_report.html')
            patches=[patch.object(ariadne,key,value) for key,value in mapping.items()]
            for item in patches:item.start()
            try:
                ariadne.ensure_dirs();ariadne.TORCH_CONFIG.write_text('[]',encoding='utf-8');ariadne.init_db()
                with ariadne.connect() as con:
                    con.execute('CREATE TABLE IF NOT EXISTS launcher_probe(value INTEGER)');con.execute('INSERT INTO launcher_probe VALUES (1)')
                db=ariadne.DB_PATH;self.assertTrue(db.exists());db.unlink();self.assertFalse(db.exists())
            finally:
                for item in reversed(patches):item.stop()

    def test_one_click_launcher_contract_files_exist(self):
        root=Path(__file__).resolve().parents[1]
        for relative in ('START-ARIADNE.cmd','scripts/start-windows.ps1','scripts/launcher_preflight.py','requirements.txt'):
            self.assertTrue((root/relative).is_file(),relative)

    def test_closing_connection_is_real_close_not_only_commit(self):
        with tempfile.TemporaryDirectory() as temp:
            db=Path(temp)/'probe.sqlite';original=ariadne.DB_PATH;original_dir=ariadne.DB_DIR
            try:
                ariadne.DB_PATH=db;ariadne.DB_DIR=db.parent
                with ariadne.connect() as con:con.execute('CREATE TABLE probe(value INTEGER)')
                db.unlink();self.assertFalse(db.exists())
            finally:
                ariadne.DB_PATH=original;ariadne.DB_DIR=original_dir

if __name__=='__main__':unittest.main()
