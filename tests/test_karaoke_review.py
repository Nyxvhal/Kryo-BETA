"""Review-first reliability regressions; no ML mocking is an accuracy claim."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from kryonyx import karaoke_quality as q,karaoke_jobs,karaoke_worker
from test_karaoke import sample
import test_karaoke as baseline

class QualityTests(unittest.TestCase):
 def test_high_confidence_is_not_verified(self):
  d=sample();d['alignment']={'engine':'faster-whisper','model':'base','forced':False}
  for w in d['lines'][0]['words']:w['confidence']=.99
  result=q.assess(d);self.assertFalse(result['reviewed']);self.assertIn('asr_draft',result['warnings']);self.assertIn('light_model',result['warnings'])
 def test_reference_does_not_verify_timing(self):
  d=sample();d['alignment']={'engine':'stable-ts','forced':True};r=q.assess(d);self.assertFalse(r['reviewed']);self.assertTrue(r['reference_provided'])
 def test_normalized_reference_matching(self):
  self.assertTrue(q.reference_matches(sample(),'I want to STAY!'));self.assertFalse(q.reference_matches(sample(),'I want to go'))
 def test_diagnostics_repetition_and_long_words(self):
  d={'lines':[{'start':0,'end':30,'words':[{'text':'la','start':i*5,'end':i*5+4,'confidence':.2} for i in range(6)]}]}
  r=q.assess(d);self.assertIn('repetition',r['warnings']);self.assertIn('long_words',r['warnings']);self.assertEqual(r['low_confidence_words'],6)
 def test_line_splitting_preserves_every_timestamp(self):
  words=[{'word':' word'+str(i),'start':i,'end':i+.5} for i in range(24)]
  result=q.readable_segments([{'words':words}]);self.assertGreater(len(result),1);self.assertEqual([w for r in result for w in r['words']],words)
 def test_review_is_explicit(self):
  d=sample();d['quality']={'reviewed':True};self.assertEqual(q.assess(d)['status'],'reviewed')
 def test_manual_save_keeps_previous_document(self):
  with tempfile.TemporaryDirectory() as t,patch.object(karaoke_jobs,'data_dir',return_value=t):
   old=sample();karaoke_jobs.save_track('id',old);d=sample();d['lines'][0]['translation']='Updated';karaoke_jobs.save_track('id',d)
   previous=json.loads(karaoke_jobs.binding('id').with_suffix('.previous.json').read_text());self.assertEqual(previous['lines'][0]['translation'],old['lines'][0]['translation'])
 def test_reference_word_loss_fails_and_no_cached_document(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'a';p.write_bytes(b'fixture')
   with patch.object(karaoke_worker,'probe',return_value={'cuda':False,'torch_cuda':False}),patch.object(karaoke_worker,'_infer',return_value=([{'words':[{'word':'Wrong','start':0,'end':1}]}],'en',2)),patch.object(karaoke_worker,'emit'):
    with self.assertRaisesRegex(ValueError,'preserve every reference'):karaoke_worker.run_job({'audio':str(p),'cache':t,'reference':'Correct','language':'en','model':'small'})
   self.assertFalse(list(Path(t).glob('*.karaoke.json')))

class RefinementTests(unittest.TestCase):
 def run_fixture(self,hw,outputs,**options):
  with tempfile.TemporaryDirectory() as temp:
   audio=Path(temp)/'a.wav';audio.write_bytes(b'fixture')
   with patch.object(karaoke_worker,'probe',return_value=hw),patch.object(karaoke_worker,'_infer',side_effect=outputs) as infer,patch.object(karaoke_worker,'emit'):
    doc=karaoke_worker.run_job({'audio':str(audio),'cache':temp,'model':'small','language':'en','refine':True,**options})
    return doc,infer.call_count
 def test_refinement_never_certifies_the_transcript(self):
  a=[{'words':[{'word':'Hello','start':1,'end':2}]}];b=[{'words':[{'word':'Hello','start':1.1,'end':1.9}]}]
  d,n=self.run_fixture({'cuda':False,'torch_cuda':False,'stable_ts':True},[(a,'en',3),(b,'en',3)])
  self.assertEqual(n,2);self.assertFalse(d['alignment']['forced']);self.assertFalse(d['quality']['reviewed']);self.assertIn('asr_draft',d['quality']['warnings']);self.assertEqual(d['alignment']['refinement'],'applied')
 def test_reference_text_is_not_aligned_twice(self):
  a=[{'words':[{'word':'Hello','start':1,'end':2}]}]
  d,n=self.run_fixture({'cuda':False,'torch_cuda':False,'stable_ts':True},[(a,'en',3)],reference='Hello')
  self.assertEqual(n,1);self.assertTrue(d['alignment']['forced'])
 def test_refinement_word_loss_keeps_original(self):
  a=[{'words':[{'word':'Hello','start':1,'end':2}]}];b=[{'words':[{'word':'Wrong','start':1.1,'end':1.9}]}]
  d,n=self.run_fixture({'cuda':False,'torch_cuda':False,'stable_ts':True},[(a,'en',3),(b,'en',3)])
  self.assertEqual(d['lines'][0]['text'],'Hello');self.assertEqual(d['alignment']['refinement'],'failed');self.assertIn('refinement_skipped',d['quality']['warnings'])
 def test_missing_refinement_package_is_explicit(self):
  a=[{'words':[{'word':'Hello','start':1,'end':2}]}]
  d,n=self.run_fixture({'cuda':False,'torch_cuda':False,'stable_ts':False},[(a,'en',3)])
  self.assertEqual(n,1);self.assertEqual(d['alignment']['refinement'],'unavailable');self.assertIn('refinement_skipped',d['quality']['warnings'])

class ReviewAPI(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=baseline.APITests.asyncSetUp
 asyncTearDown=baseline.APITests.asyncTearDown
 async def test_default_generation_is_review_first(self):
  import aiohttp
  form=aiohttp.FormData();form.add_field('audio',b'RIFFtest',filename='a.wav',content_type='audio/wav');form.add_field('reference','Hello');form.add_field('track_id','test')
  jobs=self.client.server.app['karaoke_jobs']
  with patch.object(jobs,'submit',return_value={'id':'accepted','stage':'queued'}) as submit:
   r=await self.client.post('/api/karaoke/generate',data=form);self.assertEqual(r.status,200);req=submit.call_args.args[0];self.assertFalse(req['auto_bind']);self.assertEqual(req['model'],'small');Path(req['audio']).unlink()
