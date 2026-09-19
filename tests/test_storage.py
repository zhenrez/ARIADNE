import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ariadne
from ariadne_core.acquisition import acquire, queue_manifest
from ariadne_core.engine import Warden
from ariadne_core.storage import (
    evict_source,
    load_policy,
    save_policy,
    set_pin,
    sync_source_storage,
)


class StorageGovernanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        mapping=dict(
            ROOT=self.root,
            DB_DIR=self.root/'db',
            DB_PATH=self.root/'db/ariadne.sqlite',
            INBOX_DIR=self.root/'inbox',
            CUSTODY_DIR=self.root/'custody',
            ARTIFACTS_DIR=self.root/'artifacts',
            CONFIG_DIR=self.root/'config',
            TORCH_CONFIG=self.root/'config/torches.json',
            REPORT_PATH=self.root/'artifacts/latest_report.html',
        )
        self.patches=[patch.object(ariadne,k,v) for k,v in mapping.items()]
        for item in self.patches:item.start()
        ariadne.ensure_dirs()
        ariadne.TORCH_CONFIG.write_text('[]',encoding='utf-8')
        ariadne.init_db()
        save_policy(self.root,{
            'mode':'metadata_first',
            'local_budget_bytes':64*1024*1024,
            'free_space_reserve_bytes':0,
            'metadata_fetch_limit_bytes':2*1024*1024,
            'processing_overhead_factor':3,
            'auto_evict_reacquirable_text_originals':True,
        })
        self.con=ariadne.connect()
        self.w=Warden(self.con,self.root,dict(multiscale_enabled=False))
        self.con.commit()

    def tearDown(self):
        self.con.close()
        for item in reversed(self.patches):item.stop()
        self.temp.cleanup()

    @staticmethod
    def fixture(url):
        return 'FETCHED',b'72 -> 70 + 2 active\n',dict(
            url=url,headers={'content-type':'text/plain'}
        )

    def test_network_acquisition_has_no_second_staging_copy(self):
        queue_manifest(self.con,'https://example.org/source')
        acquire(self.con,self.root,1,fetcher=self.fixture)
        source=self.con.execute('SELECT source_id,custody_path FROM sources').fetchone()
        self.assertTrue((self.root/source['custody_path']).is_file())
        staging=self.root/'inbox/.staging'
        self.assertFalse(staging.exists() and any(p.is_file() for p in staging.rglob('*')))

    def test_metadata_first_releases_reacquirable_original_after_indexing(self):
        queue_manifest(self.con,'https://example.org/source')
        acquire(self.con,self.root,1,fetcher=self.fixture)
        source=self.con.execute('SELECT source_id,custody_path FROM sources').fetchone()
        self.w.compile();self.con.commit()
        state=self.con.execute('SELECT state,reacquirable FROM source_storage WHERE source_id=?',(source['source_id'],)).fetchone()
        self.assertEqual(('EVICTED',1),tuple(state))
        self.assertFalse((self.root/source['custody_path']).exists())
        self.assertIn('72','\n'.join(r[0] for r in self.con.execute(
            'SELECT text FROM passages WHERE source_id=?',(source['source_id'],)
        )))

    def test_reacquisition_restores_same_custody_identity(self):
        queue_manifest(self.con,'https://example.org/source')
        acquire(self.con,self.root,1,fetcher=self.fixture)
        source=self.con.execute('SELECT source_id,custody_path FROM sources').fetchone()
        self.w.compile();self.con.commit()
        self.con.execute("UPDATE acquisition_jobs SET status='QUEUED',attempts=0,next_attempt=0 WHERE source_id=?",(source['source_id'],))
        acquire(self.con,self.root,1,fetcher=self.fixture)
        self.assertTrue((self.root/source['custody_path']).is_file())
        self.assertEqual('PRESENT',self.con.execute(
            'SELECT state FROM source_storage WHERE source_id=?',(source['source_id'],)
        ).fetchone()[0])
        self.assertEqual(1,self.con.execute('SELECT COUNT(*) FROM sources').fetchone()[0])

    def test_local_user_original_is_not_silently_evictable(self):
        path=self.root/'inbox/user-note.txt';path.write_text('unique local evidence',encoding='utf-8')
        sid,_,_=ariadne.register_source(path,move_into_custody=True,reacquirable=False)
        self.w.compile();self.con.commit()
        self.assertEqual(0,self.con.execute(
            'SELECT reacquirable FROM source_storage WHERE source_id=?',(sid,)
        ).fetchone()[0])
        with self.assertRaisesRegex(ValueError,'not safely reacquirable'):
            evict_source(self.con,self.root,sid)

    def test_pin_blocks_release(self):
        queue_manifest(self.con,'https://example.org/source')
        acquire(self.con,self.root,1,fetcher=self.fixture)
        sid=self.con.execute('SELECT source_id FROM sources').fetchone()[0]
        set_pin(self.con,sid,True)
        with self.assertRaisesRegex(ValueError,'pinned'):
            evict_source(self.con,self.root,sid)

    def test_zero_budget_defers_without_fetching(self):
        save_policy(self.root,{'local_budget_bytes':0,'free_space_reserve_bytes':0})
        queue_manifest(self.con,'https://example.org/deferred')
        called=[]
        def should_not_fetch(url):
            called.append(url)
            return self.fixture(url)
        acquire(self.con,self.root,1,fetcher=should_not_fetch)
        self.assertEqual([],called)
        self.assertEqual('STORAGE_DEFERRED',self.con.execute(
            'SELECT status FROM acquisition_jobs WHERE url=?',('https://example.org/deferred',)
        ).fetchone()[0])

    def test_storage_status_read_does_not_append_history_when_unchanged(self):
        path=self.root/'outside.txt';path.write_text('evidence',encoding='utf-8')
        ariadne.register_source(path)
        sync_source_storage(self.con,self.root);self.con.commit()
        before=self.con.execute('SELECT COUNT(*) FROM state_versions').fetchone()[0]
        sync_source_storage(self.con,self.root);self.con.commit()
        after=self.con.execute('SELECT COUNT(*) FROM state_versions').fetchone()[0]
        self.assertEqual(before,after)

    def test_default_policy_is_conservative(self):
        p=load_policy(self.root)
        self.assertEqual('metadata_first',p['mode'])
        self.assertLessEqual(p['local_budget_bytes'],64*1024*1024)


if __name__=='__main__':
    unittest.main()
