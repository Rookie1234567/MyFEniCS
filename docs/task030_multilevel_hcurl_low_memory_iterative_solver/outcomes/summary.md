# Task030：3D H(curl) 低内存迭代研究总结

## 1. 任务身份与当前分类

```text
task = Task030
branch = codex/20260713-task30-multilevel-hcurl-low-memory-iterative
base = Task029 merged master bfb6586e030efd5208ebd796c39fdc31301e1d6e
classification = workstation_memory_success_with_qualifications
workstation_memory_result = success_with_qualifications
ordinary_default_changed = false
```

Task030 在冻结 3D p2 Nédélec、双 Floquet、80 个传播模态、exact condensed DtN 和 official R/T/A 的前提下，研究“保证真残差收敛时尽量节约内存与计算”的迭代法。Task029 已先按 Review V2 更正并合入 master，本任务从更新后的 clean master 独立建分支。

## 2. 基线与成功门槛

Task027 canonical profile 是右预条件 FGMRES restart100、16 个 overlap0.25 物理 z-slab、shifted-F ILU1、两次 pre smoothing 和 75D Floquet z-hat coarse。

| h (nm) | FE DoF | iterations | full true residual | peak RSS |
|---:|---:|---:|---:|---:|
| 5 | 44,698 | 1,201 | `9.839e-7` | 1.991173 GB |
| 3 | 198,438 | 993 | `9.933e-7` | 5.08 GB |
| 2 | 615,108 | 1,804 | `9.997e-7` | 13.080257 GB |

h5 统一 100 步基线由 SHA-256 pinned Case031 记录读取，为 `2.5737371765314062e-3`；runner 对 hash、iteration=100 和 reported/true 字段 fail closed。

## 3. 实现的方法

### 3.1 真正 H(curl) 层级基础设施

实现 active/master DoF map、跨材料面对齐 hexa 网格的 nonmatching N1curl transfer、MPC slave backsub/homogenize、Hermitian restriction、MPI CSR cache、精确 condensed Galerkin `P^H(F-CH^-1D)P`、Jacobi/patch/multilevel 和全 80 模态 Woodbury 研究组件。

MPI4 目标 transfer 为 `44698×792`、145,998 nnz，无零列；伴随恒等式误差 `1.586e-15`，fresh/cache action 误差 `6.410e-15`。因此基础设施正确性通过。

### 3.2 统一候选漏斗

五个机制不同的 p/h 候选都完成 20/100 步筛选：Jacobi、z-layer patch、vertical column patch、cell patch、16-slab ILU0。另验证全模态 Woodbury、扩展 x-harmonic coarse、z coarse 密度、去 overlap、单次 post smooth 和 Krylov restart。

### 3.3 最终有效机制

真正正反馈不是 792D p1 coarse，而是保留 Task27-derived physical-slab + 75D 波动粗空间，并将平滑器改为：

```text
ILU1 -> ILU0
pre-only -> symmetric pre/post sm2
global shifted-F copy -> original F + subdomain-local diagonal shift
retain submatrix/KSP/factor -> retain factor only
FGMRES restart100 -> restart90
```

local shift 与 factor-only 逐块 factorization 均通过 serial/MPI2/MPI4 action 等价测试（约 `2e-12`），没有改变 exact condensed outer operator。

这个最终配置的统一名称是 `compact physical-slab low-memory experimental profile`；它不是成功的 p/h multigrid solver。Task30 的 H(curl) transfer/Galerkin 成果属于 validated research infrastructure。

## 4. 候选结果与机制解释

五个 p/h 候选 100 步真残差为 `0.374864–0.680155`，是 Task027 基线的 145.65–264.27 倍。相同 slab smoother 加入 p/h coarse 还把 20 步 residual 从 `0.381817` 恶化到 `0.685751`。因此结论不是 transfer 失败，而是当前 792D p1 coarse 未包含 Maxwell 近核/梯度与该 grazing-wave RHS 的关键慢误差。

对称 pre/post 是决定性正反馈：Task27 ILU1 版本在 100 步达到 `1.273503e-3`（基线的 0.4948），随后 ILU0 仍保持 `1.865566e-3`。local shift 与 factor-only 在保持相同 residual 的同时把 h5 峰值降到 1.705 GB；restart90 继续降到 1.694 GB 且仍通过 weak-positive。restart80 未通过，故停止。

Task27 ILU1 与 Task30 ILU0 的 `global_slab_factor_nnz` 在 h5/h3/h2 分别都为 7,046,752 / 30,329,104 / 95,617,608，因此当前 evidence 不能证明 factor-nnz compression。已观测内存下降主要归因于 factor-only 生命周期、local shift、释放 source submatrix/KSP/PC wrapper 和 restart90；ILU0 的作用是配合对称组合保持较低 setup/apply 成本。

## 5. 正式 h5/h3/h2 结果

| h | iterations | full true residual | peak incl. RTA | Task027 memory reduction | R / T / A | max delta vs direct |
|---:|---:|---:|---:|---:|---|---:|
| 5 | 855 | `9.924905e-7` | 1.687653 GB | 15.24% | 0.0890216035 / 0.4425882732 / 0.4683901222 | `5.438e-9` |
| 3 | 962 | `9.903890e-7` | 3.792912 GB | 25.37% | 0.00461303218 / 0.58365335775 / 0.41173361173 | `7.719e-10` |
| 2 | 1873 | `9.972228e-7` | 9.374729 GB | 28.33% | 0.00134293442 / 0.59921323601 / 0.39944383222 | `6.561e-9` |

三者 reported、condensed true 和 full augmented true residual 一致；energy closure 分别为 `-1.137e-9`、`1.659e-9` 与 `2.639e-9`。h3/h5 iteration ratio 为 `1.1251`，满足 `<=2`。h5 迭代比基线少 28.8%，h3 少 3.1%；h2 迭代比 canonical 多 3.8%，但内存低 28.33%。

h5/h3 是 final implementation commit `5b81359daee0874793c44b019d9c914b334db483` 上的 clean rerun。h3 的 3.792912 GB 同时通过 3.8 GB 绝对目标，并较 Task27 降低 25.37%。h2 未按 Review V2 重跑，本表 h2 行是 `reviewed_historical_dirty_worktree_reference`。

## 6. h2 条件运行

h5/h3 的 DoF–RSS 仿射与幂律两个独立模型给出 h2 中央预测 `9.5298 / 7.0337 GB`；较保守仿射值增加 15% 后为 `10.9593 GB`，通过 G5/G6。唯一候选首次 h2 运行峰值 9.342113 GB，1800 步真残差 `1.461130e-6`，严格未通过且没有输出 official R/T/A。

同一 PC/restart 只把 `max_it` 延到 2100 做资格复跑；残差在所有共同 monitor 点与首轮逐位一致，并于 1873 步收敛。reported/condensed/full residual 分别为 `9.972228396e-7 / 9.972228402e-7 / 9.972228402e-7`，含 R/T/A 峰值 9.374729 GB，solve/total 为 2393.689/2577.796 s。official `R/T/A=0.001342934415/0.599213236006/0.399443832218`，closure `2.639063e-9`，相对 direct 最大差 `6.561388e-9`。同一 80 modes、无 swap、内存和数值 Gate 全通过。

## 7. 成功、负结果与合并决策

已达到 `workstation_memory_success_with_qualifications`：clean final-HEAD h5/h3 full solve 通过，h3 绝对内存低于 3.8 GB且降幅超过 25%，h3/h5 iteration ratio 为 1.125；历史 h2 reference 在 9.375 GB 内完成 full solve、80 modes 与 official R/T/A，h2/h3 iteration ratio 为 1.947。由于 h2 没有在 Response V2 final-HEAD 重跑、1873 步高于 1200 的工程偏好且峰值高于 8 GB，它不是 strong success，也不能称为真正 mesh-independent GMG。

可建议合并的是通用 transfer/Galerkin 基础设施和已验证的 local-shift/factor-only/pre-post opt-in 机制。p/h solver profiles、Woodbury、x-harmonic、AMS/HX、restart80 和 heavy artifacts 不得提升。ordinary default 保持不变，最终仍需 ChatGPT review 与用户明确许可。

## 8. 局限与下一步

- “保证”只针对冻结物理模型、MPI4 分区和 explicit true residual，不代表所有角度/材料/网格参数无条件收敛。
- 当前 h/p coarse 缺少严格 commuting projection、梯度/近核辅助空间和多级 smoother；基础设施成功不等于 GMG 成功。
- factor-only 只在 qualified local image 的 PETSc 3.24.0 complex build 验证；跨 PETSc 版本必须重跑 action/lifecycle 回归。
- h2 历史证据已收敛，但 1873 步仍高于 1200 工程目标；Task31 只可在 Task30 final review、用户批准和 selective merge 后，从 clean master 独立启动。

## 9. Review V2 provenance、API 隔离与自动 Gate

h5/h3 在 final implementation commit `5b81359daee0874793c44b019d9c914b334db483` 上完成 clean rerun，host tracked-source 状态为 clean，并用 exact full-SHA attestation 与容器内 HEAD 交叉核对。heavy JSON SHA-256 分别为 `2be05820cf69db67ba72b257c44624c08e15f7f7ceeae6e479eed2a9e68523f3` 和 `48c9bb51b89a99b7ba1653f8c95f8450e7917f987274c1aef631464484275232`。h2 没有重跑；其 record 保留原 `bfb6586e` dirty provenance，并增加 `reviewed_historical_dirty_worktree_reference` identity 以及与 clean h5/h3 相同 solver/physics 的等价性链接。

`hcurl_multilevel.py` 已把 validated API 限定为 active DoF、nonmatching transfer/cache、transfer validation 和 condensed Galerkin。失败的 Jacobi/p-h multilevel/Woodbury 候选只由 research runner/tests 直接导入，普通 `src.solvers` 不导出；这明确了可选择合并的基础设施边界，不把 solver-negative lane 带入公共 API。

Case060 已接入 203 项 checker：除 manifest/文件合同外，还验证 clean h5/h3 final-HEAD provenance、historical h2 identity、final solver identity、p/h negative disposition、显式 opt-in、冻结物理与 80 modes、KSP reason、三残差与一致性、official R/T/A、energy closure、direct delta、h3 absolute/relative memory Gate、iteration ratio、h2 RSS 和限定分类。三份 experimental records 已进入 manifest，normal checker 可以稳定再生成同一 summary。

## 10. 证据入口

- `candidate_funnel.csv`、`candidate_comparison.csv`、`memory_breakdown.csv`；
- `hierarchy_design.md`、`transfer_validation.md`、`level_inventory.csv`；
- `h2_memory_prediction.md`、`h2_launch_decision.md`；
- `benchmarks/cases/060_multilevel_hcurl_iterative_solver/records/`；
- 重型本地证据：`benchmarks/artifacts/cases/060/`。
