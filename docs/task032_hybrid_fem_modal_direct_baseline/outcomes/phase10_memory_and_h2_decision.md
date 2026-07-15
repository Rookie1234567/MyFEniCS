# Phase 10 内存、时间与 h2 决策

## 测量口径

每条路径均在独立容器进程中运行 h5/h3、M160、MPI4、complex128。外部采样器
每 0.25 s 同时读取四个 worker 的当前 RSS，并单列 container cgroup、swap 与
阶段标记；不把不同 rank、不同时间的 historical high-water 相加。

六条正式记录来自 clean source
`793354af0ac72cbfe1c6eb1030b2438afe10c101`，镜像实际 ID 为
`sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d`。
全部记录数值通过、零 swap、未触发 4.5 GiB warning 或 6 GiB controlled
termination。

## 独立实测

| mesh/path | worker RSS GiB | cgroup current GiB | solver total s | peak stage | swap |
|---|---:|---:|---:|---|---:|
| h5 augmented | 1.8654 | 1.5838 | 70.72 | record and release | 0 |
| h5 Schur fast | 1.7551 | 1.1598 | 63.01 | middle-plane reconstruction | 0 |
| h5 Schur memory-minimal | 1.6977 | 1.0611 | 60.91 | interface projection and coupling | 0 |
| h3 augmented | 3.8526 | 3.2150 | 102.58 | augmented matrix and factor | 0 |
| h3 Schur fast | 3.9983 | 3.3623 | 111.97 | top Schur contribution | 0 |
| h3 Schur memory-minimal | 3.2244 | 2.5865 | 99.69 | bottom Schur contribution | 0 |

h5 上 memory-minimal 相对 augmented 降低 `8.99%`。h3 上 Schur-fast 反而比
augmented 高 `3.78%`；顺序因子生命周期的 memory-minimal 才把 h3 峰值降低
`16.31%`。因此正式结论不是“Schur 必然省内存”，而是：只有显式释放 bottom
因子、再构造 top 因子并在恢复时逐侧重新因子化，才在 h3 规模形成可重复的
结构性收益。

记录同时保留 interface active DoF、模式数、projection estimate、modal Schur
bytes、right/left eigenvector bytes、MUMPS factor nnz/estimate、阶段峰值及
setup/multi-RHS/recovery 时间。三条路径都保持
`O(N_interface*M)+O(M^2)`，没有 dense interface square，也没有完整
field/mode gather。

## h2 双方法预测

以 h3 峰值最低的 `modal-schur-memory-minimal` 为候选：

| 方法 | 中心 GiB | 保守上界 GiB |
|---|---:|---:|
| h5/h3 网格尺度 power law | 5.3649 | 6.1697 |
| MUMPS factor payload affine | 11.6468 | 13.3938 |

两种独立方法的中心值都未满足 `<=4.0 GiB`，保守上界也都未满足
`<=5.0 GiB`。第二种方法是基于 MUMPS 填充载荷的 fail-closed 工程外推，
不是统计置信区间。

```text
h2 unlock = false
h2 run performed = false
warning = 4.5 GiB
controlled termination = 6.0 GiB
decision = do not run h2 in Task032
```

这是任务书第 5.7 节和停止规则的强制结果。未执行 h2 不是遗漏，而是通过预测
Gate 后应当作出的停止决定；不得用宿主剩余内存或一次冒险运行绕过它。
