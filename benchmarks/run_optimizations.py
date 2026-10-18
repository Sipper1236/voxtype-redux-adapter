import sys,json,time,statistics,pathlib,wave,array
from run_suite import ROOT,AUDIO,OUT,CONFIGS,MANIFEST,Worker,wer,PYTHON,RUST,MODEL,LIBRARY,backend_env
sys.path.insert(0,str(ROOT.parent))
from redux_adapter import CppEngine
OUT.mkdir(parents=True,exist_ok=True)
import argparse
argparse.ArgumentParser(description='Sequential CPP thread/chunk sweep and Moonshine chunk comparison').parse_args()
rows=[]
for threads in [0,1,2,4]:
 engine=CppEngine(model=MODEL,library=LIBRARY,pool_threads=threads)
 try:
  engine.transcribe(MANIFEST[0]['file'])
  times=[]
  for _ in range(2):
   t=time.perf_counter();text=engine.transcribe(MANIFEST[1]['file']);times.append(time.perf_counter()-t)
  r={'pool_threads':threads,'seconds':times,'median_seconds':statistics.median(times),'text':text};r.update(wer(MANIFEST[1]['reference'],text));rows.append(r)
  print('CPP THREADS',threads,r['median_seconds'],flush=True)
 finally:engine.close()
(OUT/'cpp-thread-sweep.json').write_text(json.dumps(rows,indent=2)+'\n')
best=min(rows,key=lambda r:r['median_seconds'])['pool_threads']
for chunk_seconds in [0,30]:
 name=f'cpp-tuned-{best}-chunk{chunk_seconds}'
 worker=Worker(name,[PYTHON,str(ROOT/'python_worker.py'),'cpp',str(best),str(chunk_seconds)])
 result={'name':name,'pool_threads':best,'chunk_seconds':chunk_seconds,'cases':[],**worker.ready}
 try:
  worker.infer(MANIFEST[0]['file'])
  cases=MANIFEST if chunk_seconds==30 else [x for x in MANIFEST if x['id'] in ['clean-30s','clean-120s']]
  for case in cases:
   r=worker.infer(case['file']);r['backend_seconds']=r.pop('seconds');r.update(id=case['id'],audio_seconds=case['seconds'],reference=case['reference'],inference_seconds=r['wall_seconds']);r.update(wer(case['reference'],r['text']));result['cases'].append(r)
   print(name,case['id'],round(r['wall_seconds'],3),'WER',round(r['wer']*100,2),flush=True)
  result['sampled_peak_rss_mib']=worker.peak/1024
 finally:worker.close()
 (OUT/(name+'.json')).write_text(json.dumps(result,indent=2)+'\n')
# Test whether segmentation repairs Moonshine's observed long-input failure.
name='moonshine-chunk15';worker=Worker(name,[RUST,str(CONFIGS/'moonshine-base.toml')],env=backend_env())
result={'name':name,'cases':[],**worker.ready}
try:
 worker.infer(MANIFEST[0]['file'])
 for case in MANIFEST:
  with wave.open(case['file']) as w:pcm=array.array('h',w.readframes(w.getnframes()))
  start=0;texts=[];t=time.perf_counter()
  while start<len(pcm):
   end=min(len(pcm),start+15*16000)
   if end<len(pcm):end=min(range(max(start+16000,end-48000),end,320),key=lambda i:sum(v*v for v in pcm[i:i+320]))+160
   path=AUDIO/'chunk-tmp.wav'
   with wave.open(str(path),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(pcm[start:end].tobytes())
   texts.append(worker.infer(str(path))['text']);start=end
  elapsed=time.perf_counter()-t;text=' '.join(texts)
  r={'id':case['id'],'audio_seconds':case['seconds'],'inference_seconds':elapsed,'text':text,'reference':case['reference']};r.update(wer(case['reference'],text));result['cases'].append(r)
  print(name,case['id'],round(elapsed,3),'WER',round(r['wer']*100,2),flush=True)
 result['sampled_peak_rss_mib']=worker.peak/1024
finally:worker.close();(AUDIO/'chunk-tmp.wav').unlink(missing_ok=True)
(OUT/(name+'.json')).write_text(json.dumps(result,indent=2)+'\n')
