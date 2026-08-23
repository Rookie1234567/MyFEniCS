# Review V7 response：L0–L2 closeout

本文是 Review V7 的文档收口，按 §15.4 逐项回答。首次术语说明：**positive auxiliary contraction** 是在一个正定辅助算子上做一次固定预条件修正，并检查残差是否按合同下降；它不是物理 Maxwell 求解。**hard stop** 是达到冻结 Gate 后停止后续阶段，表示该路线在本次证据链中没有资格继续，不代表所有其他物理算子都失败。

## 总结矩阵

| 阶段 | 结果 | 证据边界 |
|---|---|---|
| L0 | `PASS` | qualified complex PETSc ABI、tiny PCGAMG capability、容量审计按 V7 通过；预算不是本次 L2 RSS 测量 |
| L1 | `PASS` | 五案 transfer/de Rham/orientation/Floquet/MPI oracle aggregate 通过 |
| L2 | `FAIL / HARD STOP` | `p2-mpi1/random` 独立重算 `rho=1.7348663090876784 > 0.45` |
| L3 | `not_run_by_L2_gate` | p6/h10 cold setup 未运行 |
| L4 | `not_run_by_L2_gate` | exact-A 五 source 未运行 |
| L5 | `not_run_by_L2_gate` | 20/100/150/200 screen 未运行 |

## Review V7 §15.4 逐项回答

| # | 问题 | 回答与证据 |
|---:|---|---|
| 1 | branch、HEAD、base、upstream、ahead/behind、worktree、ABI | branch=`codex/20260820-task38-extra-full3d-iterative-0p7nm`；L2 source HEAD=`91992c0ac3aa467f74955fa7da944a10da8f0fbb`；base/merge-base=`438caf150439343ee7c4c58ad7e02a3da812a23c`；upstream=`origin/codex/20260820-task38-extra-full3d-iterative-0p7nm`，upstream SHA=`6006034e19c0dcf32a874bf9f074db8d85b868cb`，ahead/behind=`11/0`。formal start worktree clean；formal 后仅新增两个 untracked compact JSON，代码未改。qualified activation=`1`，PETSc complex128/int32，线程 OMP/OpenBLAS/MKL 均为 1；resolved qualified bin 为 `/home/shenjh/Projects/MyFEniCS-Surrogate/.venv/bin`。本文件不自引用最终 docs commit，final SHA 以交付报告为准。 |
| 2 | FC1/FC3 和 closed families 是否保持原样 | 保持。FC1 scoped pass、FC3 controlled resource negative、旧 N2 v1/v2、LA/v3 evidence、Candidate/trace-harmonic/local-spectral closed families均未删除、覆盖或重分类。FC3 不重跑，旧负证据仍 do-not-merge。 |
| 3 | Task011/013/014a/023/024 历史差异审计 | L0 inherited audit 保留这些历史边界：Task011 direct complex hypre AMS、Task013 real-split、Task014a reduced FE-AMS/aux、Task023 response service、Task024 large FE response；本 lane 采用 native complex PETSc + refined lowest-order de Rham auxiliary，不整体迁移旧源码。V7 本轮未重跑这些历史方法。 |
| 4 | L0 PCGAMG complex tiny smoke 和实际 PC tree | L0 已 PASS：`PCGAMG(agg)` 可用，tiny observed levels=`2`，冻结 maximum levels=`8`；coarse KSP=`preonly`、coarse PC=`jacobi`，无 direct factor。L2 record 的 HX audit继续闭合 one shared scalar hierarchy、one V-cycle per nodal correction、omega=`2/3`；该事实不抵消 L2 rho Gate。 |
| 5 | LOR exact topology counts 与完整容量账本 | L1 p2/p3/p6 single-cell transfer 已 PASS。L2 p2 fixture facts为 high rows=`988`、LOR cells=`240`、full LOR edge rows=`988`、full LOR node rows=`385`、de Rham metadata=`32,604 B`；piecewise positive coefficients与 slave/master completeness均有 record。p6/h10 full inventory、完整 hierarchy live-set、L3 retained/cold ledger未运行，不能从小 fixture冒充。L0 budget仍是预算审计，不是 L2 process-tree 测量。 |
| 6 | high↔LOR transfer、commuting、orientation、Floquet、MPI identity | L1 aggregate `lor_transfer_oracle_v1.json`：source=`08df08ab61a364b933d2d3d6e79a394d7ee1dd4e`，SHA=`3ba0a3e4d9feca725d426913b4b0d1ffb580d57b16334180c6d272ec3aabbd39`，五案通过。p2/p3 六项跨 MPI 均 `<=1e-12`，p6 spectral=`15.133589067492856 <=21.481695769715852`。这些是 L1 transfer/oracle 结果，不是 L2 contraction 通过。 |
| 7 | local spectral equivalence 区间 | L1 diagnostic condition 为 p2=`9.454227208854832`、p3=`10.740847884857926`、p6 single-cell=`15.133589067492856`，跨 degree limit=`21.481695769715852`，在 L1 scope 内通过。它不是 L2 HX contraction 或 p6/h10 hierarchy 的 spectral equivalence 证明。 |
| 8 | L2 positive auxiliary contraction 与 PCG iterations | 正式首案 `p2-mpi1` 的 random residual norm=`583.0377018610059`，独立 checker 重算 `rho=1.7348663090876784`，limit=`0.45`，失败。finite/input unchanged/repeat=`true/true/0`；其余 source、CG reason/iterations/true residual均 `not_run_by_gate`。因此 L2=`CONTROLLED_NEGATIVE_BY_POSITIVE_AUXILIARY_CONTRACTION_GATE`。 |
| 9 | L3 p6/h10 cold peak、retained、hierarchy inventory、forbidden audit | `not_run_by_L2_gate`。没有 p6/h10 cold peak、post-setup retained、hierarchy inventory 或 L3 resource Gate；不能把 L2 单进程 `137,695,232 B`写成 p6/process-tree qualification。 |
| 10 | L4 五 source rho、repeat 和资源 | `not_run_by_L2_gate`。L2 使用的是 positive `B_h`，没有构造 exact physical `A=T2+T3 DtN`，所以没有 exact-A rho、repeat 或 L4 resource 结果。 |
| 11 | L5 20/100/150/200 true residual、wall 和资源 | `not_run_by_L2_gate`。四个 checkpoint、FGMRES history、matvec/PC count、wall 和 process-tree/swap 均无结果。 |
| 12 | measured/derived/budget/failed/controlled_stop/not_run 分类 | L2 `rho`、record/aggregate SHA、marker ledger 和 `/usr/bin/time` 单进程 RSS/wall/swap 是 measured；L0 capacity 是 budget/derived；L2 random rho 是 failed Gate；worker 按固定 control flow early stop，后续 case/source 是 controlled `not_run_by_gate`；L3–L5 是 `not_run_by_L2_gate`；没有用未测值补 PASS。 |
| 13 | T6-F、official physics、T7–T9、0.7 nm | 全部 `not_authorized` / `not_run`。没有 official E/H、R/T/A、full diffraction、T7–T9 或 full 0.7 nm PDE。 |
| 14 | selective-merge 边界和 do-not-merge family | 新 LOR/HX lane 当前为 research-only、因 L2 hard stop 不具备 production qualification；不整体 merge 分支。FC3/local-spectral、Candidate A/B/C、trace-harmonic、旧失败 runner/checker 与相关 closed family 保留 evidence、分类 `do-not-merge`。只有经后续 review 明确批准的独立文件组才可 selective merge。 |
| 15 | tests、commands、records、raw hashes | 实现前收口：`31 passed in 424.05s`（含 test294/test295/test297），随后 test295=`13 passed`；compileall/diff-check pass。首次 `12 passed/1 failed` 是 synthetic residual 同步测试 bug，修复后 `13 passed`，不是 formal failure。L2 record SHA=`0a6ccfdb6a28b003167046e3ca3fc5e4de0d40825784786319661901a65389f3`；aggregate SHA=`eaea740a3b379066204f9b4055e217718305a708d912cc2cdd9ba72339672f50`；raw root=`benchmarks/artifacts/task038_extra_full3d_lor_hx_l2_v1/91992c0/p2-mpi1`；marker SHA=`571abce21302801d236cc4410f7a809553628b79fb69964af65af30f781f984b`。`fixture_audit.hx_audit` 的 `apply_count=0`、`last_nodal_correction_count=0`、`last_output_finite=false` 是构造时的 non-authoritative stale diagnostic snapshot，未在 record 前刷新；`contract_errors=[]`，且该快照不影响 canonical raw 与独立 rho 裁决。详细 canonical raw SHA 见 `outcomes/lor_native_complex_hx_oracle.md`。 |
| 16 | 下一轮建议 | 只等待新的 Review；不自动进入 L3，不调 omega/shift/scaling，不扫描参数，不重跑本次 hard-stop case，不恢复 FC3 或 closed families。 |

## L2 证据与根因边界

L2 runner rc=`0`，说明事实采集和 record 写入完成；独立 checker rc=`1`，说明冻结 positive contraction Gate 失败。`random` 的 finite、输入不变、重复结果和 canonical artifact 角色均闭合，marker 到 `record_written`；`contract_errors=[]`。需要明确，`fixture_audit.hx_audit` 的动态字段是构造时未刷新的 non-authoritative stale diagnostic snapshot，不影响 canonical raw 与独立 rho 裁决，也不构成数值 Gate 原因。正式能下的结论仅是：冻结复合 `M_H^{-1}` 对首个 `random` positive source 未达到 `rho<=0.45`。高低阶谱缩放/提升后过校正是开发诊断层面的解释性推断，不是本次 formal 直接测量的唯一机制。

本轮保留旧 N2 v1/v2、FC1、FC3 和所有 closed-family 证据；不覆盖 raw，不创建第二候选，不进入 L3/L4/L5。最终 docs closure commit 的 SHA 不能由本文件自引用，交付报告负责给出。
