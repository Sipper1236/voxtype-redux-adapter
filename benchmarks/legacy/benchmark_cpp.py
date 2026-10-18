import ctypes as c, wave, array, time, json, statistics, subprocess, pathlib, resource
import os, sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from bench_config import REPO,OUT,CONFIGS,MODEL,LIBRARY,backend_env,generate_configs
generate_configs()
out = OUT/'legacy-redux';out.mkdir(parents=True,exist_ok=True)
vad=REPO/'custom-voxtype/tests/fixtures/vad'
cpp=pathlib.Path(os.environ.get('VOXTYPE_PARAKEET_SOURCE',str(REPO.parent/'parakeet.cpp')))
custom=os.environ.get('VOXTYPE_CUSTOM_BINARY',str(REPO/'custom-voxtype/target/release/voxtype'))
lib = c.CDLL(str(LIBRARY))
lib.parakeet_capi_load.argtypes=[c.c_char_p]; lib.parakeet_capi_load.restype=c.c_void_p
lib.parakeet_capi_transcribe_pcm.argtypes=[c.c_void_p,c.POINTER(c.c_float),c.c_int,c.c_int,c.c_int]; lib.parakeet_capi_transcribe_pcm.restype=c.c_void_p
lib.parakeet_capi_free_string.argtypes=[c.c_void_p]; lib.parakeet_capi_free.argtypes=[c.c_void_p]
lib.parakeet_capi_last_error.argtypes=[c.c_void_p];lib.parakeet_capi_last_error.restype=c.c_char_p
model=str(MODEL)
start=time.perf_counter(); ctx=lib.parakeet_capi_load(model.encode()); load=time.perf_counter()-start
if not ctx: raise RuntimeError('load failed')
result={'model':model,'native_load_seconds':load,'method':'Identical C API and default decoder as installed Voxtype; one warmup per fixture, five measured sequential runs; no thread override. Cold means fresh process with filesystem cache potentially warm.','warm':[],'cold_cli':[]}
fixtures=[vad/'speech_hello.wav',vad/'speech_long.wav',cpp/'tests/fixtures/speech.wav',cpp/'tests/fixtures/two_speakers.wav']
try:
 for path in fixtures:
  with wave.open(str(path)) as w:
   assert w.getnchannels()==1 and w.getsampwidth()==2 and w.getframerate()==16000
   pcm=array.array('h',w.readframes(w.getnframes())); duration=len(pcm)/16000
  samples=(c.c_float*len(pcm))(*(v/32768 for v in pcm))
  times=[];texts=[]
  for i in range(6):
   start=time.perf_counter(); ptr=lib.parakeet_capi_transcribe_pcm(ctx,samples,len(pcm),16000,0); elapsed=time.perf_counter()-start
   if not ptr: raise RuntimeError(lib.parakeet_capi_last_error(ctx))
   text=c.string_at(ptr).decode();lib.parakeet_capi_free_string(ptr)
   if i: times.append(elapsed);texts.append(text)
  row={'file':str(path),'audio_seconds':duration,'seconds':times,'median_seconds':statistics.median(times),'min_seconds':min(times),'max_seconds':max(times),'median_rtf':statistics.median(times)/duration,'speedup':duration/statistics.median(times),'transcripts':texts}
  result['warm'].append(row);print(json.dumps(row),flush=True)
finally: lib.parakeet_capi_free(ctx)
result['native_process_peak_rss_mib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
for i in range(3):
 start=time.perf_counter(); p=subprocess.run([custom,'-c',str(CONFIGS/'custom-redux.toml'),'transcribe',str(fixtures[0])],capture_output=True,text=True,check=True,env=backend_env());elapsed=time.perf_counter()-start
 result['cold_cli'].append({'wall_seconds':elapsed,'stdout':p.stdout,'stderr':p.stderr});print('cold_cli',elapsed,flush=True)
(out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
print('Saved',out/'results.json',flush=True)
