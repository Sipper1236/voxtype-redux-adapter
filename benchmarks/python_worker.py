import sys,json,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from redux_adapter import CppEngine,PhotonEngine
from bench_config import MODEL,LIBRARY
backend=sys.argv[1]
start=time.perf_counter()
engine=PhotonEngine() if backend=='photon' else CppEngine(model=MODEL,library=LIBRARY,pool_threads=int(sys.argv[2]) if len(sys.argv)>2 else 0,chunk_seconds=float(sys.argv[3]) if len(sys.argv)>3 else 0)
print(json.dumps({'ready':True,'load_seconds':time.perf_counter()-start}),flush=True)
try:
 for line in sys.stdin:
  try:
   r=json.loads(line);start=time.perf_counter();text=engine.transcribe(r['file'])
   result={'ok':True,'text':text,'seconds':time.perf_counter()-start}
  except Exception as e:result={'ok':False,'error':str(e)}
  print(json.dumps(result),flush=True)
finally:engine.close()
