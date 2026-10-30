"""Bounded stdlib integration, no PDE or scientific imports."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,time
D=Path(__file__).resolve().parent;sys.path.insert(0,str(D))
from stop_request_channel_v1 import write_stop_request,RequestIdentityError

def main():
    root=Path(sys.argv[1]).resolve();root.mkdir(parents=True,exist_ok=False)
    rows=[]
    for mode in ['normal','timeout','request','wrong_identity','stage_admit','stage_reject']:
        case='task44_supervision_control_'+mode;out=root/case;launch=root/(case+'.launch.json')
        child=[sys.executable,'-I','-B','-c','import time; time.sleep('+('0.4' if mode=='normal' else '10')+')']
        if mode in ['stage_admit','stage_reject']:
            child=[sys.executable,'-I','-B','-c',"import sys;sys.path.insert(0,"+repr(str(D))+");from stage_admission_v1 import admit;admit('control',"+('0' if mode=='stage_admit' else '10000000000')+",estimate_basis='fixed stdlib control');import time;time.sleep(.3)"]
        pins=hashlib.sha256(('fixed-stdlib-control:'+mode).encode()).hexdigest()
        argv=[sys.executable,'-I','-B',str(D/'task44_supervisor_v1.py'),'--output',str(out),'--launch',str(launch),'--pins-sha256',pins,'--case',case,'--lock',str(root/'numerical.lock'),'--seconds',('1' if mode=='timeout' else '6'),'--rss-bytes',('1073741824' if mode in ['stage_admit','stage_reject'] else '268435456'),'--',*child]
        launch.write_text(json.dumps({'case':case,'pins_sha256':pins,'supervisor_argv':argv,'command':child},sort_keys=True))
        launched=time.monotonic();p=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        if mode in ['request','wrong_identity']:
            ready=out/'control_ready.json'
            while not ready.exists():
                if p.poll() is not None or time.monotonic()-launched>3:raise RuntimeError('ready missing')
                time.sleep(.02)
            if mode=='wrong_identity':
                try:write_stop_request(ready,case,'0'*64,pins)
                except RequestIdentityError:pass
                else:raise AssertionError('wrong launch not refused')
                assert not (out/'stop_request.json').exists()
            write_stop_request(ready,case,hashlib.sha256(launch.read_bytes()).hexdigest(),pins)
        stdout,stderr=p.communicate(timeout=12)
        s=json.loads((out/'summary.json').read_text())
        expect=None if mode in ['normal','stage_admit','stage_reject'] else 'RECOVERABLE_CASE_WATCHDOG' if mode=='timeout' else 'REQUESTED_STOP'
        assert s['stop_reason']==expect and s['cleanup_verified'] and not s['remaining'] and s['resource_sample_count']>0,(mode,s)
        assert p.returncode==(0 if mode in ['normal','stage_admit'] else 4),(mode,p.returncode,stderr)
        samples=[json.loads(x) for x in (out/'resources.jsonl').read_text().splitlines()]
        assert all(x['system']['swap_used']==0 and all(y['swap']==0 for y in x['process_tree']) for x in samples)
        if mode in ['stage_admit','stage_reject']:
            stages=[json.loads(x) for x in (out/'stage_admission.jsonl').read_text().splitlines()];assert len(stages)==1 and stages[0]['passed']==(mode=='stage_admit')
        rows.append({'mode':mode,'exit_code':p.returncode,'elapsed':s['elapsed_seconds'],'summary_sha256':hashlib.sha256((out/'summary.json').read_bytes()).hexdigest(),'stop_reason':s['stop_reason'],'cleanup_verified':True,'stdout':stdout,'stderr':stderr})
    (root/'control_result.json').write_text(json.dumps({'status':'PASS_SIX_STDLIB_SUPERVISOR_CONTROLS_NOT_PDE','controls':rows},indent=2))
    print('PASS_SIX_STDLIB_SUPERVISOR_CONTROLS_NOT_PDE')

if __name__=='__main__':main()
