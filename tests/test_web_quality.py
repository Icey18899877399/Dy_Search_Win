import hashlib,json,tempfile,unittest
from pathlib import Path
from importlib.util import find_spec

class WebQualityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
    def fixture(self):
        root=self.root;src=root/'artifacts/source';src.mkdir(parents=True)
        (src/'manifest.json').write_text('{"files":{}}',encoding='utf-8')
        folder=root/'artifacts/quality';folder.mkdir()
        report={'status':'completed_diagnostics','tasks':[],'requested_tasks':0,'official_resolved_tasks':0,'metrics':{},'label_protocol':'official_api_resolved_binary_payout_after_cutoff'}
        plan={'source_experiment':str(src),'source_manifest_sha256':self.sha(src/'manifest.json'),'prediction_files':{}}
        for name,data in [('report.json',report),('evaluation-plan.json',plan)]:
            (folder/name).write_text(json.dumps(data),encoding='utf-8')
        (folder/'index.html').write_text('<p>saved report</p>',encoding='utf-8')
        manifest={'artifact_type':'quality_evaluation','files':{p.name:self.sha(p) for p in folder.iterdir()}}
        (folder/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
        return folder,src
    def sha(self,p):return hashlib.sha256(p.read_bytes()).hexdigest()
    def module(self):
        self.assertIsNotNone(find_spec('dynamic_retrieval.web_quality'),'Saved quality adapter must exist')
        from dynamic_retrieval.web_quality import QualityCatalog
        return QualityCatalog
    def test_saved_report_with_zero_denominator_is_not_a_score(self):
        self.fixture();c=self.module()(self.root);rows=c.list_reports()
        self.assertEqual(len(rows['reports']),1)
        row=rows['reports'][0];self.assertEqual(row['official_resolved_tasks'],0)
        self.assertEqual(c.get(row['id'])['report']['metrics'],{})
        self.assertTrue(c.report_path(row['id']).is_file())
    def test_tampered_report_is_excluded(self):
        folder,src=self.fixture();(folder/'report.json').write_text('{}')
        self.assertEqual(self.module()(self.root).list_reports()['rejected_count'],1)
    def test_changed_source_manifest_is_excluded(self):
        folder,src=self.fixture();(src/'manifest.json').write_text('{"changed":true}')
        self.assertEqual(self.module()(self.root).list_reports()['reports'],[])
    def test_unknown_id_never_resolves_to_filesystem_path(self):
        self.fixture();c=self.module()(self.root)
        with self.assertRaises(KeyError):c.get('../source/manifest.json')
    def test_verified_index_is_rechecked_before_serving(self):
        folder,src=self.fixture();c=self.module()(self.root)
        row=c.list_reports()['reports'][0];(folder/'index.html').write_text('changed')
        with self.assertRaises(ValueError):c.report_path(row['id'])
if __name__=='__main__':unittest.main()
