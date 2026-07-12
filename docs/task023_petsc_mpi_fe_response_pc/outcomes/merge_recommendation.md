# Merge Recommendation

| item | recommendation | reason |
|---|---|---|
| docs/outcomes | merge after review | 记录了 h=5 成功闭环和 h=2 失败边界 |
| `run_task023_petsc_mpi_fe_response_pc.py` | optional research-branch merge | runner 有价值，但仍是研究脚本 |
| production default solver | no | h=2 还没有 minimum useful residual |
| plain ASM/ILU profile | no | h=2 FieldSplit residual 0.9896，selected response residual 1.540 |
| MUMPS/BLR fallback | no default change | h=2 超时，接近直接法资源成本 |

建议：本轮不要把任何新 profile 切成 production 默认。可以保留 runner 和文档，为下一轮 real-split AMS/HX FE-response service 提供证据。
