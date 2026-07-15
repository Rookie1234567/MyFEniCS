# Task032 物理场、Modal-Schur 与内存路径走读

## 调用链

```text
run_task032_phase6_augmented
├─ QEP candidate solve
├─ select_passive_direction_modes
├─ build_hybrid_internal_mode_coupling
├─ augmented / modal-schur-fast / modal-schur-memory-minimal
├─ evaluate_hybrid_augmented_solution
├─ ModalFieldReconstructor
│  ├─ selected_planes
│  └─ absorbed_power_code_units
└─ interface_field_continuity / hybrid_volume_absorption
```

内部截面模态与外部 Fourier 衍射模态仍是两套不同对象。前者只替代
z=10--110 nm 的规则中间体；上下局部三维区继续使用冻结的外部
Fourier-DtN 端口和 official modal R/T。

## 被动方向候选过滤

`solve_quadratic_beta_modes` 在宽 target slice 中可能同时返回正向、反向和
衰减分支。`select_passive_direction_modes` 先依据 Poynting 和被动衰减规则
筛选，再交给伴随 QEP 和双正交归一化。宽漏斗默认求 2M 个候选，只保留
指定方向的 M 个；被拒候选立即 destroy。这样不能把 target 附近的错误反向
分支静默塞进传播基。

## E/H 重构与吸收

`ModalFieldReconstructor` 不保存完整中间三维体场。它复用一个 mixed 源函数、
横向/纵向 scratch 和一个 DG H scratch，依次装入每个模态，避免 M=120 以上
为每个模态新建 scatter graph 而耗尽 MPICH context ID。

时间约定是 `exp(-i omega t)`，因此：

```text
H = curl(E) / (i k0 mu_r)
```

并乘冻结配置的 A/m 缩放。选面只重构 z=10/30/60/90/110 nm；界面连续性
比较局部 FEM 与 modal 的切向 E/H。中间吸收用 z 分段 Gauss-Legendre，局部
区吸收仍由 FEM 体积分得到；二者相加后与 R+T 做能量闭合。

h3 的 Stage-4 基础 z 轴是 3 nm 倍数，不含 10/110 nm。局部 Hybrid 网格在
不移动冻结物理接口的前提下插入这两个精确平面；x/y 轴和二维截面仍完全
匹配，不引入 mortar。

## 两条 Modal-Schur 生命周期

`build_hybrid_modal_schur_direct_system` 使用每个局部稀疏 LU 的一次
`KSP.matSolve([f,C])` 得到 `D A^-1 [f,C]`，只形成 2M x 2M dense modal
Schur；禁止 dense Ninterface x Ninterface。`fast_direct` 同时保留 bottom/top
因子，用于解出 modal amplitude 后恢复两个局部场。

`build_hybrid_modal_schur_memory_minimal_system` 的生命周期是：

```text
bottom factor -> multi-RHS contribution -> release
top factor    -> multi-RHS contribution -> release
modal solve
bottom refactor/recover/release
top refactor/recover/release
```

两条路径都记录 MUMPS factor nnz/raw INFOG、projection bytes、eigenvector bytes、
modal Schur bytes、setup/multi-RHS/recovery time，并提供幂等 destroy。

## 外部内存权威

`run_task032_memory_forensics` 每 0.25 s 同时采样：

- 当前四个 MPI worker RSS 之和；
- MPI process tree RSS；
- container cgroup current/peak；
- WSL swap in/out；
- 当前求解阶段。

不能把四个 rank 在不同时间出现的 historical `ru_maxrss` 相加当正式峰值。
Task32 阶段标记覆盖 eigen assembly/solve、classification、local assembly、
两侧 factor/Schur contribution、modal solve、field recovery、选面和 official RTA。

## Benchmark 路由

- `run_task032_phase8_funnel.py`：比较 M 递增时 total、复振幅、per-order power 和界面投影；
- `run_task032_phase9_smoke.py`：固定 h5/h3 角度/S-P 参数入口 smoke，不升级为全范围 production qualification；
- `run_task032_h2_prediction.py`：分别用网格尺度和 MUMPS factor payload 外推 h2，执行中心 4 GiB、上界 5 GiB 的 fail-closed 解锁判据。
- `run_task032_scalability_projection.py`：输入 wavelength/period/local thickness/mesh/mode safety/MPI，输出 deterministic `analytical_resource_projection`；它不是 PDE run 或 solver pass。

完整 volume reconstruction 仍是 heavy opt-in；普通 Task32 记录不聚集完整 FE
field、mode vector、mesh 或 interface-square matrix。

Review V1 后，current-scale QEP/augmented/Schur docstring 明确标记：last-rank modal ownership、
replicated dense M²、all-mode dense multi-RHS、all-modes MUMPS shift-invert 和 local LU 不能直接
扩展到 0.7 nm。未来主线保留 complex 3D ends + generic `epsilon(x,y)` modal middle。
