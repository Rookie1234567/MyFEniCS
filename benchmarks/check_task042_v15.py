"""Recompute frozen V15 qualification and decoder/residual norms, no new solve."""

import argparse
import json
from pathlib import Path

from src.io.local_trace_evidence_check import check_v15
from src.io.local_trace_representation import read_result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    setup=read_result('SETUP')[0];verify=read_result('VERIFY')[0];solves={}
    for name in ('LOCAL_POLY','LOCAL_NN','UNION_POLY','UNION_NN'):
        try:solves[name]=read_result(name)[0]
        except FileNotFoundError:continue
    result=check_v15(setup,solves,verify)
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['status']=='EVIDENCE_CONSISTENT' else 1


if __name__=='__main__':raise SystemExit(main())
