# P2 Runtime backend 报告

## 结论

R4 模型纯推理显示 PyTorch CPU 与 CUDA 都具有速度可行性；100 次 owner-batch
正式重复也全部通过 7.2 ms/four-slab 模型预算。Runtime 不是本次早停原因。

## Independent screen

| family | backend | 代表范围（mean/slab） | 1.8 ms 建议线 |
|---|---:|---:|---|
| Lane A rank 64 | NumPy CPU | 0.728–1.251 ms | PASS |
| Lane B rank 64 | NumPy CPU | 1.631–1.956 ms（另有 cold/noisy outlier） | mixed |
| Lane B rank 64 | PyTorch CPU | 0.716–0.913 ms | PASS |
| Lane B rank 64 | PyTorch CUDA | 0.723–0.929 ms | PASS |

Independent CUDA 数字包含每个单样本的显式 synchronize；模型、basis 与输入均持久
驻留。没有将完整 global PETSc vector 传入 GPU。

## Owner-batch formal repeat

| family | backend | independent 4-slab mean | grouped mean | grouped p95 | grouped max | 7.2 ms |
|---|---:|---:|---:|---:|---:|---|
| linear rank 64 | NumPy CPU | 4.339 ms | 4.097 ms | 4.292 ms | 4.322 ms | PASS |
| linear rank 64 | PyTorch CPU | 4.613 ms | 4.932 ms | 6.101 ms | 6.801 ms | PASS |
| linear rank 64 | PyTorch CUDA | 1.391 ms | 1.361 ms | 1.515 ms | 1.655 ms | PASS |
| nonlinear rank 64 | PyTorch CPU | 2.881 ms | 2.931 ms | 3.090 ms | 3.279 ms | PASS |
| nonlinear rank 64 | PyTorch CUDA | 1.585 ms | 1.343 ms | 1.767 ms | 2.273 ms | PASS |

这些是 model-only 数据，不含 PETSc gather/scatter、MPI wait、periodic exact audit 或
global solver。因此只证明 P2 backend headroom，不构成 2.878 ms/slab end-to-end
成功声明。

## Backend 决策

若未来解除 storage/audit blocker，优先保留：

1. PyTorch CPU：无需 PETSc/CUDA 同进程资格化，owner grouped 约 2.93 ms；
2. PyTorch CUDA：最快，owner grouped 约 1.34 ms，但仍需 complex PETSc 同进程、
   H2D/D2H、persistent buffer 和 MPI wait 的正式资格化；
3. NumPy linear：实现最简单且确定性强，owner grouped 约 4.10 ms。

原始证据位于 ignored
`benchmarks/artifacts/cases/094/p2/owner_batch.json`。
