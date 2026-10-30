"""Owner's cross-tool shared-file stop entry; never performs PID lookup/signalling."""
from pathlib import Path
import argparse,json,sys
D=Path(__file__).resolve().parent;sys.path.insert(0,str(D))
from stop_request_channel_v1 import write_stop_request

def main():
    p=argparse.ArgumentParser();p.add_argument('--ready',required=True,type=Path);p.add_argument('--case',required=True)
    p.add_argument('--launch-sha256',required=True);p.add_argument('--pins-sha256',required=True);a=p.parse_args()
    print(json.dumps(write_stop_request(a.ready,a.case,a.launch_sha256,a.pins_sha256),sort_keys=True,allow_nan=False))
if __name__=='__main__':main()
