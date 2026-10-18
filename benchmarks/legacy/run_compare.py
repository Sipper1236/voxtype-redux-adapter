import pathlib, subprocess,json,time,os,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from bench_config import OUT,backend_env
out=OUT/'legacy-comparison';out.mkdir(parents=True,exist_ok=True)
binary=os.environ['VOXTYPE_LEGACY_WORKER']
meta=[]
for model in ['tiny.en','redux','base.en']:
 print('Starting',model,flush=True); peak=0;start=time.perf_counter()
 with (out/(model+'.jsonl')).open('w') as log,(out/(model+'.stderr.log')).open('w') as err:
  p=subprocess.Popen([binary,model],stdout=log,stderr=err,env=backend_env())
  while p.poll() is None:
   try:
    status=pathlib.Path(f'/proc/{p.pid}/status').read_text()
    for line in status.splitlines():
     if line.startswith('VmHWM:'): peak=max(peak,int(line.split()[1]))
   except FileNotFoundError: pass
   time.sleep(.1)
  if p.returncode:raise RuntimeError((model,p.returncode))
 meta.append({'model':model,'sampled_peak_rss_mib':peak/1024,'total_wall_seconds':time.perf_counter()-start})
 (out/'process-metrics.json').write_text(json.dumps(meta,indent=2)+'\n')
 print('Finished',model,flush=True)
