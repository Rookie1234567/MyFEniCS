"""Read V13's frozen records and independently derive compact qualifications."""

import argparse
import json
from pathlib import Path

from src.io.tangent_head_compensation import read_result
from src.io.tangent_head_evidence_check import check_v13


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    rows=[read_result(k)[0] for k in ('TANGENT','RESPONSE','COMPENSATE','VERIFY')]
    result=check_v13(*rows)
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['status']=='EVIDENCE_CONSISTENT' else 1


if __name__=='__main__':
    raise SystemExit(main())
