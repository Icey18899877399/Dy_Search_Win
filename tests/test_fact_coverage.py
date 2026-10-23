import hashlib,unittest
from dynamic_retrieval.fact_coverage import inspect_document,select_passages

def task(kind='knesset'):
 return dict(question='Israeli parliament dissolved by July 31?' if kind=='knesset' else 'Will Elon Musk post 1000-1039 tweets in April 2026?',description='The sitting Knesset is dissolved between January 27 and July 31, 2026, 11:59 PM ET.' if kind=='knesset' else 'Only main feed posts, quote posts and reposts count. Replies do not count. The source is the XTracker Post Counter.',outcomes=['Yes','No'],cutoff='2026-05-31T23:59:59Z',target_elements={'subject':'malformed question'})
def doc(text,**extra):
 d=dict(id='x',event_id='e',title='Archive article',text=text,canonical_url='https://example.test/article',source_id='example',source_file='raw_news/test.json',published_at='2026-05-20T00:00:00Z',observed_at='2026-05-21T00:00:00Z',scrape_status='success',content_hash=hashlib.sha256(text.encode()).hexdigest());d.update(extra);return d
class FactCoverageTests(unittest.TestCase):
 def test_publication_and_body_observation_both_required(self):
  for field in ('published_at','observed_at'):
   d=doc('The Knesset was dissolved on May 20, 2026.',**{field:'2026-06-01T00:00:00Z'})
   out=inspect_document(task(),d);self.assertFalse(out['eligible']);self.assertEqual(out['passages'],[])
 def test_missing_timezone_never_assumed(self):
  self.assertFalse(inspect_document(task(),doc('Knesset dissolved',observed_at='2026-05-20'))['eligible'])
 def test_body_hash_mismatch_rejected(self):
  with self.assertRaisesRegex(ValueError,'hash'):inspect_document(task(),doc('Knesset dissolved',content_hash='bad'))
 def test_wrapper_is_not_article_despite_success_and_assertive_title(self):
  out=inspect_document(task(),doc('The Wayback Machine - https://web.archive.org/web/20260521070528/https://example.test/dissolved',title='Knesset was dissolved on May 20, 2026.'))
  self.assertIn('archive_wrapper_only',out['source_quality']['blockers']);self.assertEqual(out['passages'],[])
 def test_scans_past_model_head_without_copying_dates(self):
  text=('Unrelated content. '*1000)+'\nThe Knesset voted in a preliminary reading of the dissolution bill.\nThe bill still requires final approval.'
  spans=select_passages(task(),text)
  self.assertTrue(spans);self.assertTrue(any(p['start']>12000 for p in spans))
  for p in spans:self.assertEqual(p['text'],text[p['start']:p['end']])
 def test_procedural_fact_is_retained_as_neutral_not_completed(self):
  out=inspect_document(task(),doc('The Knesset voted in a preliminary reading of the dissolution bill. The bill still requires final approval.'))
  self.assertTrue(out['passages']);self.assertIn('procedural',out['passages'][0]['signals']);self.assertEqual(out['directional_candidates'],0);self.assertFalse(out['human_reviewed'])
 def test_missing_full_month_total_is_not_filled_from_task_range(self):
  out=inspect_document(task('count'),doc('Elon Musk posted a statement on X in April 2026.'))
  self.assertEqual(out['directional_candidates'],0)
  self.assertNotIn('1000',str(out['passages']))
 def test_aggregation_is_flagged_not_silently_asserted(self):
  text=('Other unrelated article. '*10000)+'The Knesset was dissolved on May 20, 2026.'
  out=inspect_document(task(),doc(text))
  self.assertIn('oversized_body_attribution_unresolved',out['source_quality']['blockers']);self.assertEqual(out['directional_candidates'],0)
 def test_bound_positive_control_and_source_spans(self):
  text='The Knesset was dissolved on May 20, 2026.'
  out=inspect_document(task(),doc(text))
  self.assertEqual(out['directional_candidates'],1)
  self.assertEqual(out['passages'][0]['text'],text)
  self.assertEqual(out['passages'][0]['v2_support'],[1,-1])
 def test_budget_and_dedup_are_explicit(self):
  text=('Knesset preliminary dissolution bill.\n'*40)
  spans=select_passages(task(),text,max_passages=2,max_chars=200)
  self.assertLessEqual(len(spans),2);self.assertLessEqual(sum(len(p['text']) for p in spans),200)
  self.assertEqual(len({p['text'] for p in spans}),len(spans))
