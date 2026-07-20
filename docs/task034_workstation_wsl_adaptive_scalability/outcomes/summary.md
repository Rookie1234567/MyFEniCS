# Task034 最终成果汇总

## Final status / scope

| 字段 | 结论 | 数据身份 / evidence |
|---|---|---|
| final status | `PASS_WITH_QUALIFICATIONS` | 本任务所有阶段获得正式 decision；受控物理/资源 negatives 保留 |
| primary scope | S polarization | 用户批准 reduced scope |
| P capability | p2/h5 MPI8 Full3D + Hybrid M160 可计算 | `phase_f_p2_h5_p_capability_partial.md` |
| excluded | p1；重型 P 矩阵 | user-approved，不冒充 not-run pass |
| base | `82a5107b5c2bfe4c466a0d00ead31d7b172e2af4` | `environment_and_base.md` |
| ordinary default | unchanged | `post_merge_hardening_audit.md` |
| master merge | 未执行 | 等待 ChatGPT review / selective merge |

## WSL environment matrix

| OS/stack | MPI | memory/swap | 结果 | evidence |
|---|---|---|---|---|
| Ubuntu 24.04；Python 3.12.3；DOLFINx 0.10.0.post2；PETSc/SLEPc 3.19.x complex | 1/2/4/8/16 formal；32 exploratory | 228 GiB / 32 GiB；正式作业 job swap=0 | qualified | `wsl_environment_qualification.md` |

## Hardening issue matrix

| issue | 状态 | 主要证据 |
|---|---|---|
| Floquet cache ownership/lifecycle | closed | weak owner + explicit clear tests |
| Python active-column allgather | closed | numeric distributed reduction + MPI tests |
| WSL memory/swap authority | closed | process-tree/cgroup watchdog tests |
| full source-clean semantics | closed | tracked + nonignored untracked fail closed |
| evidence-to-current numerical blobs | pass | `numerical_blob_compatibility.json` |

## Task033 reproduction matrix

单位：h 为 nm，memory 为 GiB；baseline 为 Task033 p3 anchors；环境 `task034-wsl-ubuntu-24.04-native`。

| p/h | Full3D R/T/A_volume | Hybrid M160 R/T/A_volume | max abs R/T/A_volume delta | true residual F/H | 结果 / evidence |
|---|---|---|---:|---|---|
| p3/h7.5 | .003090727/.591160863/.405748409 | .003090647/.591159679/.405749673 | `1.264e-6` | `7.682e-12 / 3.164e-12` | pass / `wsl_anchor_summary.json` |
| p3/h5 | .001090107/.600622478/.398287415 | .001090096/.600622368/.398287536 | `1.214e-7` | `6.982e-12 / 1.055e-11` | pass / `wsl_anchor_summary.json` |

## p2/p3/p4 uniform convergence matrix

单位 h=nm；baseline 是冻结 physical identity `abb8613b...`；MPI8 S；source/evidence 在 Case093 `convergence_summary.json`。

| p | 成功 Full3D+Hybrid M160 的 h | 相邻 12 分量差全部下降 | canonical anchor | 结论 |
|---:|---|---|---|---|
| 2 | 5, 3, 2 | yes | p2/h2 | measured sequence；非 continuum proof |
| 3 | 7.5, 5, 3 | yes | p3/h3 | measured sequence；p3/h10 Hybrid negative 保留 |
| 4 | 10, 7.5, 5 | yes | p4/h5 | measured sequence；非 continuum proof |

新增 p2/h1、p3/h2、p4/h3 的 Full3D 均在 assembly 后按 factorization 上界受控停止；p3/h2 和 p4/h3 Hybrid M160 pass，p2/h1 Hybrid field recovery timeout negative。详见 `fixed_geometry_ph_convergence.md/csv`。

## Full3D vs Hybrid same-degree closure matrix

| anchor | Full3D staged Gate | Hybrid funnel | same-degree closure | data identity / evidence |
|---|---|---|---|---|
| p3/h3 S | assembly/factor/full pass；39.122 GiB | M80/120/160；M160 selected | 16 gates pass | `p3_h3_reference_summary.json` |
| p4/h5 S | assembly/factor/full pass；26.786 GiB | M80/120/160；M160 selected | 16 gates pass | `p4_h5_workstation_summary.json` |
| Case093 successful anchors | full true residual pass | M160 | closure pass | `convergence_summary.json` |

## MPI1/MPI8/MPI16 identity and resource matrix

baseline：p3/h5 S；同一方法内 clean SHA；单位 ranks；evidence `mpi_identity_summary.json`。

| method | MPI1 | MPI8 | MPI16 | MPI32 | 结论 |
|---|---|---|---|---|---|
| Full3D | pass | pass | pass | exploratory pass | numerical identity qualified |
| Hybrid M160 | pass | pass | pass | exploratory pass | numerical identity qualified |

## p3/h3 与 p4 staged results

| case | assembly | factorization | full solve | official result | evidence |
|---|---|---|---|---|---|
| p3/h3 Full3D | 19.167 GiB / 778.96 s | 40.667 GiB / 2259.35 s | 39.122 GiB / 2281.13 s | residual `6.967e-11`，R/T/A=.000789468/.602514984/.396695548 | `p3_h3_reference_and_reranking.md` |
| p4/h5 Full3D | 19.414 GiB / 1242.21 s | 27.049 GiB / 1712.71 s | 26.786 GiB / 1701.84 s | residual `3.354e-11`，R/T/A=.000766313/.602677531/.396556156 | `p4_h5_workstation_study.md` |

p3/h7.5 相对新的 p3/h3 finer discrete reference 仍逐项不劣于 p2/h3 baseline（worst ratio 0.8991）；p4/h5 相对 p3/h5 有清晰工程精度收益。两者均不升级为 continuum reference。

## Adaptive / equal-accuracy / compression matrix

baseline：uniform p2/h3 Full3D；MPI8 S；M160；单位 memory=GiB、wall=s；evidence `adaptive_compression.json`。

| profile | elements | raw DoF reduction | memory | wall | max abs R/T/A delta | field/interface 主要结果 | 正式分类 |
|---|---:|---:|---:|---:|---:|---|---|
| conservative | 3978 | 1.561x | 3.964 | 112.115 | 0.01699 | middle E/H 0.306/0.315 | physical negative |
| balanced | 1885 | 3.172x | 3.292 | 96.633 | 0.1896 | middle E/H 1.673/1.672 | physical negative |
| aggressive | 600 | 9.590x | 2.537 | 71.917 | 0.9568 | interface H ~0.126 fails | physical negative |

三组 M120→M160 modal observable 均收敛 `<1e-5`，但没有一组通过 fixed same-error physical thresholds。因此 DoF 减少只记 raw reduction，不称 qualified compression；critical observable stop condition 阻止 genuine adaptive/common-mesh/p3 adaptive 重型扩展。首次 aggressive M80 的 WSL/MPI 空输出失败和同参数 retry pass 均保留。

## Resource model v2 / 0.7 nm

| wavelength | predicted peak | 256 GiB | 1 TiB | 2 TiB | evidence |
|---:|---:|---|---|---|---|
| 13.5 nm | 4.695 GiB calibrated | feasible | feasible | feasible | `resource_model_v2.json` |
| 5 nm | 201.533 GiB | high-risk | feasible with guardband | feasible | same |
| 2 nm | 13,225.875 GiB | infeasible | infeasible | infeasible | same |
| 1 nm | 358,034.098 GiB | infeasible | infeasible | infeasible | same |
| 0.7 nm | 2,014,975.394 GiB | infeasible | infeasible | infeasible | same |

0.7 nm 的 local direct factor 约 198,690 GiB，modal/dense multi-RHS 约 1,747,721 GiB；不是单一局部 FEM 或单一 modal 问题。相对 256/1024/2048 GiB 的 joint compression 下界分别约 7871x/1968x/984x，当前架构必须同时重构 local factorization 与 modal dense core。

## Failures / not-run / merge decision

| 项 | 原因 | 处理 |
|---|---|---|
| p3/h10 Hybrid | formal numerical negative | 保留，不用于 canonical positive |
| p2/h1/p3h2/p4h3 Full3D | factorization resource upper bound | controlled stop，未进入 solve |
| adaptive profiles | same-error physical Gate fail | 保留 negative，停止扩展 |
| P heavy matrix / p1 | user-approved reduced scope | not_run，不列 pass |
| M240 | M120→M160 strong Gate 已过 | condition not triggered |
| current 0.7 nm | 多组件远超预算 | infeasible，不放宽模型 |

selective merge 以 `selective_merge_manifest.csv` 为唯一逐文件建议：稳定 hardening、tests、轻量 checker/records 可审查合入；未通过或研究性的 adaptive/resource/solver 路径默认留在 Task034 分支。

## 下一任务建议

优先把 conservative graded-h 的误差来源拆成 interface、absorbing-region 与 grating-neighborhood 三个局部预算，用 goal-oriented indicator 做小规模验证；在任何更重 adaptive 前先证明至少一个 profile 通过同误差 Gate。0.7 nm 另立架构任务，分别研究 sparse/distributed local solve 与 matrix-free/low-rank modal multi-RHS，禁止用单侧压缩外推可行性。
