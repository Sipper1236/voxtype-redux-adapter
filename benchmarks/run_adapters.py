import json,os,pathlib,subprocess,sys,time,statistics
from run_suite import ROOT,OUT,CONFIGS,PYTHON,MODEL,LIBRARY,STOCK,MANIFEST,wer
import tempfile
sys.path.insert(0,str(ROOT.parent))
from redux_adapter import request
ADAPTER=ROOT.parent/'redux_adapter.py'
OUT.mkdir(parents=True,exist_ok=True)
import argparse
parser=argparse.ArgumentParser(description='Measure real stock Voxtype CLI adapter latency')
parser.add_argument('backends',nargs='*',metavar='BACKEND')
args=parser.parse_args()
if set(args.backends)-{'cpp','photon'}:parser.error('choose cpp or photon')
for backend in args.backends or ['cpp']:
 name='stock-'+backend+'-adapter';log=(OUT/(name+'.worker.log')).open('w')
 runtime=os.environ.get('XDG_RUNTIME_DIR')
 if not runtime:raise RuntimeError('XDG_RUNTIME_DIR is required for the adapter benchmark')
 socket_dir=tempfile.TemporaryDirectory(prefix=f'voxtype-redux-bench-{backend}-',dir=runtime)
 sock=str(pathlib.Path(socket_dir.name)/'worker.sock')
 python=PYTHON
 cmd=[python,str(ADAPTER),'serve','--backend',backend,'--socket',sock]
 env=os.environ.copy();env['VOXTYPE_REDUX_SOCKET']=sock
 if backend == 'cpp':
  sweep_path=OUT/'cpp-thread-sweep.json'
  sweep=json.loads(sweep_path.read_text()) if sweep_path.exists() else []
  best=min(sweep,key=lambda r:r['median_seconds'])['pool_threads'] if sweep else 4
  cmd += ['--model',str(MODEL),'--library',str(LIBRARY),'--pool-threads',str(best),'--chunk-seconds','30']
 else:
  cmd += ['--compat-model',str(MODEL)]
 worker=subprocess.Popen(cmd,stdout=log,stderr=log,env=env)
 result={'name':name,'cases':[]}
 try:
  start=time.monotonic()
  while True:
   if worker.poll() is not None:raise RuntimeError('worker failed startup; see log')
   try:result['worker_status']=request({'command':'status'},sock);break
   except (OSError,RuntimeError):
    if time.monotonic()-start>180:raise
    time.sleep(.2)
  config=CONFIGS/'adapter.toml'
  def infer(case,repeat):
   start=time.perf_counter()
   p=subprocess.run([STOCK,'-c',str(config),'transcribe',case['file']],env=env,capture_output=True,text=True,check=True,timeout=360)
   wall=time.perf_counter()-start
   (OUT/f'{name}-{case["id"]}-{repeat}.log').write_text(p.stdout+'\n'+p.stderr)
   text=p.stdout.strip().split('\n\n')[-1].strip()
   row={'id':case['id'],'audio_seconds':case['seconds'],'inference_seconds':wall,'text':text,'reference':case['reference'],'repeat':repeat};row.update(wer(case['reference'],text))
   return row
  infer(MANIFEST[0],'warmup')
  cases=MANIFEST + [c for c in MANIFEST if c['id'] in ['clean-5s','clean-30s','clean-120s']]*2
  for n,case in enumerate(cases):
   row=infer(case,n);result['cases'].append(row);print(name,case['id'],round(row['inference_seconds'],3),'WER',round(row['wer']*100,2),flush=True)
   (OUT/(name+'.partial.json')).write_text(json.dumps(result,indent=2)+'\n')
  for line in pathlib.Path(f'/proc/{worker.pid}/status').read_text().splitlines():
   if line.startswith('VmHWM:'):result['sampled_peak_rss_mib']=int(line.split()[1])/1024
 except Exception as e:result['error']=str(e);print('FAILED',name,e,flush=True)
 finally:
  worker.terminate()
  try:worker.wait(timeout=15)
  except subprocess.TimeoutExpired:worker.kill();worker.wait()
  log.close()
  socket_dir.cleanup()
 (OUT/(name+'.json')).write_text(json.dumps(result,indent=2)+'\n')
