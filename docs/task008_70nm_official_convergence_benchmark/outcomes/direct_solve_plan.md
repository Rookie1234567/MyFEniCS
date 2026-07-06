# Direct Solve Plan

## 任务设置

本计划基于 task008 的 assemble-only 结果制定。主设置为：

| item | value |
|---|---|
| domain | 50 × 25 × 140 nm |
| grating | 17 × 25 × 120 nm |
| substrate / top air | 10 nm / 10 nm |
| incidence | theta_from_z = 80 deg, phi = 0 deg |
| polarization | s, E along y |
| boundary | dtn_port, auxiliary, auto_propagating |
| official power | dtn_port_modal_amplitudes |
| MPI | 8 ranks |

## Assemble-Only 依据

| p | 最细完成 h/nm | 首个失败或停止 h/nm | 关键说明 |
|---:|---:|---:|---|
| 1 | 1.0 | 无 | h=1 完成，rows=559626，nnz=1.9017936e7，AIJ≈0.429 GB，RSS upper≈4.47 GB |
| 2 | 1.5 | 1.0 | h=1.5 完成，rows=1347314，nnz=1.42656204e8，AIJ≈3.199 GB，RSS upper≈13.89 GB；h=1 在 base matrix assembled 后 2400 s 超时，swap 增加约 33.40 GB |

80° 斜入射下 DtN auxiliary mode count 为 80，其中 top/bottom 各 40。相比 100×100 nm 周期案例的 708 个 auxiliary mode，本任务因为周期缩小到 50×25 nm，端口模态数量明显减少；但 p=2 h=1.5 的矩阵本体已经达到约 3.2 GB，default direct 仍可能因 LU fill-in 突破本机内存。

## Default Direct 计划

### p=1

计划运行：

```text
h = 5, 4, 3, 2.5, 2, 1.5, 1 nm
```

理由：p=1 h=1 assemble-only 仍较轻，适合作为本机 p=1 最细 direct benchmark 和收敛表末端。

### p=2

计划运行：

```text
h = 5, 4, 3, 2.5, 2 nm
```

若 p=2 h=2 default direct 完成且资源仍可接受，则继续尝试：

```text
h = 1.5 nm
```

p=2 h=1 不进入 default direct 计划；它已经在 assemble-only 阶段超时，并出现明显 swap 增长，应作为 assemble-only failure boundary 记录。

## OOC 计划

本任务不把 OOC 作为必跑主线。若 default direct 在 p=2 h=1.5 或 h=2 失败，可选择对同一边界点尝试 tuned MUMPS OOC；若时间或资源不允许，则在 failure boundary 中记录 default direct 失败并建议后续单独任务处理 OOC/迭代法。

## 预计边界

| p | 预计 last completed direct | 预计 first failed direct | 说明 |
|---:|---:|---:|---|
| 1 | h=1 | 无或 h<1 | p=1 规模明显低于 task006 reduced-height p=2 边界 |
| 2 | h=2 或 h=1.5 | h=1.5 或 h=1 | h=1.5 assemble RSS upper 已接近本机 WSL 内存分配；h=1 assemble-only 已超时 |

## 实际执行结果

计划执行后得到的实际边界为：

| p | actual last completed direct | actual first failed direct | 说明 |
|---:|---:|---:|---|
| 1 | h=1 | 未尝试 h<1 | p=1 h=1 completed，R=0.0945820，T=0.423887，A_volume=0.481531 |
| 2 | h=2 | h=1.5 | p=2 h=2 completed，R=0.00134293，T=0.599213，A_volume=0.399444；p=2 h=1.5 在 `stage4_dtn_augmented_ksp_setup` 被 signal 9 kill |

p=2 h=1 不进入 direct：assemble-only 已在 `stage4_dtn_base_matrix_assembled` 后超时，AIJ 估算矩阵约 10.313 GB，并出现约 33.4 GB swap 增量。
