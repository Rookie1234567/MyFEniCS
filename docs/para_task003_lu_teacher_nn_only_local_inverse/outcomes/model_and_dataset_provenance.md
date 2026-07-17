# 数据与模型 provenance

| capture | role | count | stride | operator fingerprint |
|---|---|---:|---:|---|
| A | train | 512 | 5 | `0fe7e9f597345f6a10bd924ebc43e15198815e151654173c0659d7dbf0306784` |
| B | validation | 128 | 13 | same exact fingerprint |
| C | holdout/active-like | 64 | 17 | same exact fingerprint |

所有 sample 文件只包含 `rhs` 与 `apply_index`，不包含 ILU output、ILU residual、local correction 或当前 PC output。Teacher dataset schema 为 `myfenics.lu_teacher_raw_local_inverse.dataset.v1`；labels 全部由同一个 COLAMD sparse-LU factor 解出。`samples.npz` SHA-256 为 `54611f42318def54bde915769515b27170464f660df33664523a9dc5029eed3e`。

模型训练为 `not_run_by_gate`，因此没有 checkpoint、GPU training time 或模型泛化声明。重型来源位于 `benchmarks/artifacts/cases/092/` 并保持 Git ignored。

数据集 manifest 同时固定三份 capture solver record 的相对路径、文件 SHA-256、`commit_sha=7e52ebac416463e1e90bd93050ea148a155a025e`、分支、dirty 标志和 case 名。三份 record 均来自目标分支并标记 `git_dirty=true`、`tracked_source_dirty=true`；因此它们足以支持本任务的 research-negative Gate，但不冒充 clean-final-HEAD canonical performance evidence。
