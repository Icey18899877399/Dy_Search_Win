"""Historical replay must bind dependencies to recorded code, not current code."""
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('artifact_verifier_test',ROOT/'scripts/verify_artifacts.py')
verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)

class ArtifactHistoryTests(unittest.TestCase):
    def test_archived_engine_uses_archived_dependency_and_preserves_live_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'src/dynamic_retrieval';source.mkdir(parents=True)
            archive=root/'artifacts/code-archive';archive.mkdir(parents=True)
            originals={'engine.py':'from .helper import VALUE\ndef run(): return VALUE\n',
                       'helper.py':'VALUE = 7\n', 'models.py':'class Config: pass\n'}
            manifest={'code_sha256':{}}
            for name,body in originals.items():
                data=body.encode();digest=hashlib.sha256(data).hexdigest()
                (archive/(digest+'.py')).write_bytes(data)
                (source/name).write_text('raise RuntimeError("Live code must not be imported")\n',encoding='utf-8')
                manifest['code_sha256']['src/dynamic_retrieval/'+name]=digest
            previous=verifier.ROOT
            try:
                verifier.ROOT=root
                run,_=verifier.historical_replay(manifest)
                self.assertEqual(run(),7)
                self.assertIn('Live code', (source/'engine.py').read_text())
                digest=manifest['code_sha256']['src/dynamic_retrieval/helper.py']
                (archive/(digest+'.py')).write_text('VALUE = 99\n')
                with self.assertRaises(AssertionError):verifier.historical_replay(manifest)
            finally:verifier.ROOT=previous


class ObservationArtifactHistoryTests(unittest.TestCase):
    def test_measurement_manifest_does_not_require_prediction_result(self):
        import json
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);out=root/'artifacts/observations';out.mkdir(parents=True)
            value={'empirical_calibration':False,'network_attempts':0,'label_reads':0,'source_cost_parameters_replaceable':False,'measured_calls':1}
            (out/'summary.json').write_text(json.dumps(value),encoding='utf-8')
            (out/'query-observations.jsonl').write_text(json.dumps({'backend':'local_archive','rate_limit_quota':None,'empirical_calibration':False})+'\n',encoding='utf-8')
            files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}
            manifest={'artifact_type':'phase14_local_archive_observations','files':files,'source_sha256':{}}
            self.assertTrue(hasattr(verifier,'verify_observation_manifest'),'observation manifest routing missing')
            verifier.verify_observation_manifest(out,manifest)
            value['empirical_calibration']=True
            (out/'summary.json').write_text(json.dumps(value),encoding='utf-8')
            manifest['files']['summary.json']=hashlib.sha256((out/'summary.json').read_bytes()).hexdigest()
            with self.assertRaises(AssertionError):verifier.verify_observation_manifest(out,manifest)

    def test_preserved_legacy_observation_hashes_are_checked(self):
        import json
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)
            (out/'summary.json').write_text(json.dumps({'empirical_calibration':False,'network_attempts':0,'label_reads':0,'source_cost_parameters_replaceable':False,'measured_calls':0}),encoding='utf-8')
            (out/'query-observations.jsonl').write_text('',encoding='utf-8')
            manifest={'outputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()},'input_sha256':{},'query_count':0,'empirical_calibration':False}
            self.assertTrue(hasattr(verifier,'verify_observation_manifest'),'legacy observation verification missing')
            verifier.verify_observation_manifest(out,manifest)
            (out/'query-observations.jsonl').write_text('tampered',encoding='utf-8')
            with self.assertRaises(AssertionError):verifier.verify_observation_manifest(out,manifest)

if __name__=='__main__':unittest.main()
