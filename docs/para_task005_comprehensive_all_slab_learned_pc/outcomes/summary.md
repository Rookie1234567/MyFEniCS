# PARA-Task005 执行总结

## 最终状态

| 项目 | 结果 |
|---|---|
| classification | `learned_pc_memory_budget_failure` |
| secondary finding | local quality 与 model-only runtime positive |
| P0 | PASS |
| P1 | PASS，16/16 teacher |
| P2 local quality | PASS，有多个 R4 4/4 admissible candidates |
| P2 model runtime | PASS，owner batch 1.34–4.93 ms mean |
| P2 storage | **FAIL**，最小完整 owner 68.282 MiB |
| P3–P9 | `not_run_by_gate` |
| ordinary default | 未改变 |
| pull / push / merge / branch | 均未执行 |

## 数据与 teacher

| split | 每 slab | 总样本 | 当前身份 |
|---|---:|---:|---|
| T1 train | 512 | 8192 | 独立执行、同分布相关 |
| T2 train | 512 | 8192 | 独立执行、同分布相关 |
| V validation | 256 | 4096 | 未用于选择 |
| H screening | 256 | 4096 | 已用于候选筛选 |

四次 capture 是 execution-independent but distribution-correlated：它们来自相同
固定物理、确定性 RHS/Krylov trajectory distribution。互斥性只由 stride/offset
保证；capture 未记录 phase、norm bucket 或 outer-iteration metadata。

| Teacher Gate | 实测 | 门槛 | 状态 |
|---|---:|---:|---|
| datasets | 16/16 | 16/16 | PASS |
| worst slab median rho | `5.905e-15` | `<=1e-11` | PASS |
| worst slab p95 rho | `7.469e-15` | `<=1e-10` | PASS |
| global max rho | `1.050e-14` | `<=1e-9` | PASS |
| fingerprint stable | 16/16 | 16/16 | PASS |
| exact/near duplicate | 0 / 0 | 0 / 0 | PASS |
| factor destroyed | 16/16 | 16/16 | PASS |
| swap delta | 0 / 0 | 0 / 0 | PASS |

## P2 模型能力

| candidate | R4 admissible | median-ratio range | p95-ratio range | 判断 |
|---|---:|---:|---:|---|
| Lane A D0 rank 32 | 2/4 | 0.573–1.188 | 0.765–1.091 | reject |
| Lane A D0 rank 64 | 4/4 | 0.418–0.917 | 0.491–0.836 | local pass |
| Lane A D0 rank 96 | 4/4 | 0.292–0.764 | 0.333–0.726 | stronger / too large |
| Lane A D0 rank 128 | 4/4 | 0.219–0.632 | 0.231–0.614 | strongest / too large |
| Lane A D1 rank 96 | 4/4 | 0.353–0.800 | 0.404–0.745 | worse than D0 |
| Lane B D0 rank 64 GELU skip | 4/4 | 0.409–0.910 | 0.473–0.822 | no clear gain over A |
| Lane B D1 rank 64 GELU skip | 4/4 | 0.483–0.997 | 0.608–0.884 | worse than D0 |

D1 的五类 index-space structured synthetic exact pairs 与四个幅值尺度没有改善
当前 R4 consumed screening split，故不升级为 full recipe；该结论不覆盖
physics-aware structured augmentation。Lane B 没有明确优于 Lane A，按条件不运行 Lane C；
Lane A/B 已有 local pass，因此也不触发 Lane D。

## Backend 与 owner batch

| candidate/backend | grouped mean | p95 | 7.2 ms | 等价性 |
|---|---:|---:|---|---|
| linear NumPy CPU | 4.097 ms | 4.292 ms | PASS | `0.0` |
| linear PyTorch CPU | 4.932 ms | 6.101 ms | PASS | `0.0` |
| linear PyTorch CUDA | 1.361 ms | 1.515 ms | PASS | `0.0` |
| nonlinear PyTorch CPU | 2.931 ms | 3.090 ms | PASS | `2.157e-7` |
| nonlinear PyTorch CUDA | 1.343 ms | 1.767 ms | PASS | `1.298e-7` |

## Storage Gate

| 配置 | model/basis | private exact-audit CSR | 合计 | 33.670 | 50.505 |
|---|---:|---:|---:|---|---|
| heterogeneous smallest admissible linear | 27.824 MiB | 40.458 MiB | **68.282 MiB** | FAIL | FAIL |
| heterogeneous smallest admissible nonlinear | 28.234 MiB | 40.458 MiB | **68.692 MiB** | FAIL | FAIL |

这是硬早停原因。只报告 checkpoint storage 会隐藏 exact/periodic audit 所需 operator，
违反任务书的 storage 定义。

## 卡住与恢复

| 事件 | 根因 | 处置 | 数据完整性 |
|---|---|---|---|
| scalar teacher 看似卡住 | 逐 RHS SuperLU 粒度过细 | 改为最大 64 RHS 有界批次 | rejected run 保留 |
| WSL 无法启动/注册 | 两条旧 grep/SCOTCH probe 持有 VM | 清理明确 PID、重启 WSL service、原地恢复 VHDX | 未重装/复制/删除 |
| 第一次 nohup 无进程 | WSL shell 退出回收子进程 | Windows hidden process 持有会话 | 0 个半成品 |

## 决策

Task005 到 P2 为止已经回答：神经/learned local inverse 在当前固定 operator 上具有
局部质量和模型计算速度可行性，但当前严格 audit storage architecture 不可行。
按 Gate 停止 full16，避免额外训练产生无法进入集成的 checkpoint。

建议的后续任务不是扩大神经网络，而是资格化无私有 CSR 副本的 strict proxy +
periodic exact audit；通过后才恢复 P3。
