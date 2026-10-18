import subprocess,time,json,re
from run_suite import ROOT,OUT,CONFIGS,MANIFEST,STOCK,ONNX,wer
import argparse
argparse.ArgumentParser(description='Sanity-check native packaged binaries on the 30-second clip').parse_args()
case=next(c for c in MANIFEST if c['id']=='clean-30s');rows=[]
for name,binary in [('tiny.en',STOCK),('base.en',STOCK),('parakeet-int8',ONNX),('moonshine-base',ONNX)]:
 start=time.perf_counter();p=subprocess.run([binary,'-c',str(CONFIGS/(name+'.toml')),'transcribe',case['file']],capture_output=True,text=True,timeout=180)
 (OUT/('stock-verify-'+name+'.log')).write_text(p.stdout+'\n'+p.stderr)
 matches=re.findall(r'[Tt]ranscription completed in ([0-9.]+)s',p.stdout+p.stderr)
 text=p.stdout.strip().split('\n\n')[-1]
 row={'name':'stock-verify-'+name,'id':case['id'],'audio_seconds':case['seconds'],'ok':p.returncode==0,'model':name,'binary':binary,'exit_code':p.returncode,'wall_seconds':time.perf_counter()-start,'logged_inference_seconds':float(matches[-1]) if matches else None,'text':text}
 if p.returncode==0: row.update(wer(case['reference'],text))
 rows.append(row);print(row,flush=True)
(OUT/'stock-verification.json').write_text(json.dumps(rows,indent=2)+'\n')
