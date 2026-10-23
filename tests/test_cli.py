import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from dynamic_retrieval.report import render_report
from dynamic_retrieval.demo import demo_result
from dynamic_retrieval.evaluation import summarize_comparison
from dynamic_retrieval import cli


class CLITests(unittest.TestCase):
    def test_cli_outputs_unicode_as_utf8_under_legacy_windows_encoding(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'report-\u02b9-\U0001f4ca'
            env=dict(os.environ,PYTHONIOENCODING='gbk')
            p=subprocess.run([sys.executable,'-m','dynamic_retrieval','demo','--output',str(target)],
                             capture_output=True,env=env)
            self.assertEqual(p.returncode,0,p.stderr.decode('utf-8',errors='replace'))
            self.assertIn(str(target),p.stdout.decode('utf-8'))

    def test_demo_cli_writes_complete_json_and_safe_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=subprocess.run([sys.executable,'-m','dynamic_retrieval','demo','--output',tmp],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
            data=json.loads((Path(tmp)/'result.json').read_text(encoding='utf-8'))
            self.assertTrue(data['rounds'])
            self.assertTrue((Path(tmp)/'report.html').is_file())
            self.assertTrue((Path(tmp)/'manifest.json').is_file())
            self.assertGreater(data['result']['supporting_evidence_count'],0)

    def test_html_escapes_evidence_and_script_closing_strings(self):
        result=demo_result()
        result['task']['question']='</script><script>alert(1)</script>'
        result['evidence'][0]['title']='<img src=x onerror=alert(1)>'
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'report.html';render_report(result,target)
            html=target.read_text(encoding='utf-8')
            self.assertNotIn('<script>alert(1)',html)
            self.assertNotIn('<img src=x',html)
            self.assertIn('逐轮',html)

    def test_proxy_labels_never_yield_verified_accuracy(self):
        results={'enhanced':demo_result()}
        summary=summarize_comparison(results,[{'resolved_outcome':'Yes','resolve_type':'price_collapsed'}])
        self.assertEqual(summary['label_status'],'proxy_only')
        self.assertIsNone(summary['verified_brier'])
        self.assertIn('proxy_brier',summary['modes']['enhanced'])

    def test_contradictory_proxy_labels_are_not_scored(self):
        summary=summarize_comparison({'enhanced':demo_result()},[
            {'resolved_outcome':'Yes','resolve_type':'price_collapsed'},
            {'resolved_outcome':'No','resolve_type':'expired'}])
        self.assertEqual(summary['label_status'],'conflicting_proxies')
        self.assertIsNone(summary['modes']['enhanced']['proxy_brier'])

    def test_proxy_score_locates_yes_outcome_explicitly(self):
        result=demo_result();result['task']['outcomes']=['No','Yes']
        result['result']['probabilities']=[.8,.2]
        summary=summarize_comparison({'enhanced':result},[{'resolved_outcome':'Yes','resolve_type':'expired'}])
        self.assertAlmostEqual(summary['modes']['enhanced']['proxy_brier'],.64)

    def test_missing_database_gives_actionable_error_not_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=subprocess.run([sys.executable,'-m','dynamic_retrieval','tasks','--db',str(Path(tmp)/'missing.sqlite'),
                              '--cutoff','2026-01-01T00:00:00Z'],capture_output=True,text=True)
            self.assertEqual(p.returncode,2)
            self.assertIn('Error:',p.stderr)
            self.assertNotIn('Traceback',p.stderr)

    def test_untrusted_market_id_cannot_escape_output_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp).resolve()
            for market in ('../escaped','C:\\outside','/absolute','..','normal-123'):
                name=cli.market_directory(market)
                self.assertEqual((base/name).resolve().parent,base)
            self.assertEqual(cli.market_directory('normal-123'),'normal-123')

    def test_manifest_records_input_and_annotation_fingerprints(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=demo_result();cli.save_run(result,tmp)
            manifest=json.loads((Path(tmp)/'manifest.json').read_text())
            self.assertEqual(len(manifest['input_sha256']),64)
            self.assertEqual(len(manifest['annotation_sha256']),64)
            self.assertTrue(manifest['code_sha256'])


if __name__=='__main__':unittest.main()
