import copy
import unittest
try:
    from dynamic_retrieval import patent_evidence_v2 as p
except ImportError:
    from dynamic_retrieval import patent_evidence as p


def task(question='Israeli parliament dissolved by July 31?', cutoff='2026-06-01T23:59:59Z'):
    return dict(question=question, description='The sitting Israeli Knesset is dissolved between January 27 and July 31, 2026, 11:59 PM ET.', observed_at='2026-01-27T00:00:00Z', cutoff=cutoff, outcomes=['Yes','No'], target_elements={'subject':question,'time':'July 31'}, element_aliases={})

def cease(cutoff='2026-06-01T23:59:59Z'):
    t=task('Russia x Ukraine ceasefire by June 30, 2026?',cutoff)
    t['description']='Official ceasefire agreement: publicly announced and mutually agreed general halt in military engagement. Agreement reached before deadline qualifies even if starts afterward. Humanitarian pauses and energy infrastructure ceasefires do not qualify.'
    return t

def count(cutoff='2026-05-02T00:00:00Z'):
    t=task('Will Elon Musk post 1000-1039 tweets in April 2026?',cutoff)
    t['description']="Only main feed posts, quote posts and reposts count. Replies not on the main feed are excluded. Deleted posts count if captured. Resolution source is the 'Post Counter' at https://xtracker.polymarket.com."
    return t

def run(sentence,t=None,quote=None,extra='',ann=None,raw=None):
    return p.evaluate(raw or {'subject':'hallucination','action':'paraphrase'},t or task(),quote=sentence if quote is None else quote,text=sentence+extra,original_support=[-1,1],annotation=ann)


class PatentV2Tests(unittest.TestCase):
    def test_task_contract_isolated_and_year_source(self):
        t=task(); old=copy.deepcopy(t); e=p.effective_task(t)
        self.assertEqual(t,old)
        self.assertEqual(e['_patent_contract']['deadline']['date'],'2026-07-31')
        self.assertEqual(e['_patent_contract']['deadline']['year_source'],'description')
        self.assertEqual(e['_patent_contract']['time_interval']['start'],'2026-01-27')
        self.assertEqual(e['_patent_contract']['deadline']['timezone'],'America/New_York')
    def test_missing_year_never_wallclock(self):
        t=task();t['description']='';e=p.effective_task(t)
        self.assertEqual(e['_patent_contract']['status'],'incomplete')
    def test_future_metadata_not_used(self):
        t=task();t['observed_at']='2027-01-01T00:00:00Z'
        self.assertEqual(p.effective_task(t)['_patent_contract']['status'],'incomplete')
    def test_positive_dissolution_real_date(self):
        e,r,s,tr=run('The Knesset was dissolved on May 28, 2026.')
        self.assertEqual(s,[1,-1]);self.assertEqual(e['time'],'2026-05-28')
        self.assertEqual(r,2/3);self.assertFalse(tr['overlap']['semantic_gate_applied'])
    def test_procedural_kept_distinct(self):
        a=run('The Knesset passed a preliminary dissolution bill on May 28, 2026.')
        b=run('The Knesset was dissolved on May 28, 2026.')
        self.assertEqual(a[2],[0,0]);self.assertNotEqual(a[3]['fact_group']['key'],b[3]['fact_group']['key'])
    def test_old_cycle_future_and_missing_date_abstain(self):
        for s in ['The Knesset was dissolved on May 28, 2025.','The Knesset was dissolved on July 28, 2026.','The Knesset was dissolved.']:
            with self.subTest(s=s):self.assertEqual(run(s)[2],[0,0])
    def test_annotation_other_cycle_is_not_overwritten(self):
        self.assertEqual(run('The Knesset was dissolved on May 28, 2026.',ann={'time_scope':'historical_other_cycle'})[2],[0,0])
    def test_not_yet_future_deadline_neutral(self):
        self.assertEqual(run('The Knesset had not been dissolved as of May 28, 2026.')[2],[0,0])
    def test_explicit_no_after_deadline(self):
        self.assertEqual(run('The Knesset had not been dissolved by July 31, 2026.',task(cutoff='2026-08-02T00:00:00Z'))[2],[-1,1])
    def test_later_dissolution_does_not_prove_no(self):
        self.assertEqual(run('The Knesset was dissolved on August 1, 2026.',task(cutoff='2026-08-02T00:00:00Z'))[2],[0,0])
    def test_false_prefix_full_sentence(self):
        s='It is false that the Knesset was dissolved on May 28, 2026.'
        self.assertEqual(run(s,quote='the Knesset was dissolved on May 28, 2026.')[2],[0,0])
    def test_matching_denial_elsewhere(self):
        self.assertEqual(run('The Knesset was dissolved on May 28, 2026.',extra=' Officials denied the claim that the Knesset was dissolved on May 28, 2026.')[2],[0,0])
    def test_unrelated_denial_elsewhere(self):
        self.assertEqual(run('The Knesset was dissolved on May 28, 2026.',extra=' Officials denied that the unrelated tax bill had passed.')[2],[1,-1])
    def test_unrelated_denial_same_sentence(self):
        self.assertEqual(run('The Knesset was dissolved on May 28, 2026.; officials denied the unrelated tax bill.')[2],[1,-1])
    def test_quote_paraphrase_rejected(self):
        self.assertEqual(run('The Knesset was dissolved on May 28, 2026.',quote='Israeli parliament ended on May 28, 2026.')[2],[0,0])
    def test_no_cross_sentence_frankenstein(self):
        e,_,s,_=run('The Knesset discussed a tax bill. Parliament in France was dissolved on May 28, 2026.',quote='The Knesset discussed a tax bill.',raw={'subject':'Knesset','action':'dissolved','time':'May 28, 2026'})
        self.assertNotEqual(e.get('action'),'dissolve');self.assertEqual(s,[0,0])
    def test_date_distinguishes_exact_fact(self):
        self.assertNotEqual(run('The Knesset was dissolved on May 27, 2026.')[3]['fact_group']['key'],run('The Knesset was dissolved on May 28, 2026.')[3]['fact_group']['key'])
    def test_ceasefire_agreement_before_effective_date(self):
        s='Russia and Ukraine publicly announced a mutually agreed general ceasefire agreement on May 28, 2026, effective July 2, 2026.'
        e,_,support,_=run(s,cease());self.assertEqual(support,[1,-1]);self.assertEqual(e['time'],'2026-05-28')
    def test_ceasefire_talks_proposals_partial_wrong_parties(self):
        for s in ['Russia and Ukraine proposed a ceasefire on May 28, 2026.','Russia and Ukraine held ceasefire talks on May 28, 2026.','Russia and Ukraine publicly announced a mutually agreed humanitarian ceasefire on May 28, 2026.','Russia and Iran publicly announced a mutually agreed general ceasefire on May 28, 2026.']:
            with self.subTest(s=s):self.assertEqual(run(s,cease())[2],[0,0])
    def test_ceasefire_unilateral_neutral(self):
        self.assertEqual(run('Russia announced a ceasefire with Ukraine on May 28, 2026.',cease())[2],[0,0])
    def test_ceasefire_negative_requires_elapsed_deadline(self):
        s='Russia and Ukraine had not reached any official ceasefire agreement by June 30, 2026.'
        self.assertEqual(run(s,cease())[2],[0,0]);self.assertEqual(run(s,cease('2026-07-02T00:00:00Z'))[2],[-1,1])
    def test_ceasefire_generic_participants(self):
        t=cease();t['question']='Armenia x Azerbaijan ceasefire by June 30, 2026?'
        self.assertEqual(run('Armenia and Azerbaijan publicly announced a mutually agreed general ceasefire on May 28, 2026.',t)[2],[1,-1])
    def test_count_closed_period_bounds_and_exact_keys(self):
        rows=[]
        for n,expect in [(999,[-1,1]),(1000,[1,-1]),(1010,[1,-1]),(1039,[1,-1]),(1040,[-1,1])]:
            row=run(f"XTracker's final Post Counter for Elon Musk for the entire month of April 2026 was {n} posts.",count());rows.append(row)
            self.assertEqual(row[2],expect)
        self.assertEqual(len({tuple(r[3]['fact_group']['key']) for r in rows}),5)
    def test_count_daily_incomplete_forecast_metric_unverified(self):
        for s in ['Elon Musk posted 1010 tweets in April 2026.','Elon Musk posted 1010 tweets on April 15, 2026.','XTracker projected a final Post Counter of 1010 posts for Elon Musk for the entire month of April 2026.',"XTracker's Post Counter for Elon Musk for April 2026 so far was 1010 posts."]:
            with self.subTest(s=s):self.assertEqual(run(s,count())[2],[0,0])
    def test_count_incomplete_month_even_final_claim(self):
        self.assertEqual(run("XTracker's final Post Counter for Elon Musk for the entire month of April 2026 was 1010 posts.",count('2026-04-30T23:59:59Z'))[2],[0,0])
    def test_count_generic_publisher_and_other_month(self):
        t=count();t['question']='Will Alice Smith post 10-19 tweets in May 2027?';t['cutoff']='2027-06-02T00:00:00Z'
        self.assertEqual(run("XTracker's final Post Counter for Alice Smith for the entire month of May 2027 was 12 posts.",t)[2],[1,-1])
    def test_hypothetical_and_negated_count_neutral(self):
        for prefix in ['It is false that ', 'If ', 'It is predicted that ']:
            self.assertEqual(run(prefix+"XTracker's final Post Counter for Elon Musk for the entire month of April 2026 was 1010 posts.",count())[2],[0,0])
    def test_fallback_election_contract(self):
        t=task('Will Alice win the presidential election in 2026?');t['target_elements']={'subject':'Alice','action':'win','object':'presidential election','time':'2026'};t['element_aliases']={'action':['won']}
        e,r,s,tr=run('Alice won the presidential election in 2026.',t,raw={'subject':'Alice','action':'won','object':'presidential election','time':'2026'})
        self.assertEqual(s,[1,-1]);self.assertTrue(tr['structured_contract']['fallback_v1'])

if __name__=='__main__':unittest.main()

class PatentV2AdditionalTests(unittest.TestCase):
    def test_negative_truth_prefix_and_false_attribution(self):
        for prefix in ['It is not true that ', 'The opposition falsely claimed that ', 'There is no evidence that ']:
            s=prefix+'the Knesset was dissolved on May 28, 2026.'
            self.assertEqual(run(s,quote='the Knesset was dissolved on May 28, 2026.')[2],[0,0])
    def test_timestamp_after_cutoff_not_truncated(self):
        self.assertEqual(run('The Knesset was dissolved on 2026-05-20T23:00:00Z.',task(cutoff='2026-05-20T12:00:00Z'))[2],[0,0])
    def test_timestamp_preserved_for_exact_identity(self):
        a=run('The Knesset was dissolved on 2026-05-20T11:00:00Z.');b=run('The Knesset was dissolved on 2026-05-20T12:00:00Z.')
        self.assertNotEqual(a[3]['fact_group']['key'],b[3]['fact_group']['key'])
    def test_unrelated_ceremony_date_not_event_time(self):
        e,_,s,_=run('The Knesset was dissolved after an opening ceremony on May 28, 2026.')
        self.assertEqual(s,[0,0]);self.assertNotIn('time',e)
    def test_ceasefire_cooccurring_parties_not_relation(self):
        s='Russia and Ukraine observed that Israel and Hamas publicly announced a mutually agreed general ceasefire on May 28, 2026.'
        self.assertEqual(run(s,cease())[2],[0,0])
    def test_count_wrong_person_in_same_sentence(self):
        s="Elon Musk commented that XTracker's final Post Counter for Alice Smith for the entire month of April 2026 was 1010 posts."
        self.assertEqual(run(s,count())[2],[0,0])
    def test_count_explicit_incompatible_metric(self):
        s="XTracker's final Post Counter for Elon Musk for the entire month of April 2026 was 1010 posts including all replies."
        self.assertEqual(run(s,count())[2],[0,0])

class PatentV2IdentityTests(unittest.TestCase):
    def test_actual_ceasefire_parties_survive_normalization(self):
        a=run('Russia and Ukraine publicly announced a mutually agreed general ceasefire on May 28, 2026.',cease())
        b=run('Russia and Ukraine welcomed the news that Armenia and Azerbaijan publicly announced a mutually agreed general ceasefire on May 28, 2026.',cease())
        self.assertNotEqual(a[3]['fact_group']['key'],b[3]['fact_group']['key'])
        self.assertEqual(b[0].get('subject'),'armenia');self.assertEqual(b[0].get('object'),'azerbaijan')
    def test_actual_count_publisher_survives_normalization(self):
        a=run("XTracker's final Post Counter for Elon Musk for the entire month of April 2026 was 1010 posts.",count())
        b=run("Elon Musk said XTracker's final Post Counter for Alice Smith for the entire month of April 2026 was 1010 posts.",count())
        self.assertNotEqual(a[3]['fact_group']['key'],b[3]['fact_group']['key'])
        self.assertEqual(b[0].get('subject'),'alice smith')

class PatentV2FinalSafetyTests(unittest.TestCase):
    def test_negated_final_count_is_not_actual_count(self):
        s="XTracker's final Post Counter for Elon Musk for the entire month of April 2026 was not 1010 posts."
        self.assertEqual(run(s,count())[2],[0,0])
    def test_negative_ceasefire_parties_not_incidental(self):
        s='Russia and Ukraine reported that Armenia and Azerbaijan had not reached any official ceasefire agreement by June 30, 2026.'
        self.assertEqual(run(s,cease('2026-07-02T00:00:00Z'))[2],[0,0])

class PatentV2PublisherBindingTests(unittest.TestCase):
    def test_ordinary_actual_publisher_is_retained(self):
        e,r,s,tr=run('Elon Musk posted a message on April 12, 2026.',count())
        self.assertEqual(e.get('subject'),'elon musk');self.assertEqual(e.get('action'),'post')
        self.assertEqual(e.get('time'),'2026-04-12');self.assertEqual(r,0.5);self.assertEqual(s,[0,0])
    def test_post_noun_is_not_posting_action(self):
        e,r,s,tr=run('Elon Musk testified about tweets during a trial.',count())
        self.assertNotEqual(e.get('action'),'post');self.assertLess(r,0.5)
