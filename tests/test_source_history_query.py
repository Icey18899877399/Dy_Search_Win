import importlib.util
import sqlite3
import unittest
import zlib
from pathlib import Path
from test_source_history import TASK, BODY, WRAPPER, document

path=Path(__file__).resolve().parents[1]/'scripts/audit_source_gaps.py'
spec=importlib.util.spec_from_file_location('gap_audit_under_test',path)
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)

class SourceHistoryQueryTests(unittest.TestCase):
    def test_query_does_not_hide_failed_scrape_with_substantive_correction(self):
        with sqlite3.connect(':memory:') as con:
            con.row_factory=sqlite3.Row
            con.execute('CREATE TABLE documents (id TEXT,canonical_url TEXT,event_id TEXT,observed_at TEXT,published_at TEXT,content_hash TEXT,has_text INT,scrape_status TEXT)')
            con.execute('CREATE TABLE bodies(content_hash TEXT PRIMARY KEY,payload BLOB)')
            items=[document('old',BODY),document('correction','Correction: the vote did not occur.','2026-05-29T00:00:00Z',scrape_status='error'),document('wrapper',WRAPPER,'2026-05-30T00:00:00Z')]
            for d in items:
                con.execute('INSERT INTO documents VALUES (?,?,?,?,?,?,1,?)',tuple(d[k] for k in ('id','canonical_url','event_id','observed_at','published_at','content_hash','scrape_status')))
                con.execute('INSERT INTO bodies VALUES (?,?)',(d['content_hash'],zlib.compress(d['text'].encode())))
            docs=audit.load_visible_versions(con,TASK)
            out=audit.historical_body_candidate(TASK,docs)
            self.assertEqual(out['document']['id'],'correction')
            self.assertEqual(out['document']['scrape_status'],'error')

if __name__=='__main__':unittest.main()
