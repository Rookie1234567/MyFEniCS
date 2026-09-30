"""Independently recompute V14 record qualification without new FE actions."""
import argparse
import json
from pathlib import Path
from src.io.orthonormal_trace_reprofile import read_result
from src.io.orthonormal_trace_evidence_check import check_v14

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    records=[read_result(k)[0] for k in ('DECODER','PROFILE','VERIFY')]
    result=check_v14(*records)
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['status']=='EVIDENCE_CONSISTENT' else 1

if __name__=='__main__':
    raise SystemExit(main())
