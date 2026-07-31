# Task036 forward solver bugfix report

## 1. 报告边界与源码身份

Task036 是 `BUGFIX_ONLY`：只修正已有失败证据支持的前向求解器缺陷，或在无法
局部修复时增加确定性的 fail-closed（在产生错误物理结果前主动拒绝）。本轮没有
引入 surrogate、dataset、inversion、迭代法、h/p campaign 或新的求解器框架。

| 项目 | 身份 |
|---|---|
| 起始 `origin/master` | `007298261681014efbe6508ac91c6c3ae9a6a44a` |
| 第一批核心修复 | `393b7c583c40bea17d4ceca6440c140317e0b60c` |
| reciprocal / reference-binding 加固 | `9de46581fa47ea02295d73688d30a55a38c01a91` |
| incidence / exact-traction Gate 加固 | `bb0e5e3e385586e137d861cf0a53a142e4fe0fe0` |
| Review V2 M120 数值源码 | `6d5e9781bcb1458ecac7a77af22fa2d420f0cd55` |
| 工作分支 | `codex/20260730-task36-forward-solver-bugfix-hardening` |
| ordinary default | **unchanged** |
| Hybrid-P production | **仍未资格化，继续 quarantine** |

三批正式本地 artifact 根目录为：

```text
benchmarks/artifacts/task036/
    393b7c583c40bea17d4ceca6440c140317e0b60c/
        20260730T110213Z/
    9de46581fa47ea02295d73688d30a55a38c01a91/
        20260730T122723Z_reciprocal_basis_batch_v1/
    bb0e5e3e385586e137d861cf0a53a142e4fe0fe0/
        b06_p6phi45_final_source_v1/
    6d5e9781bcb1458ecac7a77af22fa2d420f0cd55/
        v2_robustness/
```

这些是本地、SHA-bound 的回归证据，不作为新的 tracked evidence schema。最终测试
计数由 `test_summary.md` 汇总；本文按 bug 说明覆盖范围和数值证据。

### 1.1 术语的通俗解释

- **切向场**：端口平面内的 `E_x/E_y`。DtN 端口只与这两个分量耦合，垂直于端口
  的 `E_z` 不能偷偷混入投影。
- **reciprocal 正/负模态**：同一横截面上分别向 `+z/-z` 传播或衰减的一对波。
  两边必须使用同一套离散坐标身份，否则舍入误差会被高阶插值放大。
- **exact variational conormal dual**：不在少量采样点上比较一个强形式近似，而在
  整个有限元试验空间中检查界面载荷是否平衡；这是正式 traction/H 连续性依据。
- **beta**：模态沿 `z` 方向传播或衰减的常数。传播 E、构造 traction 和恢复 H
  可以有不同来源，但必须显式记录，不能静默混用。
- **biorthogonality**：非自伴模态的左右基应形成近似单位矩阵。若两个几乎简并的
  模态被拆进不同 block，单个交叉项可能不大，但一整行累积误差仍可能超 Gate。
- **trace alias**：网格太粗时，本应正交的两个衍射谐波在离散边界空间里变得几乎
  一样，产生假的非零衍射能量。
- **historical peak**：各 rank 在不同时间各自见过的峰值；不能把它们相加冒充同一
  时刻的总内存。同步 sampler 的 process-tree RSS/PSS/USS 才是整作业内存 authority。

## 2. 结论总览

| bug | 最终状态 | 结论 |
|---|---|---|
| B01 DtN tangential projection | `FIXED` | S/P、top/bottom、零级/非零级的直接切向投影均通过 `1e-10` Gate |
| B02 high-order reciprocal trace | `FIXED` | degree、quadrature、canonical/raw 坐标闭合；F1 standard/static 通过 |
| B03 exact traction dual | `FIXED` | formal exact dual 与 sampled proxy 已彻底分开 |
| B04 beta semantics | `FIXED` | propagation/traction/reconstruction 及 static local reassembly 来源和值显式一致 |
| B05 Hybrid-P disposition | `FAIL_CLOSED` | Full3D-P 存在；Hybrid-P 仍不允许成为 production |
| B06 near-degenerate blocks | `FAIL_CLOSED` | 检测和一次有界修复已实现；M40 仍是 controlled negative，通用解法 deferred |
| B07 Ny trace alias | `FIXED` | Ny3 在 solve 前确定性拒绝；Ny4 正式通过 |
| B08 MUMPS factor NNZ overflow | `FIXED` | `2,277,000,000` 正确恢复且 raw 值保留 |
| B09 solver lifecycle | `FIXED` | Full3D 已有路径确认；Hybrid factor/system 可在 field output 前释放 |
| B10 memory/MPI semantics | `FIXED` | simultaneous authority 与 historical upper bound 不再混称 |
| B11 DoF/row semantics | `FIXED` | active、carrier、trace rows、augmented rows 分字段报告 |

## 3. B01：DtN 直接模态投影严格使用切向场

### before

`_mode_projection_from_solution` 的分子使用三分量 E 与三分量 mode，分母却只用
tangential norm。S 模态常有 `E_z=0`，所以错误被掩盖；P 模态 `E_z!=0` 时历史
Case118 出现最大约 `5.252668e-3` 的假 discrepancy。

### root cause

诊断分子和分母采用了不同的物理内积。DtN 的未知量是端口切向 trace，因此必须
同时忽略场和参考模态的第三分量，并在 top 端统一减去入射投影。

### changed files

```text
src/solvers/dtn_port_3d.py
benchmarks/run_task033_full3d_watchdog.py
src/test/test_14_stage4_dtn_modes.py
src/test/test_68_task033_full3d_watchdog.py
```

### minimal fix

直接投影只形成 `(E_x,E_y,0)` 与 `(e_x,e_y,0)`；增加纯 NumPy oracle 和统一
outgoing/incident subtraction；官方 auxiliary amplitude 定义完全不改。watchdog
要求正式记录具备完整、有限、唯一的 mode identity，并覆盖 top/bottom 与 S/P。

### after

MPI8 正式点全部远低于 `1e-10`：

| 代表点 | backend | 最大绝对差 |
|---|---|---:|
| p2/h5, S | standard | `9.4748898284e-14` |
| p4/h10, P | static | `1.2858608598e-13` |
| p6/h10, S | static | `1.7523606569e-12` |
| F2, `0.5°/0°/P` | static | `8.7387411650e-12` |
| F5, `10°/90°/P` | static | `2.3768368512e-14` |

上述运行同时通过 true residual、能量、Floquet、zero-swap 和完整投影身份检查。

### regression scope

synthetic oblique S/P、非零 `E_z`、lossy-bottom P、top incident subtraction、近零
通道绝对误差，以及实际 p2/p4/p6、standard/static、MPI8 Full3D。

### remaining limitation

这是诊断公式修复，不改变 official DtN amplitude，也不等价于资格化 Hybrid-P。

### status

`FIXED`

### evidence

```text
benchmarks/artifacts/task036/393b7c583c40bea17d4ceca6440c140317e0b60c/20260730T110213Z/w1_full3d_p2h5_s_standard_retry1/run/watchdog_summary.json
benchmarks/artifacts/task036/393b7c583c40bea17d4ceca6440c140317e0b60c/20260730T110213Z/w1_full3d_p4h10_p_static_retry1/run/watchdog_summary.json
benchmarks/artifacts/task036/393b7c583c40bea17d4ceca6440c140317e0b60c/20260730T110213Z/w1_full3d_p6h10_s_static_anchor_retry1/run/watchdog_summary.json
benchmarks/artifacts/task036/393b7c583c40bea17d4ceca6440c140317e0b60c/20260730T110213Z/w3_full3d_f2_p4h10_0p5_phi0_p_static/run/watchdog_summary.json
benchmarks/artifacts/task036/393b7c583c40bea17d4ceca6440c140317e0b60c/20260730T110213Z/w3_full3d_f5_p4h10_10_phi90_p_static/run/watchdog_summary.json
```

## 4. B02：高阶 reciprocal trace 的 degree / quadrature / canonical 一致性

### before

历史 F1 低掠射 trace residual 为约 `6.3e-8`–`7.0e-8`。lifted coefficient
曾按 degree 0 选 quadrature；正负 reciprocal trace 又分别从浮点坐标恢复，导致
本来很小的坐标舍入误差被高阶插值和 entity reduction 放大。

### root cause

同一物理 trace 被赋予两套数值坐标身份，而且积分阶数没有反映真实 lifted FE
degree。问题是离散表示不一致，不是 Maxwell 解不存在。

### changed files

```text
src/coupling/hybrid_internal_modes.py
src/solvers/hcurl_assembly_time_condensation.py
src/solvers/hybrid_local_dtn.py
src/solvers/hybrid_local_static_condensation.py
src/modes/mode_classification.py
src/modes/quadratic_beta_eigenproblem.py
benchmarks/run_task032_phase6_augmented.py
src/test/test_53_task033_high_order_hybrid_components.py
src/test/test_179_task035b_hybrid_static_condensation.py
src/test/test_33_task032_mode_classification.py
src/test/test_79_task034_native_full3d_reference.py
```

### minimal fix

1. quadrature 使用 lifted target space 的真实 degree；
2. 每个 side/role/mode 记录 surface reduction audit；
3. 先检查 raw relation，再让 reciprocal negative trace 使用同一 canonical basis；
4. 增加显式 opt-in 的 scalar `stage4_xy` reciprocal negative basis：先独立求解并
   审计负向 QEP，再按解析 reciprocal 对称构造 coupling basis，重算约束投影、
   QEP residual、Poynting flux 和 `Q'(beta)` identity；
5. ordinary default 继续使用 independent positive/negative QEP。

### after

F1 p4/h10/M120 的 MPI8 结果：

| 指标 | standard | static |
|---|---:|---:|
| bottom raw reciprocal consistency | `9.34999e-16` | `8.40901e-16` |
| top raw reciprocal consistency | `7.57846e-16` | `8.13179e-16` |
| max canonical representation error | `2.34583e-15` | `2.50926e-15` |
| combined interface-E algebra residual | `2.20448e-11` | `2.38902e-11` |
| true residual | `3.09037e-11` | `3.32409e-11` |

解析 reciprocal construction audit 在两点均 `pass`；约束重构误差约 `1e-17`，
重算后的左右 polynomial residual 仍远低于 `1e-8` Gate。

ordinary-default 对照
`b1_conical_s_m120_standard_ordinary` 明确记录
`task036_scalar_stage4_reciprocal_basis_requested=false`、正负 basis 均为
`independent_qep`，且全部正式 S physical gates 通过。因此本修复没有静默改变
ordinary default。

### regression scope

p1–p6 trace/degree policy、orientation reversal、正负 reciprocal、standard/static、
MPI 路径，以及 F1 standard/static MPI8 actual PDE。显式 opt-in parser 与非零
方位角 Full3D reference hash/incidence 绑定也有独立测试。

### remaining limitation

解析 reciprocal basis 只允许 scalar `stage4_xy` 且显式 opt-in；分类为
`research_only / not_production`，不是 ordinary default，也不是通用各向异性
模态架构。独立负向 QEP 仍先运行并保存为审计，不能跳过。该 opt-in 路径与
partition audit/repair 的实现规模较大，最终是否选择性合入 production 应由后续
review 单独决定，不能因本轮实测通过而自动提升。

### status

`FIXED`

### evidence

```text
benchmarks/artifacts/task036/9de46581fa47ea02295d73688d30a55a38c01a91/20260730T122723Z_reciprocal_basis_batch_v1/b1_f1_m120_s_standard/solver_record.json
benchmarks/artifacts/task036/9de46581fa47ea02295d73688d30a55a38c01a91/20260730T122723Z_reciprocal_basis_batch_v1/b1_f1_m120_s_static/solver_record.json
benchmarks/artifacts/task036/9de46581fa47ea02295d73688d30a55a38c01a91/20260730T122723Z_reciprocal_basis_batch_v1/b1_conical_s_m120_standard_ordinary/solver_record.json
```

## 5. B03：sampled traction proxy 与 exact variational dual 分离

### before

采样点上的 strong-traction density L2 proxy 曾使用看似“exact traction”的名称，
runner 也可能把 sampled magnetic continuity 当成正式 H/traction Gate。

### root cause

采样 proxy 只回答“有限采样点上两组密度看起来多接近”；它不等于有限元弱式里
对所有试验函数都成立的界面载荷平衡。两种量被混名，导致诊断量可能否决或资格化
正式结果。

### changed files

```text
src/solvers/hybrid_fem_modal_augmented_direct.py
src/postprocessing/hybrid_field_reconstruction.py
benchmarks/run_task032_phase6_augmented.py
benchmarks/task032_final_gates.py
benchmarks/task034_mpi_identity.py
src/test/test_39_task032_hybrid_augmented_direct.py
src/test/test_196_task036_forward_solver_hardening.py
```

### minimal fix

增加详细 FE conormal dual，分别保存 operator、RHS、正/负 modal traction load
及相对 dual residual；保留旧 scalar wrapper 兼容。采样量改名为
`traction_density_l2_proxy`，写明 `diagnostic_only` 和 `formal_gate=false`；
正式 Gate 只读取 `traction_hcurl_dual.relative_dual`。旧 Task032 记录的兼容仅
绑定冻结 SHA 且要求 top/bottom 两个 exact dual 都完全缺失；新记录缺失一侧、
部分缺失或数值超限均 fail closed。

### after

- conical ordinary S：bottom/top exact dual 为
  `3.3845e-12 / 1.2662e-12`；
- F1 standard：`1.0571e-11 / 6.1969e-12`；
- F1 static：`5.3574e-12 / 5.8479e-12`；
- F2/F5 P：exact dual 也约 `1e-13`，但 Hybrid-P 仍因其他物理 Gate 正确拒绝。

F1 bottom sampled proxy 为约 `1.2805e-2`，超过旧 diagnostic 阈值，但 exact dual
与正式 S physical gates 通过。这正是语义分离应产生的结果：**sampled proxy
不是 formal failure，也不能拿来掩盖真正的 formal failure。**

### regression scope

synthetic exact balance、故意扰动 modal traction、diagnostic/formal Gate 隔离、
top/bottom、S/P、standard/static actual PDE。

### remaining limitation

sampled proxy 仍保留供定位局部场形状问题，但没有资格化或否决权。

### status

`FIXED`

### evidence

```text
benchmarks/artifacts/task036/9de46581fa47ea02295d73688d30a55a38c01a91/20260730T122723Z_reciprocal_basis_batch_v1/b1_conical_s_m120_standard_ordinary/solver_record.json
benchmarks/artifacts/task036/9de46581fa47ea02295d73688d30a55a38c01a91/20260730T122723Z_reciprocal_basis_batch_v1/b1_f1_m120_s_standard/solver_record.json
benchmarks/artifacts/task036/9de46581fa47ea02295d73688d30a55a38c01a91/20260730T122723Z_reciprocal_basis_batch_v1/b1_f1_m120_s_static/solver_record.json
benchmarks/artifacts/task036/9de46581fa47ea02295d73688d30a55a38c01a91/20260730T122723Z_reciprocal_basis_batch_v1/b1_f2_m120_p_static/solver_record.json
benchmarks/artifacts/task036/9de46581fa47ea02295d73688d30a55a38c01a91/20260730T122723Z_reciprocal_basis_batch_v1/b1_f5_m120_p_static/solver_record.json
```

## 6. B04：propagation、traction 与 reconstruction beta 显式分离

### before

E propagation 已使用选定的 propagation beta，但 H reconstruction 仍可能直接取
`mode.beta`，没有证明它等于 coupling 实际使用的 traction beta。

### root cause

不同离散模型给出的 beta 可能非常接近，却不完全相同。静默混用会使 E 与 H 来自
不同的离散身份，进而让 traction/energy 诊断失去可解释性。

### changed files

```text
src/postprocessing/hybrid_field_reconstruction.py
src/solvers/hybrid_static_field_recovery.py
benchmarks/run_task032_phase6_augmented.py
src/test/test_39_task032_hybrid_augmented_direct.py
```

### minimal fix

`ModalFieldReconstructor` 显式接收成对的 positive/negative traction beta；E 继续用
propagation beta，H/traction 使用选定 traction beta；缺一侧、长度不匹配或非有限
输入均 fail closed。记录同时保存 requested/selected 模型、数值数组和 reconstruction
来源。Review V2 又发现 static-condensed field recovery 在重新装配局部 traction 时
没有沿用该 selected beta；现已通过 `beta_override` 把 coupling 的 discrete traction
beta 传给 local reassembly，避免 solve 与 recovery 再次分叉。

### after

全部新 Hybrid 记录均写明：

```text
field_reconstruction_magnetic_beta_source =
    selected_coupling_traction_beta
field_reconstruction_beta_equals_traction_beta = true
```

单元回归还证明：只改变 traction beta 会改变 H，但 E 位完全不变。

源码 `6d5e978...` 的五个 M120 actual 点均得到 exact traction
`4.565e-13–2.169e-11`。不过 recovered physical interface E jump 仍为
`9.272e-5–1.822e-1`，说明 beta 身份修复是必要修复，但不是 remaining M120
channel failure 的完整根因。

### regression scope

beta 数组配对/shape/finite 检查、E/H 分离，以及 F1/F2/F5/conical actual PDE。

### remaining limitation

Task036 没有重新设计 axial modal method；未资格化的传播/traction 组合继续拒绝。
M120 的 trace-complement 强消元需要改变 trial/test space，按
`DEFERRED_ARCHITECTURE_REQUIRED` 留给后续独立任务。

### status

`FIXED`

### evidence

```text
benchmarks/artifacts/task036/9de46581fa47ea02295d73688d30a55a38c01a91/20260730T122723Z_reciprocal_basis_batch_v1/b1_conical_s_m120_standard_ordinary/solver_record.json
benchmarks/artifacts/task036/9de46581fa47ea02295d73688d30a55a38c01a91/20260730T122723Z_reciprocal_basis_batch_v1/b1_f1_m120_s_standard/solver_record.json
benchmarks/artifacts/task036/9de46581fa47ea02295d73688d30a55a38c01a91/20260730T122723Z_reciprocal_basis_batch_v1/b1_f1_m120_s_static/solver_record.json
benchmarks/artifacts/task036/9de46581fa47ea02295d73688d30a55a38c01a91/20260730T122723Z_reciprocal_basis_batch_v1/b1_f2_m120_p_static/solver_record.json
benchmarks/artifacts/task036/9de46581fa47ea02295d73688d30a55a38c01a91/20260730T122723Z_reciprocal_basis_batch_v1/b1_f5_m120_p_static/solver_record.json
```

## 7. B05：Hybrid-P 不得被误判为物理不存在

### before

旧 generic status 不能区分：Full3D-P 物理解是否存在、Hybrid modal rank 是否
不足、Hybrid interface/energy 是否失败，以及投影 diagnostic 是否有 bug。

### root cause

一个总状态混合了“物理 PDE 可解”和“某个降阶 Hybrid 表示能否承载该解”两个
不同问题。Full3D-P 已通过，Hybrid M120 失败不能写成 P 物理失败。

### changed files

```text
benchmarks/run_task032_phase6_augmented.py
benchmarks/task032_final_gates.py
benchmarks/task035c_p6_h10_gates.py
src/test/test_181_task035c_p6_h10_runner_gates.py
src/test/test_79_task034_native_full3d_reference.py
```

### minimal fix

增加明确 disposition：

```text
full3d_physical_solution_exists
hybrid_modal_rank_insufficient
hybrid_interface_closure_failed
diagnostic_projection_bug
hybrid_p_production_qualified
full3d_fallback_is_hybrid_success
```

Full3D reference 必须通过 SHA-256、源码、incidence、九项 direct-projection Gate 和
raw/solver payload 等价检查；nonzero-phi reference 不再被错误硬编码成旧 theta/phi
身份。没有放宽任何数值 Gate，也没有提高默认 M。

### after

- F2 与 F5 Full3D p4/h10/P static 均为 `full3d_reference_pass`，true residual 分别
  `5.6680e-13`、`9.9620e-13`，能量闭合约 `7e-13`；
- 对应 Hybrid M120 均记录
  `status=hybrid_modal_rank_insufficient`、
  `full3d_physical_solution_exists=true`、
  `diagnostic_projection_bug=false`、
  `hybrid_p_production_qualified=false`；
- F2/F5 Hybrid energy closure 分别为 `1.00994e-3` 与 `2.56646e-5`，均超过
  `1e-5` Gate，因此没有被 reciprocal/traction 的代数通过误写为物理成功。

### regression scope

四类 disposition、Full3D fallback 身份、F2/F5 P static MPI8、原通过 conical S
ordinary-default control。

### remaining limitation

Hybrid-P 的新模态架构是 `DEFERRED_ARCHITECTURE_REQUIRED`；Task036 只保证它安全
拒绝，不声称已使其 production-qualified。当前 runner 对 P 的 modal-rank 判定仍
采用保守 false，因此能安全 quarantine，但还不能细分“rank 已足而仅
interface/energy 失败”的情况。

### status

`FAIL_CLOSED`

### evidence

```text
benchmarks/artifacts/task036/393b7c583c40bea17d4ceca6440c140317e0b60c/20260730T110213Z/w3_full3d_f2_p4h10_0p5_phi0_p_static/run/watchdog_summary.json
benchmarks/artifacts/task036/393b7c583c40bea17d4ceca6440c140317e0b60c/20260730T110213Z/w3_full3d_f5_p4h10_10_phi90_p_static/run/watchdog_summary.json
benchmarks/artifacts/task036/9de46581fa47ea02295d73688d30a55a38c01a91/20260730T122723Z_reciprocal_basis_batch_v1/b1_f2_m120_p_static/solver_record.json
benchmarks/artifacts/task036/9de46581fa47ea02295d73688d30a55a38c01a91/20260730T122723Z_reciprocal_basis_batch_v1/b1_f5_m120_p_static/solver_record.json
benchmarks/artifacts/task036/9de46581fa47ea02295d73688d30a55a38c01a91/20260730T122723Z_reciprocal_basis_batch_v1/b1_conical_s_m120_standard_ordinary/solver_record.json
```

## 8. B06：near-degenerate mode blocks 不得错误拆分

### before

p6/45° 的相邻近简并 blocks 被分别归一化；block 内通过，但全局交叉 overlap/整行
identity error 超过 `1e-6`。旧路径可能只看局部 block，或只看单个最大 entry。

### root cause

几乎同 beta 的模态张成一个共同子空间，独立旋转每个小 block 会留下交叉误差。
而且多个小 entry 会在同一行累积，所以只检查最大 entry 不足以保护全局单位矩阵。

### changed files

```text
src/modes/mode_classification.py
src/modes/quadratic_beta_eigenproblem.py
benchmarks/run_task032_phase6_augmented.py
src/test/test_33_task032_mode_classification.py
src/test/test_79_task034_native_full3d_reference.py
```

### minimal fix

1. 每次归一化后审计完整 `||B-I||_inf`、最大 entry、cross-block pair、beta 距离和
   group provenance；
2. 仅显式 opt-in、scalar `stage4_xy`、同方向、union 不超过 4 个 mode 时，允许
   **最多一次** joint left-basis inverse；右模态和 beta 不改；
3. condition 超限、候选不符合边界，或修复后任一完整 Gate 仍失败，立即在 Hybrid
   solve 前拒绝；
4. `1e-6` Gate 保持不变。

### after

旧 SHA 的 p6/45° anchor 在 solve 前确定性拒绝：

```text
max cross-block overlap = 1.6202694892e-6
relative beta distance  = 1.4142290610e-6
status                  = near_degenerate_block_partition_split
```

新 SHA 的 F1/M40 尝试了一次合法的四-mode joint inverse：

```text
initial row norm        = 5.6156478455e-6
initial max cross       = 3.7051879064e-6
joint condition         = 1.0000066834
final max cross         = 2.3680383753e-7
final full row norm     = 1.0494079425e-6  > 1e-6
```

虽然单个最大交叉项已低于 Gate，整行累积仍超限，因此结果被正确保存为
`cross_block_biorthogonality_failure`，没有进入 PDE。这是 **bounded repair
controlled negative**，不得改写成修复成功。

F1/M120 opt-in reciprocal 路径可以通过本轮全部 basis Gate，但不改变 M40 负结果，
也不证明所有角度、degree 和截断 M 的 near-degenerate 问题已经解决。

最终 source `bb0e5e3...` 先生成同 source、同 grazing `10°`（theta `80°`）、
phi `45°` 的 Full3D p6/h10
authority；它以 true residual `1.681162353e-11`、energy closure
`2.011280031e-12`、direct projection `7.493344842e-13`、同步峰值
`15.400711 GiB` 和 zero swap 通过。对应 Hybrid M120 随后得到：

```text
initial full row norm  = 2.2073452529e-6
initial max cross     = 1.6293443792e-6
repaired group        = [114, 115, 116, 117]
joint condition       = 1.0000020721
final max cross       = 6.9628686655e-7
final full row norm   = 1.0333656795e-6  > 1e-6
new worst groups      = [96, 97] / [98, 99]
```

该 Hybrid 明确设置
`task036_scalar_stage4_reciprocal_basis_requested=true`，属于
`research_only / not_production` opt-in。一次合法 repair 已耗尽；虽然最大单项
通过，完整 row norm 仍超限，因此在 Hybrid solve 前以顶层
`near_degenerate_block_partition_split` 停止，并记录
`mode_partition_stop_disposition=bounded_repair_exhausted`。这条 final-source
实测正式闭合了 p6/45° 回归证据链，但结论仍是 controlled negative，而不是
production 成功。

### regression scope

synthetic split detector、row-norm 累积反例、bounded candidate policy、condition
拒绝、joint inverse 单元测试、p6/45° actual guard、F1/M40 actual bounded negative。

### remaining limitation

通用 block continuation/joint subspace rotation 仍是
`DEFERRED_ARCHITECTURE_REQUIRED`。Task036 已完成的是可靠检测和受限局部修复，
不是通用模态架构。

### status

`FAIL_CLOSED`

### evidence

```text
benchmarks/artifacts/task036/393b7c583c40bea17d4ceca6440c140317e0b60c/20260730T110213Z/w3_p6_phi45_near_degenerate_guard/solver_record.json
benchmarks/artifacts/task036/393b7c583c40bea17d4ceca6440c140317e0b60c/20260730T110213Z/w3_f1_m40_s_standard/solver_record.json
benchmarks/artifacts/task036/393b7c583c40bea17d4ceca6440c140317e0b60c/20260730T110213Z/w3_f1_m40_s_static/solver_record.json
benchmarks/artifacts/task036/9de46581fa47ea02295d73688d30a55a38c01a91/20260730T122723Z_reciprocal_basis_batch_v1/b1_f1_m40_s_standard/solver_record.json
benchmarks/artifacts/task036/bb0e5e3e385586e137d861cf0a53a142e4fe0fe0/b06_p6phi45_final_source_v1/full3d/run/watchdog_summary.json
benchmarks/artifacts/task036/bb0e5e3e385586e137d861cf0a53a142e4fe0fe0/b06_p6phi45_final_source_v1/hybrid/solver_record.json
```

## 9. B07：y 向 trace alias 在 bulk solve 前识别

### before

Ny3 在 `2*ky≈3*Gy` 附近把物理 `n=0` 与 `n=-3` trace 混合，历史泄漏功率约
`1.2312e-6`、最大幅值约 `1.0147e-3`。提高 surface quadrature 不改变结果。

### root cause

这是网格诱发的离散 Bragg/trace alias，不是 quadrature 随机误差，也不是求解器
残差问题。沿 y 不变的连续模型仍可能被过粗的离散 trace space污染。

### changed files

```text
src/common/config_3d.py
src/geometry/mesh_builder_3d.py
src/solvers/dtn_port_3d.py
src/solvers/hybrid_local_dtn.py
benchmarks/run_task033_full3d_watchdog.py
benchmarks/run_task032_phase6_augmented.py
src/test/test_14_stage4_dtn_modes.py
src/test/test_68_task033_full3d_watchdog.py
src/test/test_181_task035c_p6_h10_runner_gates.py
```

### minimal fix

ordinary-default-off 的 y-invariant/n0 preflight 使用**实际 MPC-reduced tangential
surface functional**计算 n0 与 relevant n!=0 的归一化 overlap；planned/actual
axis counts 不一致也拒绝。阈值固定 `1e-8`，超限时要求 refinement，不放宽后验
leakage Gate。

### after

Ny3：

```text
maximum normalized overlap = 0.9171201301
limit                      = 1e-8
worst pair                 = top (m=-2,n=0,P) / (m=-2,n=-3,P)
status                     = task036_dtn_trace_alias_controlled_negative
PDE solve                  = not entered
```

Ny4 同物理点完成 MPI8 Full3D p5 static：

```text
status             = full3d_reference_pass
true residual      = 2.8602331154e-11
energy closure     = 1.4730439091e-12
max n!=0 power     = 8.3769540111e-26
sum n!=0 power     = 7.1163695354e-25
max n!=0 amplitude = 1.7579865826e-13
swap               = 0
```

### regression scope

axis-count mismatch、overlap helper、Ny3 controlled rejection、Ny4 actual solve 与
official n!=0 power/amplitude。

### remaining limitation

防护仅在调用者明确声明 y-invariant/fixed-n0 时启用；ordinary general diffraction
运行不被静默改写。

### status

`FIXED`

### evidence

```text
benchmarks/artifacts/task036/393b7c583c40bea17d4ceca6440c140317e0b60c/20260730T110213Z/w2_ny3_alias_controlled_negative/run/dtn_trace_alias_preflight.json
benchmarks/artifacts/task036/393b7c583c40bea17d4ceca6440c140317e0b60c/20260730T110213Z/w2_ny3_alias_controlled_negative/run/watchdog_summary.json
benchmarks/artifacts/task036/393b7c583c40bea17d4ceca6440c140317e0b60c/20260730T110213Z/w2_ny4_alias_pass/run/watchdog_summary.json
benchmarks/artifacts/task036/393b7c583c40bea17d4ceca6440c140317e0b60c/20260730T110213Z/w2_ny4_alias_pass/run/dtn_port_diffraction_orders_3d.json
```

## 10. B08：MUMPS factor NNZ 的 int32 overflow

### before

p6/h5 的 PETSc raw factor NNZ 为 `-2017967296`，MUMPS `INFOG(9)=-2277`。
负数进入 fill 或资源模型会产生无意义结果。

### root cause

PETSc 的旧遥测字段发生 32-bit overflow；MUMPS 用负的“百万 entries”为单位表达
超大计数。两种 raw 值都需要保留，但正式资源计算必须用 Python 64-bit-safe `int`。

### changed files

```text
src/solvers/common_3d_solve.py
src/adaptivity/high_order_resource_audit.py
src/adaptivity/high_order_same_error.py
benchmarks/run_direct_memory_forensics.py
src/test/test_195_task036_mumps_factor_nnz.py
src/test/test_70_task033_reduced_equal_accuracy.py
```

### minimal fix

仅当 solver 是 MUMPS 且 `INFOG(9)<0` 时生成：

```text
factor_nnz_corrected = abs(INFOG(9)) * 1_000_000
factor_nnz_corrected_source = mumps_infog_9_negative_millions
```

raw PETSc/INFOG 不覆盖；fill 与资源 consumer 优先 corrected count。正 MUMPS 值和
非 MUMPS solver 不套用该规则。

### after

历史 p6/h5 被正确解释为：

```text
factor_nnz_corrected = 2,277,000,000
type                 = Python int
value > 2^31         = true
```

资源审计和 same-error/forensics consumer 不再用负 NNZ 计算比率。

### regression scope

真实 overflow 值、正 `INFOG(9)`、非 MUMPS、raw 值保留、fill 与 storage ratio
consumer。

### remaining limitation

这是遥测解释修复，不改变 MUMPS factor 本身，也没有重跑 p6/h5 PDE。

### status

`FIXED`

### evidence

```text
docs/task035e_reference_blind_multilevel_hp_adaptivity/README.md
docs/development_model_registry.md
src/test/test_195_task036_mumps_factor_nnz.py
```

## 11. B09：solver 对象生命周期不叠加到 field output

### before

Full3D 已有释放路径，但 Hybrid factor、system matrix、RHS/solution handles 可能
保留到 physical reconstruction 或记录末尾，使本来已不用的直接法对象和 field
output 同时驻留。

### root cause

对象所有权与“最后一次需要 factor 的回代”没有形成明确生命周期；另外
`malloc_trim(0)==0` 曾可能被误读为调用失败。

### changed files

```text
src/solvers/common_3d_utils.py
src/solvers/common_3d_case_flow.py
src/solvers/hybrid_fem_modal_augmented_direct.py
src/solvers/hybrid_fem_modal_schur_direct.py
benchmarks/run_task032_phase6_augmented.py
src/test/test_196_task036_forward_solver_hardening.py
```

### minimal fix

完成 field recovery、true residual、factor inventory 和必要回代后，复制后处理所需
标量/向量，再幂等销毁 KSP/MUMPS factor、system matrix 和 RHS；销毁后的 handle
置 `None` 防 use-after-destroy。`malloc_trim` 把“调用完成”和“allocator 实际归还
页”分开记录，return 0 不是数值失败。

### after

新 Hybrid 记录均有
`release_before_field_output=true`，列出 released/retained objects。以 F1 standard
为例，各 rank 的 phase-local current RSS 从约 `406.1–456.2 MiB` 降至
`280.2–298.7 MiB`。该下降只证明生命周期释放发生；记录也明确写明它是进程内
阶段采样，**不是同步 process-tree 内存 authority，更不是矩阵结构压缩。**

### regression scope

Full3D lifecycle 回归、Hybrid release 幂等、destroy 清空 factor handles、
`malloc_trim(0)`、F1/F2/F5/conical actual Hybrid。

### remaining limitation

Task036 没有处理 Hybrid replicated `M^2`、all-mode multi-RHS 或 local LU 的结构
内存；这些仍是后续技术债。

### status

`FIXED`

### evidence

```text
benchmarks/artifacts/task036/9de46581fa47ea02295d73688d30a55a38c01a91/20260730T122723Z_reciprocal_basis_batch_v1/b1_f1_m120_s_standard/solver_record.json
benchmarks/artifacts/task036/9de46581fa47ea02295d73688d30a55a38c01a91/20260730T122723Z_reciprocal_basis_batch_v1/b1_f1_m120_s_static/solver_record.json
benchmarks/artifacts/task036/9de46581fa47ea02295d73688d30a55a38c01a91/20260730T122723Z_reciprocal_basis_batch_v1/b1_f2_m120_p_static/solver_record.json
benchmarks/artifacts/task036/9de46581fa47ea02295d73688d30a55a38c01a91/20260730T122723Z_reciprocal_basis_batch_v1/b1_f5_m120_p_static/solver_record.json
benchmarks/artifacts/task036/9de46581fa47ea02295d73688d30a55a38c01a91/20260730T122723Z_reciprocal_basis_batch_v1/b1_conical_s_m120_standard_ordinary/solver_record.json
```

## 12. B10：内存 authority 与 MPI identity 语义

### before

日志可能把各 rank 不同时间的 historical peak 之和简写成 total peak RSS；某些
MPI identity 路径也可能读取随 partition 变化的 raw vector bytes/hash。

### root cause

“每个 rank 曾经达到过多少”与“同一时刻整作业用了多少”是不同量；分区后的原始
向量字节也不是物理不变量。

### changed files

```text
src/solvers/common_3d_utils.py
src/solvers/common_3d_case_flow.py
benchmarks/run_task033_full3d_watchdog.py
benchmarks/run_task033_memory_watchdog.py
benchmarks/task034_mpi_identity.py
src/test/test_196_task036_forward_solver_hardening.py
src/test/test_80_task034_mpi_identity.py
```

### minimal fix

无同步 sampler 时只写 `sum_rank_historical_peaks_mb_upper_bound`；日志不再称它为
total peak。存在 watchdog sampler 时，以同一采样时刻的 process-tree RSS 和
完整 rank `smaps_rollup` PSS/USS/swap 为 authority。MPI 物理 identity 使用 topology、
phase、constraint count、residual 和 canonical entity hash，不使用 partition-sensitive
raw vector hash。

### after

四个 Full3D MPI8 代表点的同步 authority：

| 点 | process-tree RSS GiB | simultaneous PSS MiB | simultaneous USS MiB | swap |
|---|---:|---:|---:|---:|
| p2/h5 S standard | `3.012226` | `2027.248` | `1972.594` | 0 |
| p4/h10 P static | `4.535061` | `3408.848` | `3186.355` | 0 |
| p6/h10 S static | `15.566528` | `13905.693` | `13359.363` | 0 |
| Ny4 p5 static | `10.581425` | `9250.438` | `8747.688` | 0 |

Hybrid records没有外部同步 sampler，只报告
`per-rank ru_maxrss historical peaks; not simultaneous RSS`。本文不把这些 rank
峰值相加成 Hybrid 整作业内存。

### regression scope

日志标签、optional rank collective、同步/历史口径隔离、MPI identity scope 和
实际 Full3D watchdog records。

### remaining limitation

没有为 Hybrid 新建 telemetry framework；缺少同步 sampler 的 Hybrid run 仍只能
给 historical 口径。

### status

`FIXED`

### evidence

```text
benchmarks/artifacts/task036/393b7c583c40bea17d4ceca6440c140317e0b60c/20260730T110213Z/w1_full3d_p2h5_s_standard_retry1/run/watchdog_summary.json
benchmarks/artifacts/task036/393b7c583c40bea17d4ceca6440c140317e0b60c/20260730T110213Z/w1_full3d_p4h10_p_static_retry1/run/watchdog_summary.json
benchmarks/artifacts/task036/393b7c583c40bea17d4ceca6440c140317e0b60c/20260730T110213Z/w1_full3d_p6h10_s_static_anchor_retry1/run/watchdog_summary.json
benchmarks/artifacts/task036/393b7c583c40bea17d4ceca6440c140317e0b60c/20260730T110213Z/w2_ny4_alias_pass/run/watchdog_summary.json
benchmarks/artifacts/task036/9de46581fa47ea02295d73688d30a55a38c01a91/20260730T122723Z_reciprocal_basis_batch_v1/b1_conical_s_m120_standard_ordinary/solver_record.json
benchmarks/artifacts/task036/9de46581fa47ea02295d73688d30a55a38c01a91/20260730T122723Z_reciprocal_basis_batch_v1/b1_f1_m120_s_standard/solver_record.json
benchmarks/artifacts/task036/9de46581fa47ea02295d73688d30a55a38c01a91/20260730T122723Z_reciprocal_basis_batch_v1/b1_f1_m120_s_static/solver_record.json
benchmarks/artifacts/task036/9de46581fa47ea02295d73688d30a55a38c01a91/20260730T122723Z_reciprocal_basis_batch_v1/b1_f1_m40_s_standard/solver_record.json
benchmarks/artifacts/task036/9de46581fa47ea02295d73688d30a55a38c01a91/20260730T122723Z_reciprocal_basis_batch_v1/b1_f2_m120_p_static/solver_record.json
benchmarks/artifacts/task036/9de46581fa47ea02295d73688d30a55a38c01a91/20260730T122723Z_reciprocal_basis_batch_v1/b1_f5_m120_p_static/solver_record.json
```

## 13. B11：active DoF、storage carrier 与 matrix rows 分离

### before

variable-p 或 static-condensed 记录可能只给 `num_nedelec_dofs` 或
`num_active_condensed_dofs`，无法判断这是物理 active space、统一 p6 carrier，
还是实际求解矩阵行数。

### root cause

“保存系数的容器”“真正启用的有限元自由度”“消元后保留的 trace unknown”
和“加上 DtN auxiliary 后实际送入求解器的 rows”是四个不同对象。

### changed files

```text
src/solvers/dtn_port_3d.py
src/solvers/common_3d_case_flow.py
src/solvers/hcurl_assembly_time_condensation.py
src/test/test_115_task035b_assembly_time_condensation.py
src/test/test_190_task035d_variable_p_stage4_smoke.py
src/test/test_192_task035d_mixed_variable_p_stage4.py
src/test/test_196_task036_forward_solver_hardening.py
```

### minimal fix

保留旧字段兼容，同时增加并校验：

```text
num_active_exact_sequence_fe_dofs
num_storage_carrier_fe_dofs
num_independent_trace_rows
num_augmented_rows
dof_row_semantics
```

校验 `active <= carrier`，并要求
`augmented rows = independent trace rows + auxiliary rows`（相应 reduction 激活时）。

### after

正式 record 示例：

| 点 | active FE DoF | carrier DoF | independent trace rows | augmented rows |
|---|---:|---:|---:|---:|
| p2/h5 standard | 44,698 | 44,698 | N/A | 44,778 |
| p4/h10 static | 53,084 | 53,084 | 21,744 | 21,824 |
| p6/h10 static | 173,802 | 173,802 | 51,192 | 51,272 |

variable-p、p5-trace/p6-interior 与 selective-trace fixtures 另行覆盖
`active < carrier` 的真正混合阶情形。

### regression scope

字段关系、非法 active/carrier、非法 augmented row identity、standard/static、
p5-trace/p6-interior 和 selective trace。

### remaining limitation

这些字段修正报告语义，不声称 static condensation 改变了原始 FE approximation
space，也不用 Full3D-equivalent DoF 代替实际 rows。

### status

`FIXED`

### evidence

```text
benchmarks/artifacts/task036/393b7c583c40bea17d4ceca6440c140317e0b60c/20260730T110213Z/w1_full3d_p2h5_s_standard_retry1/run/run_summary.json
benchmarks/artifacts/task036/393b7c583c40bea17d4ceca6440c140317e0b60c/20260730T110213Z/w1_full3d_p4h10_p_static_retry1/run/run_summary.json
benchmarks/artifacts/task036/393b7c583c40bea17d4ceca6440c140317e0b60c/20260730T110213Z/w1_full3d_p6h10_s_static_anchor_retry1/run/run_summary.json
```

## 14. 明确未解决与不应误读的边界

1. **Hybrid-P 仍未 production-qualified。** Full3D-P 通过只证明物理解存在；F2/F5
   Hybrid 的 modal-rank/field/energy 失败保持原样。
2. **M40 bounded repair 是负结果。** 最大单 entry 下降不等于完整 row-norm 通过；
   本轮正确停止，没有放宽 `1e-6`。
3. **sampled traction proxy 不是正式失败。** formal authority 是 exact
   `traction_hcurl_dual`；反过来也不能用 sampled proxy 通过来覆盖 exact dual 失败。
4. **Hybrid historical RSS 不是同步内存。** 本报告只对 Full3D watchdog 点给出
   process-tree/PSS/USS authority。
5. **p6/h5 没有重跑。** `2,277,000,000` 是对已有 raw MUMPS telemetry 的通用、
   单元测试覆盖的解释修复。
6. **ordinary default 未改变。** reciprocal basis、Ny alias preflight 和 Task036
   formal audit 均为显式 opt-in；conical ordinary S control 使用独立正负 QEP 并通过。
7. 下列内容继续是后续技术债，不在 Task036 展开：
   Hybrid-P 新模态架构、通用 near-degenerate continuation、replicated `M^2`、
   all-mode multi-RHS、global allgather、迭代求解器、h/p controller 和 surrogate。
8. **增加 M 已关闭。** A049-P 的 M120→M492 平台没有修复物理界面跳跃，M492
   约 19.405 GiB 反而高于约 10.161 GiB 的 Full3D。后续 Hybrid 架构必须把 M120
   作为硬上限，并通过强 trace-subspace elimination 消除未约束补空间；若 M120
   仍不能通过则 fail closed。
