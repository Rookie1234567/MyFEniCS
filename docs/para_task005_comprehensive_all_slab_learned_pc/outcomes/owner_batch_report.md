# P2 Owner-batch 报告

## 合同

冻结 R4 `{0,5,9,15}` 模拟一个 owner 的四个不同 slab。输入/model/basis 均持久
驻留，只传 local RHS；rank-64 reduced coordinates 采用 stacked matrix/batched
GEMM，slab-specific encoder/decoder 保留。

| 检查 | linear | nonlinear |
|---|---:|---:|
| candidate | `A_D0_R64` | `B_D0_R64_W128_D3_GELU_SKIP` |
| arithmetic | complex128 | complex64 + float32 MLP |
| grouped vs independent error | `0.0` | `1.298e-7`（CUDA worst recorded） |
| tolerance | `1e-12` | `2e-6` |
| equivalence | PASS | PASS |
| full global vector transfer | 否 | 否 |
| per-call model reload | 否 | 否 |

## 100-repeat 结果

| backend | grouped mean | median | p95 | max | budget |
|---|---:|---:|---:|---:|---|
| linear NumPy CPU | 4.097 ms | 4.094 ms | 4.292 ms | 4.322 ms | PASS |
| linear PyTorch CPU | 4.932 ms | 4.772 ms | 6.101 ms | 6.801 ms | PASS |
| linear PyTorch CUDA | 1.361 ms | 1.345 ms | 1.515 ms | 1.655 ms | PASS |
| nonlinear PyTorch CPU | 2.931 ms | 2.928 ms | 3.090 ms | 3.279 ms | PASS |
| nonlinear PyTorch CUDA | 1.343 ms | 1.276 ms | 1.767 ms | 2.273 ms | PASS |

模型预算 7.2 ms/four-slab 全部通过。最终 11.514 ms owner end-to-end 预算没有运行，
因为 P2 storage Gate 已在进入 PETSc/MPI integration 前失败。
