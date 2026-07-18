# P1 Borrowed exact action equivalence

## Gate 结论

`P1 = PASS`。正式 h5/MPI4 在 16/16 slabs、每 slab 4 个冻结 probes 上得到：

| 指标 | 实测 | Gate | 状态 |
|---|---:|---:|---|
| action relative error max | `6.030e-16` | `<=1e-12` | PASS |
| local rho absolute error max | `3.558e-16` | `<=1e-12` | PASS |
| row count | 64/64 | 64/64 | PASS |
| private persistent local CSR | 0 bytes | 0 bytes | PASS |
| MPI2 | 每 rank 3 passed | pass | PASS |
| MPI4 | 每 rank 2 passed | pass | PASS |
| destroy idempotence | pass | pass | PASS |
| ordinary full solve | 852 iterations、numeric/RTA pass | unchanged | PASS |

## 实现语义

每次 audit 是一个 MPI collective：

```text
owner local correction
-> existing owner-union reverse scatter
-> persistent distributed global input
-> borrowed shifted-F/global MatMult
-> existing owner-union forward scatter
-> owner slab restriction
```

只有当前 slab owner 填入 local correction，所有 rank 按相同 slab 顺序参加
MatMult。由零扩展/限制恒等式，
`restrict_I(A * lift_I(x)) = A[I,I] * x`，因此 overlap slab 不需要复制 CSR。

auditor 不拥有 action operator 或 union scatter；它只拥有两个 distributed 和两个
sequential persistent work vectors。smoother destroy 会先销毁已创建 auditor，
重复 destroy 幂等，destroy 后调用 fail closed。ordinary path 不创建 auditor，
因此不增加普通 ILU profile storage。

## 16-slab 结果

probe 覆盖 deterministic complex、`1e-8` scale + phase、三点 sparse
boundary/interior 和 alternating high-frequency correction。rho 对照还加入冻结的
小扰动，避免只验证零残差。

| slab | action error max | rho error max | mean collective audit |
|---:|---:|---:|---:|
| 0 | `5.889e-16` | `3.211e-16` | 6.283 ms |
| 1 | `5.750e-16` | `3.467e-16` | 6.269 ms |
| 2 | `5.714e-16` | `3.429e-16` | 6.259 ms |
| 3 | `5.982e-16` | `3.396e-16` | 6.266 ms |
| 4 | `5.845e-16` | `3.454e-16` | 6.209 ms |
| 5 | `5.897e-16` | `3.558e-16` | 6.255 ms |
| 6 | `5.907e-16` | `3.369e-16` | 6.280 ms |
| 7 | `5.709e-16` | `3.375e-16` | 6.095 ms |
| 8 | `5.795e-16` | `3.225e-16` | 6.085 ms |
| 9 | `5.796e-16` | `3.348e-16` | 6.128 ms |
| 10 | `5.658e-16` | `3.314e-16` | 6.160 ms |
| 11 | `5.751e-16` | `3.248e-16` | 6.181 ms |
| 12 | `6.030e-16` | `3.182e-16` | 6.139 ms |
| 13 | `5.812e-16` | `3.035e-16` | 6.338 ms |
| 14 | `5.918e-16` | `3.037e-16` | 6.159 ms |
| 15 | `5.895e-16` | `2.811e-16` | 6.120 ms |

## Storage 与 qualification-only reference

| rank | persistent work vectors | layout metadata | private CSR |
|---:|---:|---:|---:|
| 0 | 0.762 MiB | 0.068 MiB | 0 |
| 1 | 0.754 MiB | 0.068 MiB | 0 |
| 2 | 0.753 MiB | 0.068 MiB | 0 |
| 3 | 0.761 MiB | 0.068 MiB | 0 |

为证明等价性，qualification hook 一次只在 slab owner 临时加载一个 Task005
reference CSR；最大 ephemeral reference 为 12.095 MiB，用完即释放。它不是
runtime auditor 的 persistent storage，也不会进入 P2-P7 live path。

## Full-solve guard

clean implementation `0b20f2554a9cc0526efa893f941174fb81918472` 的同轮
full solve 为 852 iterations、95.026 s，三种 residual 均约 `9.980248e-7`，
R/T/A closure `-1.860e-9`，swap 0/0。外部 peak 1.613209 GiB，相对 P0
1.608242 GiB 为 `1.00309x`。

完整测试为 212 passed、12 skipped；P1 Ruff、compileall 与 diff check 通过。
重型逐 probe rows、solver record、timeline 位于
`benchmarks/artifacts/cases/095/p1_borrowed_0b20f25/` 并保持 ignored。
