import os,sys,json,time,pathlib,subprocess,threading,queue,re,statistics
from bench_config import ROOT, AUDIO, OUT, CONFIGS, PYTHON, RUST, STOCK, ONNX, MODEL, LIBRARY, manifest, backend_env, generate_configs
generate_configs()
MANIFEST=manifest()
OUT.mkdir(parents=True,exist_ok=True)
# CPU runs are deliberately sequential.
def normalize(t):
 t=re.sub(r'\bmr\.', 'mister',t.lower());t=re.sub(r'\bmrs\.', 'missus',t)
 return re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?",t)
def wer(ref,hyp):
 a,b=normalize(ref),normalize(hyp);prev=list(range(len(b)+1))
 for i,x in enumerate(a,1):
  row=[i]
  for j,y in enumerate(b,1):row.append(min(row[-1]+1,prev[j]+1,prev[j-1]+(x!=y)))
  prev=row
 return {'word_errors':prev[-1],'reference_words':len(a),'wer':prev[-1]/len(a)}
class Worker:
 def __init__(self,name,cmd,env=None):
  self.log=(OUT/(name+'.stderr.log')).open('w');self.p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.log,text=True,bufsize=1,env=env);self.q=queue.Queue();self.peak=0
  def reader():
   for line in self.p.stdout:
    try:self.q.put(json.loads(line))
    except json.JSONDecodeError: self.log.write(line);self.log.flush()
   self.q.put({'error':'worker exited','exit':self.p.poll()})
  threading.Thread(target=reader,daemon=True).start()
  def monitor():
   while self.p.poll() is None:
    try:
     for line in pathlib.Path(f'/proc/{self.p.pid}/status').read_text().splitlines():
      if line.startswith('VmHWM:'):self.peak=max(self.peak,int(line.split()[1]))
    except FileNotFoundError:pass
    time.sleep(.1)
  threading.Thread(target=monitor,daemon=True).start()
  try:
   self.ready=self.q.get(timeout=300)
   if not self.ready.get('ready'):raise RuntimeError(self.ready)
  except Exception:
   self.close()
   raise
 def infer(self,file):
  start=time.perf_counter();self.p.stdin.write(json.dumps({'file':file})+'\n');self.p.stdin.flush();r=self.q.get(timeout=360);r['wall_seconds']=time.perf_counter()-start
  if not r.get('ok'):raise RuntimeError(r)
  return r
 def close(self):
  if self.p.poll() is None:
   self.p.stdin.close()
   try:self.p.wait(timeout=10)
   except subprocess.TimeoutExpired:self.p.terminate();self.p.wait(timeout=10)
  self.log.close()
def main():
 import argparse
 parser=argparse.ArgumentParser(description='Sequential warm backend screening; see benchmarks/README.md')
 parser.add_argument('jobs',nargs='*',metavar='MODEL')
 parsed=parser.parse_args()
 allowed={'tiny.en','base.en','custom-redux','vanilla-photon','parakeet-int8','moonshine-base'}
 if set(parsed.jobs)-allowed:parser.error('unknown model; choose from '+', '.join(sorted(allowed)))
 jobs=parsed.jobs or ['tiny.en','base.en','custom-redux','parakeet-int8','moonshine-base']
 for name in jobs:
  dest=OUT/(name+'.json')
  if dest.exists() and not json.loads(dest.read_text()).get('error'):
   print('Skipping completed',name,flush=True);continue
  worker=None; result={'name':name,'cases':[]}
  try:
   cmd=[PYTHON,str(ROOT/'python_worker.py'),'photon'] if name=='vanilla-photon' else ([PYTHON,str(ROOT/'python_worker.py'),'cpp',name.split('-')[2],'30'] if name.startswith('cpp-tuned-') else [RUST,str(CONFIGS/(name+'.toml'))])
   env=backend_env()
   print('START',name,flush=True);worker=Worker(name,cmd,env);result.update(worker.ready)
   worker.infer(MANIFEST[0]['file']) # one independent model warmup
   for case in MANIFEST:
    r=worker.infer(case['file']);r['backend_seconds']=r.pop('seconds');r.update({k:case[k] for k in ['id','reference']});r['audio_seconds']=case['seconds']
    r['inference_seconds']=r['wall_seconds'] # total warm request, including file read/decode
    r.update(wer(case['reference'],r['text']));result['cases'].append(r)
    print(name,case['id'],round(r['inference_seconds'],3),'WER',round(r['wer']*100,2),flush=True)
    (OUT/(name+'.partial.json')).write_text(json.dumps(result,indent=2)+'\n')
   result['sampled_peak_rss_mib']=worker.peak/1024
  except Exception as e:result['error']=str(e);print('FAILED',name,e,flush=True)
  finally:
   if worker:worker.close()
  dest.write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
