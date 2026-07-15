# Phase 10 内存、时间与 h2 决策

## 测量口径

每条路径在独立进程中运行 h5/h3、M160、MPI4、complex128。外部采样每
0.25 s 同时读取四个 worker 当前 RSS，并单列 process tree、container cgroup、
swap 和 stage。不得把不同 rank 的 historical high-water 相加。

## 独立实测

| mesh/path | simultaneous worker RSS GiB | cgroup current peak GiB | total s | peak stage | swap |
|---|---:|---:|---:|---|---|
| h5 augmented | 1.8691 | 1.2671 | 57.6 | middle-plane reconstruction | 0 |
| h5 Schur fast | 1.6493 | 1.0345 | 42.2 | middle-plane reconstruction | 0 |
| h5 Schur memory-minimal | 1.6802 | 1.0479 | 51.0 | interface coupling | 0 |
| h3 augmented | 3.8688 | 3.2293 | 106.3 | augmented factor | 0 |
| h3 Schur fast | 3.9737 | 3.3416 | 96.9 | top Schur contribution | 0 |
| h3 Schur memory-minimal | 3.2148 | 2.5674 | 101.9 | bottom Schur contribution | 0 |

h5 上 Schur-fast 比 augmented 降约 11.8%，memory-minimal 却比 fast 高约
1.9%；h3 上 fast 反而比 augmented 高约 2.7%，而 memory-minimal 比
augmented 降约 16.9%。结论是：同时保存两个局部因子并不保证总填充更小；
顺序因子生命周期只在 h3 规模开始显示结构收益。

记录同时保留 interface active DoF、M、projection estimate bytes、modal Schur
bytes、right/left eigenvector bytes、MUMPS factor nnz/estimate bytes、阶段峰值
和 setup/multi-RHS/recovery time。全部路径保持 `O(N_interface*M)+O(M^2)`，
没有 dense interface square。

## h2 双方法预测

以 h3 峰值最低的 `modal-schur-memory-minimal` 为候选：

| 方法 | 中心 GiB | 保守上界 GiB |
|---|---:|---:|
| h5/h3 网格尺度 power law | 5.3805 | 6.1876 |
| MUMPS factor payload affine | 11.5109 | 13.2376 |

第二种方法较保守，因为 h5/h3 的 factor fill 指数约 4.34；它是 fail-closed
工程外推，不是统计置信区间。两种中心均未满足 `<=4.0 GiB`，上界也未满足
`<=5.0 GiB`。

```text
h2 unlock = false
warning = 4.5 GiB
controlled termination = 6.0 GiB
decision = do not run h2 in Task032
```

这是任务书规定的停止条件。不得用已有宿主余量或一次冒险运行绕过预测 Gate。
