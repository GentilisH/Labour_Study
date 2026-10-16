import csv
import json
import tempfile
import unittest
from pathlib import Path
from labordb.coding import derive,migration
from labordb.io import FIELDS,write_csv,read_records
from labordb.db import ingest,connect
from labordb.stats import fisher,wilson,difference_ci,holm,stratified
from labordb.analyze import run

def synthetic():
    r={k:'' for k in FIELDS};r.update(source_record_id='SYNTHETIC-1',q1='2',q2='1',q4='1',q6='1',q12='4',q26='1',q27='1',q3='否',q7='服务业',q10='5',q11='8')
    for q in range(14,20):r[f'q{q}']='1'
    for q,n in [(21,9),(23,9),(24,12)]:
        for i in range(1,n+1):r[f'q{q}_{i}']='0'
    r['q21_9']='1';return r

class Statistics(unittest.TestCase):
    def test_fisher_reference(self):
        self.assertAlmostEqual(fisher(1,9,11,3),.0027594561852200836)
        self.assertEqual(fisher(0,10,0,20),1.)
    def test_intervals_boundaries(self):
        self.assertAlmostEqual(wilson(0,40)[1],.0876216011972866)
        self.assertEqual(wilson(0,0),(None,None))
        lo,hi=difference_ci(4,17,0,40);self.assertGreater(lo,0);self.assertLess(hi,1)
    def test_holm(self):self.assertEqual(holm([.01,.04,.03]),[.03,.06,.06])
    def test_conditional_single_stratum(self):
        # Symmetric margins make probability-ordering and distance-ordering agree.
        self.assertAlmostEqual(stratified([(1,9,9,1)])['p'],fisher(1,9,9,1))
        self.assertEqual(stratified([(1,0,0,0)])['overlap_n'],0)

class Data(unittest.TestCase):
    def test_coding_and_missing(self):
        r=synthetic();d,_,_=derive(r);self.assertEqual(d['any_violation'],0)
        r['q21_1']='1';d,_,_=derive(r);self.assertEqual(d['q21_conflict'],1);self.assertEqual(d['any_violation'],1)
        r['q21_1']='';r['q21_9']='';d,_,_=derive(r);self.assertIsNone(d['any_violation'])
        self.assertEqual(migration('否则'),'unknown');self.assertEqual(migration('否，6个月'),'local')
        self.assertEqual(migration('20年'),'unknown');self.assertEqual(migration('是，5年'),'nonlocal')
    def test_idempotency_revision_and_rollback(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'data.csv';db=Path(t)/'study.sqlite';r=synthetic();write_csv(p,[r],FIELDS)
            self.assertEqual(ingest(db,p,'wave1')['inserted'],1)
            self.assertTrue(ingest(db,p,'wave1')['duplicate_batch'])
            r['q21_9']='0';r['q21_1']='1';write_csv(p,[r],FIELDS)
            with self.assertRaises(ValueError):ingest(db,p,'wave1')
            c=connect(db)
            try:self.assertEqual(c.execute('SELECT any_violation FROM v_current').fetchone()[0],0)
            finally:c.close()
            self.assertEqual(ingest(db,p,'wave1',True)['revised'],1)
            c=connect(db)
            try:
                self.assertEqual(c.execute('SELECT count(*) FROM response_revision').fetchone()[0],2)
                self.assertEqual(c.execute('SELECT count(*) FROM v_current').fetchone()[0],1)
                self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
                self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            finally:c.close()
            r['q2']='9';write_csv(p,[r],FIELDS)
            with self.assertRaises(ValueError):ingest(db,p,'wave2')
    def test_duplicate_rows_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'data.csv';write_csv(p,[synthetic(),synthetic()],FIELDS)
            with self.assertRaises(ValueError):ingest(Path(t)/'d.sqlite',p,'wave')
    def test_rounds_are_not_silently_pooled(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'data.csv';db=Path(t)/'d.sqlite';write_csv(p,[synthetic()],FIELDS)
            ingest(db,p,'wave1');ingest(db,p,'wave2')
            with self.assertRaises(ValueError):run(db,Path(t)/'out')
            result=run(db,Path(t)/'out','wave1')
            self.assertEqual(result['n'],1)
            self.assertEqual(result['primary'][0]['n0'],0)
            self.assertIsNone(result['primary'][0]['p'])

if __name__=='__main__':unittest.main()
