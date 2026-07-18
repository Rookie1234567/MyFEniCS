# Case092：WSL 工作站受控可扩展性

本 Case 保存 Task034 的轻量、可审阅资格化记录。重型 PDE 原始输出保留在
`benchmarks/artifacts/task034/`（gitignored），并由这里的 SHA-256、clean source
identity、Gate 状态和关键测量摘要绑定。

## 已登记记录

- `records/workstation_hybrid_launch_authority.json`：仅在显式
  `--task034-workstation-gate` 下生效；Task033 的 14 GiB Case091 Gate 保持不变。
- `records/p3_h3_reference_summary.json`：Phase D 的 p3/h3 finer discrete reference、
  Hybrid M160 same-degree closure、p2/h3 与 p3/h7.5/p3/h5 的 Task033 D1 同口径重排名。

旧 Task033 资源模型只能作为历史输入，不能单独授权 Task034 重型运行。所有后续候选
仍需遵守 one-heavy-case-at-a-time、assembly/factorization/full-solve 分级 Gate、
zero job swap、true residual 与 source-clean 证据要求。
