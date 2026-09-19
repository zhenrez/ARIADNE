import contextlib
import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ariadne
from ariadne_core.algorithms import AhoCorasick, anti_unify, minimal_unsat_core, missing_mass, osa_distance
from ariadne_core.engine import Warden
from ariadne_core.history import recover, snapshot, state_at, verify_history
from ariadne_core.report import render
from ariadne_core.store import verify_events
from ariadne_core.structure import extract


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        mapping=dict(ROOT=self.root,DB_DIR=self.root/'db',DB_PATH=self.root/'db/ariadne.sqlite',
                     INBOX_DIR=self.root/'inbox',CUSTODY_DIR=self.root/'custody',
                     ARTIFACTS_DIR=self.root/'artifacts',CONFIG_DIR=self.root/'config',
                     TORCH_CONFIG=self.root/'config/torches.json',REPORT_PATH=self.root/'artifacts/latest_report.html')
        self.patches=[patch.object(ariadne,k,v) for k,v in mapping.items()]
        for p in self.patches:p.start()
        ariadne.ensure_dirs()
        ariadne.TORCH_CONFIG.write_text(json.dumps([dict(torch_id='TORCH-JUDAH',title='Judah',state='BANKED',any_terms=['judah'],all_terms=[],min_hits=1)]))
        ariadne.init_db();self.con=ariadne.connect()
        self.w=Warden(self.con,self.root,dict(query_budget=5,candidate_limit=100,retrieval_limit=20))
        self.con.commit()

    def tearDown(self):
        self.con.close()
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def add(self,name,text):
        path=self.root/'inbox'/name;path.write_text(text,encoding='utf-8')
        sid,_,_=ariadne.register_source(path)
        return sid

    def typed(self,name,records,family=None,tradition=None):
        return self.add(name,json.dumps(dict(ariadne_schema=1,source=dict(family=family,tradition=tradition),records=records)))

    def compile(self):
        self.w.compile();self.con.commit()

    def test_custody_survives_inbox_modification(self):
        sid=self.add('a.txt','72 -> 70 + 2 active')
        (self.root/'inbox/a.txt').write_text('replaced')
        self.compile()
        text='\n'.join(r[0] for r in self.con.execute('SELECT text FROM passages WHERE source_id=? ORDER BY locator',(sid,)))
        self.assertIn('72',text)
        self.assertEqual('',self.con.execute('SELECT text FROM source_profiles WHERE source_id=?',(sid,)).fetchone()[0])

    def test_v0_rows_survive_additive_migration(self):
        self.add('a.txt','70 vs 72 unknown')
        before=[tuple(r) for r in self.con.execute('SELECT * FROM discrepancies')]
        self.compile()
        self.assertEqual(before,[tuple(r) for r in self.con.execute('SELECT * FROM discrepancies')])

    def test_duplicate_feed_does_not_duplicate_source(self):
        self.add('a.txt','same');self.add('b.txt','same');self.compile()
        self.assertEqual(1,self.con.execute('SELECT COUNT(*) FROM sources').fetchone()[0])

    def test_custody_tampering_stops_compilation(self):
        sid=self.add('a.txt','72 -> 70 + 2')
        row=self.con.execute('SELECT custody_path FROM sources WHERE source_id=?',(sid,)).fetchone()
        (self.root/row[0]).write_text('changed')
        with self.assertRaisesRegex(ValueError,'Custody'):self.w.compile()

    def test_operators_never_merge_at_same_count(self):
        self.add('a.txt','72 -> 70 + 2 active\n12 × 6 -> 72')
        self.compile()
        rows=self.con.execute("SELECT kind,signature FROM findings WHERE address='72'").fetchall()
        self.assertEqual({'PARTITION','FACTOR'},{r[0] for r in rows})
        self.assertEqual(2,len({r[1] for r in rows}))

    def test_generalized_partition_and_residual_preserved(self):
        self.add('a.txt','72 -> 70 + 2 active')
        self.add('b.txt','12 -> 10 + 2 active')
        self.compile()
        self.assertEqual(1,self.con.execute('SELECT COUNT(*) FROM rule_proposals').fetchone()[0])
        self.assertEqual(2,self.con.execute("SELECT COUNT(*) FROM findings WHERE kind='PARTITION'").fetchone()[0])

    def test_unknown_residual_function_stays_unknown(self):
        self.assertIsNone(extract('72 -> 70 + 2')[0][3]['residual_function'])

    def test_invalid_arithmetic_fails_kitchen(self):
        self.add('a.txt','72 -> 69 + 2');self.add('b.txt','12 -> 10 + 2')
        self.compile()
        self.assertEqual('FAILED_CONTROL',self.con.execute('SELECT verdict FROM challenges').fetchone()[0])

    def test_same_lineage_is_not_independent(self):
        self.typed('a.json',[dict(kind='partition',full_set=72,displayed_set=70,residual_count=2)],'copied-family','A')
        self.typed('b.json',[dict(kind='partition',full_set=12,displayed_set=10,residual_count=2)],'copied-family','B')
        self.compile()
        check=json.loads(self.con.execute('SELECT checks FROM challenges').fetchone()[0])
        self.assertEqual('FAIL_SHARED_FAMILY',check['source_independence'])

    def test_unrun_controls_are_unknown(self):
        self.add('a.txt','72 -> 70 + 2');self.add('b.txt','12 -> 10 + 2')
        self.compile()
        check=json.loads(self.con.execute('SELECT checks FROM challenges').fetchone()[0])
        self.assertEqual('UNKNOWN_NO_SAMPLING_MODEL',check['null_model'])
        self.assertEqual('UNRESOLVED',self.con.execute('SELECT verdict FROM challenges').fetchone()[0])

    def test_claim_conflict_requires_same_scope(self):
        a=dict(kind='claim',subject='council',predicate='count',value='70',scope='event1')
        self.typed('a.json',[a]);self.typed('b.json',[dict(a,value='72',scope='event2')]);self.compile()
        self.assertEqual(0,self.con.execute("SELECT COUNT(*) FROM proposals WHERE kind='SCOPED_CONFLICT'").fetchone()[0])

    def test_conflicting_environments_and_nogood_retained(self):
        a=dict(kind='claim',subject='council',predicate='count',value='70',scope='event1',exclusive=True)
        self.typed('a.json',[a]);self.typed('b.json',[dict(a,value='72')]);self.compile()
        data=json.loads(self.con.execute("SELECT data FROM proposals WHERE kind='SCOPED_CONFLICT'").fetchone()[0])
        self.assertEqual(2,len(data['environments']));self.assertEqual(1,len(data['nogoods']))

    def test_no_machine_promotion(self):