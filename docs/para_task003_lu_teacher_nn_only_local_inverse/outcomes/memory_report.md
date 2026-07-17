# 内存报告

| run | peak incl. RTA | vs P0 baseline |
|---|---:|---:|
| P0 ILU baseline | 1.595139 GiB | reference |
| slab-9 exact-LU oracle | 1.778637 GiB | +11.50% |
| slab 0/9/10 exact-LU oracle | 2.002991 GiB | +25.57% |

Oracle profile 为了测迭代上限，当前实现仍保留原 ILU factors 并额外构造 sparse LU，因此该峰值不是 factor-removal candidate，也不能用于 NN 在线内存结论。P6 未解锁，没有 selected-factor removal 或 memory-saving claim。

离线 slab-9 teacher 的显式 factor storage 估算为 82.07 MB；checkpoint/model storage 为 not applicable，因为 oracle Gate 阻止了模型训练。所有 teacher/capture artifacts 保持 Git ignored。
