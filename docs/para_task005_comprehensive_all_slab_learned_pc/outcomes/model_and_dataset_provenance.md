# Model 与 dataset provenance

| 内容 | commit / identity |
|---|---|
| capture source | `a141c8e41527609e51dcfe35af06382f05cc3463` |
| teacher batching | `92dcc40` |
| P1 report | `d603b76` |
| PETSc ILU holdout | `90b16bb` |
| frozen P2 pool / Lane A | `88f41bb` |
| Lane B | `c51149a` |
| owner batch | `21c7401` |
| branch | `ChatGPT/20260715-para-task-neural-local-pc` |

每个 teacher dataset 保存 operator fingerprint、capture solver-record SHA-256、
samples SHA-256、split counts、LU diagnostics 与 resource counters。每个 P2 heavy
checkpoint/result 按 candidate/slab 分目录，并由 tracked candidate pool 解释配置。

P2 没有产生可部署 finalist：所有 checkpoint 都是 research-only ignored artifacts，
不得用于 production 或 ordinary default。
