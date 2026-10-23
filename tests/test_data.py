import importlib
import json
import pathlib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch


class DataStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.archive = self.root / 'archive'
        self.archive.mkdir()
        self.db = self.root / 'index.sqlite'

    def tearDown(self):
        self.temp.cleanup()

    def module(self):
        try:
            return importlib.import_module('dynamic_retrieval.data.store')
        except ModuleNotFoundError:
            self.fail('Missing data adapter: implement build_index and Store')

    def write(self, name, data):
        p = self.archive / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data), encoding='utf-8')

    def batch(self, when, article=None, full=True, question='Will A win?', event='e1', market='m1'):
        m = {'market_id': market, 'question': question}
        if full:
            m.update(description='Resolves Yes if A wins.', outcomes=['Yes', 'No'], closed=True,
                     outcome_prices=['0', '1'], resolved_outcome='No')
        e = {'event_id': event, 'markets': [m]}
        x = {'events': [e]}
        x['collected_at' if full else 'scraped_at'] = when
        if article is not None:
            e['articles'] = article if isinstance(article, list) else [article]
            x['scraped_at'] = when
        return x

    def article(self, text='old body', published='2026-01-01T00:00:00Z', **kwargs):
        return dict(url='https://EXAMPLE.com/story?id=1&utm_source=x#part', source='Reuters',
                    provider='newsapi', title='A wins', published_at=published,
                    full_text=text, scrape_status='success', **kwargs)

    def test_adapter_api_exists(self):
        m = self.module()
        self.assertTrue(callable(m.build_index))
        self.assertTrue(callable(m.Store))

    def test_mixed_directories_cutoff_versions_and_label_isolation(self):
        self.write('raw_news/full.json', self.batch('2026-01-02T00:00:00Z', self.article()))
        self.write('market/partial.json', self.batch('2026-01-03T00:00:00Z', self.article('new body'), False, 'Changed partial'))
        self.write('market/future.json', self.batch('2026-01-05T00:00:00Z', self.article('future body'), True, 'Future full'))
        self.write('raw_news/failure.json', self.batch('2026-01-04T00:00:00Z', self.article(''), False))
        self.write('labels.json', {'recorded_at': '2026-01-06T00:00:00Z', 'resolved_markets': [
            {'market_id': 'm1', 'event_id': 'e1', 'question': 'Leaky', 'resolved_outcome': 'No',
             'resolve_type': 'price_collapsed', 'final_prices': [0,1]}]})
        m = self.module(); audit = m.build_index(self.archive, self.db)
        with m.Store(self.db) as s:
            tasks = s.tasks('2026-01-04T12:00:00Z')
            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0]['question'], 'Will A win?')
            self.assertEqual(tasks[0]['observed_at'], '2026-01-02T00:00:00.000000Z')
            for key in ('closed','outcome_prices','resolved_outcome','final_prices'):
                self.assertNotIn(key, tasks[0])
            docs = s.documents('e1','2026-01-04T12:00:00Z')
            self.assertEqual([d['text'] for d in docs], ['new body'])
            self.assertEqual(docs[0]['canonical_url'], 'https://example.com/story?id=1')
            self.assertEqual(docs[0]['source_id'], 'publisher:reuters')
            self.assertEqual(docs[0]['provider'], 'newsapi')
            self.assertEqual(len(s.labels('m1')), 1)
            self.assertTrue(s.labels('m1')[0]['is_proxy'])
        self.assertEqual(audit['counts']['documents'],4)
        self.assertEqual(len(audit['source_manifest']),5)

    def test_article_fallback_and_bad_records_are_explicit(self):
        good=self.article()
        missing=self.article(); del missing['published_at']
        self.write('market/articles.json',self.batch('2026-01-02T08:00:00+08:00', [good,missing,self.article(published='bad'),self.article(published='2027-01-01T00:00:00Z')],False))
        (self.archive/'broken.json').write_text('{',encoding='utf-8')
        self.write('odd.json', [1,'unexpected'])
        m=self.module(); audit=m.build_index(self.archive,self.db)
        with m.Store(self.db) as s:
            task=s.tasks('2026-01-03T00:00:00Z')[0]
            self.assertEqual(task['metadata_quality'],'partial_inferred_binary')
            self.assertEqual(task['outcomes'],['Yes','No'])
            self.assertEqual(len(s.documents('e1','2026-01-03T00:00:00Z')),1)
            with self.assertRaises(ValueError): s.tasks('not-a-date')
        self.assertEqual(audit['counts']['parse_errors'],1)
        self.assertEqual(audit['counts']['missing_published_at'],1)
        self.assertEqual(audit['counts']['invalid_published_at'],1)
        self.assertGreaterEqual(audit['counts']['unrecognized_files'],1)
        self.assertTrue((self.db.parent/'audit.json').exists())

    def test_idempotence_deduplication_and_output_safety(self):
        x=self.batch('2026-01-02T00:00:00Z',self.article())
        self.write('market/a.json',x);self.write('raw_news/b.json',x)
        m=self.module(); a=m.build_index(self.archive,self.db)
        with m.Store(self.db) as s: first=s.documents('e1','2026-01-03T00:00:00Z')
        b=m.build_index(self.archive,self.db)
        with m.Store(self.db) as s: self.assertEqual(first,s.documents('e1','2026-01-03T00:00:00Z'))
        self.assertEqual(a['counts']['documents'],1)
        self.assertEqual(b['counts']['documents'],1)
        other=self.root/'other.sqlite'
        c=sqlite3.connect(other);c.execute('create table unrelated(x)');c.close()
        with self.assertRaises(ValueError):m.build_index(self.archive,other)
        with self.assertRaises(ValueError):m.build_index(self.archive,self.archive/'bad.sqlite')

    def test_full_metadata_at_cutoff_and_published_time_gate(self):
        self.write('raw_news/first.json',self.batch('2026-01-02T00:00:00Z',self.article(),False))
        self.write('market/later.json',self.batch('2026-01-04T00:00:00Z',self.article('future publication',published='2026-01-06T00:00:00Z'),True,'Full question'))
        self.write('market/last.json',self.batch('2026-01-05T00:00:00Z',None,True,'Latest question'))
        m=self.module();m.build_index(self.archive,self.db)
        with m.Store(self.db) as s:
            self.assertEqual(s.tasks('2026-01-03T00:00:00Z')[0]['metadata_quality'],'partial_inferred_binary')
            self.assertEqual(s.tasks('2026-01-04T12:00:00Z')[0]['question'],'Full question')
            self.assertEqual(s.tasks('2026-01-05T12:00:00Z')[0]['question'],'Latest question')
            self.assertEqual(s.documents('e1','2026-01-05T12:00:00Z')[0]['text'],'old body')

    def test_unreadable_source_file_is_audited_without_losing_other_files(self):
        self.write('good.json',self.batch('2026-01-02T00:00:00Z',self.article()))
        self.write('blocked.json',{})
        m=self.module()
        original=pathlib.Path.open
        def restricted(path,*args,**kwargs):
            if path.name=='blocked.json': raise PermissionError('fixture read denied')
            return original(path,*args,**kwargs)
        with patch.object(pathlib.Path,'open',restricted):
            audit=m.build_index(self.archive,self.db)
        self.assertEqual(audit['counts']['read_errors'],1)
        self.assertEqual(audit['source_read_failures'],1)
        self.assertEqual(audit['coverage_status'],'partial_source_read')
        self.assertEqual(audit['counts']['documents'],1)
        self.assertEqual(next(x for x in audit['source_manifest'] if x['path']=='blocked.json')['schema'],'read_error')

    def test_known_nonbinary_metadata_cannot_be_overridden_by_inferred_binary(self):
        x=self.batch('2026-01-02T00:00:00Z',None,True)
        x['events'][0]['markets'][0]['outcomes']=['A','B','C']
        self.write('market/full.json',x)
        self.write('raw_news/partial.json',self.batch('2026-01-03T00:00:00Z',self.article(),False))
        m=self.module();m.build_index(self.archive,self.db)
        with m.Store(self.db) as s:
            self.assertEqual(s.tasks('2026-01-04T00:00:00Z'),[])

    def test_aborted_rebuild_keeps_previous_index_and_cleans_temporary_files(self):
        self.write('good.json',self.batch('2026-01-02T00:00:00Z',self.article()))
        m=self.module();m.build_index(self.archive,self.db)
        previous=self.db.read_bytes()
        with patch.object(m,'_ingest',side_effect=RuntimeError('fixture ingest failure')):
            with self.assertRaisesRegex(RuntimeError,'fixture ingest failure'):
                m.build_index(self.archive,self.db)
        self.assertEqual(self.db.read_bytes(),previous)
        self.assertEqual(list(self.root.glob('*.building*')),[])

    def test_repeated_snapshot_bodies_are_compact_and_round_trip_exactly(self):
        text=('A body with Unicode: \u4e2d\u6587. '*40000)
        for day in range(2,7):
            self.write(f'raw_news/{day}.json',self.batch(f'2026-01-{day:02}T00:00:00Z',self.article(text),False))
        m=self.module();audit=m.build_index(self.archive,self.db)
        with m.Store(self.db) as s:
            self.assertEqual(s.documents('e1','2026-01-07T00:00:00Z')[0]['text'],text.strip())
        self.assertLess(self.db.stat().st_size,200000)
        self.assertEqual(audit['counts']['unique_bodies'],1)

    def test_reserved_audit_filename_cannot_be_the_database_output(self):
        self.write('good.json',self.batch('2026-01-02T00:00:00Z',self.article()))
        m=self.module()
        with self.assertRaises(ValueError):
            m.build_index(self.archive,self.root/'audit.json')

    def test_body_clock_cannot_fall_back_to_earlier_metadata_collection(self):
        x=self.batch('2026-01-02T00:00:00Z',self.article())
        x['scraped_at']='2026-01-05T00:00:00Z'
        self.write('mixed.json',x)
        y=self.batch('2026-01-02T00:00:00Z',self.article('missing body observation'))
        del y['scraped_at']
        self.write('missing.json',y)
        m=self.module();audit=m.build_index(self.archive,self.db)
        with m.Store(self.db) as s:
            self.assertEqual(len(s.tasks('2026-01-03T00:00:00Z')),1)
            self.assertEqual(s.documents('e1','2026-01-03T00:00:00Z'),[])
            docs=s.documents('e1','2026-01-06T00:00:00Z')
            self.assertEqual(docs[0]['text'],'old body')
            self.assertEqual(docs[0]['observed_at'],'2026-01-05T00:00:00.000000Z')
        self.assertEqual(audit['counts']['missing_document_observed_at'],1)

    def test_explicit_nonbinary_outcomes_without_description_are_excluded(self):
        x=self.batch('2026-01-02T00:00:00Z',None,False)
        x['events'][0]['markets'][0]['outcomes']=['A','B','C']
        self.write('partial.json',x)
        m=self.module();m.build_index(self.archive,self.db)
        with m.Store(self.db) as s: self.assertEqual(s.tasks('2026-01-03T00:00:00Z'),[])

    def test_partial_explicit_binary_preserves_original_outcome_order(self):
        x=self.batch('2026-01-02T00:00:00Z',None,False)
        x['events'][0]['markets'][0]['outcomes']='["No","Yes"]'
        self.write('partial.json',x)
        m=self.module();m.build_index(self.archive,self.db)
        with m.Store(self.db) as s:
            self.assertEqual(s.tasks('2026-01-03T00:00:00Z')[0]['outcomes'],['No','Yes'])
            self.assertEqual(s.tasks('2026-01-03T00:00:00Z')[0]['metadata_quality'],'partial_explicit_binary')

    def test_audit_publish_failure_preserves_old_database_and_audit(self):
        import os
        self.write('good.json',self.batch('2026-01-02T00:00:00Z',self.article()))
        m=self.module();m.build_index(self.archive,self.db)
        previous=self.db.read_bytes();audit_path=self.root/'audit.json';old_audit=audit_path.read_bytes()
        self.write('good.json',self.batch('2026-01-03T00:00:00Z',self.article('new content'),question='Changed?'))
        original=os.replace
        def denied(src,dst):
            if pathlib.Path(dst)==audit_path: raise PermissionError('fixture audit publish denied')
            return original(src,dst)
        with patch.object(m.os,'replace',denied):
            with self.assertRaisesRegex(PermissionError,'fixture audit publish denied'):
                m.build_index(self.archive,self.db)
        self.assertEqual(self.db.read_bytes(),previous)
        self.assertEqual(audit_path.read_bytes(),old_audit)
        self.assertEqual(list(self.root.glob('*.building*')),[])

    def test_database_publish_failure_restores_old_audit(self):
        import os
        self.write('good.json',self.batch('2026-01-02T00:00:00Z',self.article()))
        m=self.module();m.build_index(self.archive,self.db)
        previous=self.db.read_bytes();audit_path=self.root/'audit.json';old_audit=audit_path.read_bytes()
        self.write('good.json',self.batch('2026-01-03T00:00:00Z',self.article('new content')))
        original=os.replace
        def denied(src,dst):
            if pathlib.Path(dst)==self.db: raise PermissionError('fixture database publish denied')
            return original(src,dst)
        with patch.object(m.os,'replace',denied):
            with self.assertRaisesRegex(PermissionError,'fixture database publish denied'):
                m.build_index(self.archive,self.db)
        self.assertEqual(self.db.read_bytes(),previous)
        self.assertEqual(audit_path.read_bytes(),old_audit)


if __name__=='__main__': unittest.main()
