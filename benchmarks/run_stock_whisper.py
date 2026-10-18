import json,time,subprocess,re
from run_suite import ROOT,OUT,CONFIGS,MANIFEST,STOCK,ONNX,wer
import argparse
argparse.ArgumentParser(description='Measure packaged Whisper commands including model loading').parse_args()
for model in ['tiny.en','base.en']:
 result={'name':'stock-whisper-'+model,'cases':[],'method':'Packaged /usr/bin/voxtype 1.1.0; each invocation loads its model. Wall times include model loading; logged inference excludes load but is first-call inference, not resident warm.'}
 for case in MANIFEST:
  start=time.perf_counter();p=subprocess.run([STOCK,'-c',str(CONFIGS/(model+'.toml')),'transcribe',case['file']],capture_output=True,text=True,check=True,timeout=180)
  wall=time.perf_counter()-start
  (OUT/f'stock-whisper-{model}-{case["id"]}.log').write_text(p.stdout+'\n'+p.stderr)
  text=p.stdout.strip().split('\n\n')[-1];matches=re.findall(r'[Tt]ranscription completed in ([0-9.]+)s',p.stdout+p.stderr)
  row={'id':case['id'],'audio_seconds':case['seconds'],'inference_seconds':wall,'logged_inference_seconds':float(matches[-1]),'text':text,'reference':case['reference']};row.update(wer(case['reference'],text));result['cases'].append(row)
  print(model,case['id'],round(wall,3),matches[-1],'WER',round(row['wer']*100,2),flush=True)
 (OUT/('stock-whisper-'+model+'.json')).write_text(json.dumps(result,indent=2)+'\n')
