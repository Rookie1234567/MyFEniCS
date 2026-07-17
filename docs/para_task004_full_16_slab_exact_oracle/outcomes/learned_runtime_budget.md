# Future learned action runtime 与 storage budget

## 目标与公式

目标 projected solve：

```text
0.8 × baseline solve
= 0.8 × 89.190254
= 71.352203 s
```

Baseline root one-level path为 `0.00909586 × 5166 = 46.989215 s`；它包含 local ILU solve、gather/scatter和组合，是“ILU local apply accumulated”的保守上界。Baseline non-local estimate为 `89.190254 - 46.989215 = 42.201039 s`。

G16 two-step critical owner exact solves累计142.176235 s；从 G16 solve减去它得到同一candidate action-count下的 non-local observed estimate 32.252320 s。因而达到20% global speedup时可留给 learned local path：

```text
71.352203 - 32.252320 = 39.099883 s
```

## Runtime 上限

| 口径 | 调用数 | 最大平均时间 |
|---|---:|---:|
| independent slab model | 13,584 calls / critical rank | 2.878 ms / slab |
| owner-batched 4 slabs | 3,396 batches | 11.514 ms / owner batch |
| synchronized all-rank critical path | 3,396 global applies | 11.514 ms / critical apply |

这些预算假设learned approximation能保持接近G16 exact two-step的566-step谱质量。若模型误差提高iteration count，实际允许时间会更小。One-step没有收敛，不为其给出“可资格化的20%预算”。

## Storage 上限

| 口径 | memory-neutral 上限 |
|---|---:|
| global model+basis+buffers | 141,220,416 B / 134.678 MiB |
| per owner rank | 35,305,104 B / 33.670 MiB |
| exact oracle factors（仅参考，不是模型） | 916,096,012 B / 873.657 MiB |

预算不等同于已实现NN性能，不包含训练成本、checkpoint泛化、GPU/CPU传输和同步开销。后续Task005必须单独实测。
