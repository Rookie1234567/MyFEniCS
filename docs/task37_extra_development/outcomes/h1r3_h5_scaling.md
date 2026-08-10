# H1R3.2：p6/h5 MPI1 action-only 缩放资格化

## 结论

本次只测一个全空间 matrix-free action：它把有限元向量直接作用到离散算子，逐单元计算并累加结果，不把庞大的全局矩阵存下来。这样可以测量低存储 action 的数值和资源行为，但它不是求解 PDE，也不包含 KSP、物理场恢复或 R/T/A 后处理。

| 项目 | 结论 |
|---|---|
| H1R3.2 p6/h5 MPI1 scaling | **PASS** |
| watchdog / checker | 各仅运行一次，return code=`0` |
| H1R3.1 | 已通过；本 outcome 不重做其测量 |
| H2 | `locked`，不因 H1R3.2 PASS 自动进入 |
| KSP / PDE / DtN / RTA / physical field | `not_run` |
| ordinary default | `unchanged` |

H1R3.2 PASS 只表示 Review V6 规定的 action scaling Gate 通过，不是完整求解器或物理问题的通过。

## 身份、固定范围与复现

| 项目 | 值 |
|---|---|
| branch | `codex/20260806-task37-iterative-extra-development` |
| formal source SHA | `d25669db29a25608685cce3bfff1f63379885aa5` |
| source start/end | 同一 SHA，均 clean |
| discretization | p6 / h5 / MPI1 |
| source | `seed_17037` |
| applies | reference=`1`，candidate=`2` |
| timeout | `1800 s` |
| canonical | `false`；canonical directory absent |
| runtime | qualified marker=`1`，PETSc `complex128` / `int32`，线程均为 `1` |

Python 使用记录中的 qualified shared target `/home/shenjh/Projects/MyFEniCS-Surrogate/.venv/bin/python`；当前仓库 `.venv` 解析到同一 qualified target，因此不是 Windows/ABI 混用。

正式 watchdog 命令：

```bash
source scripts/activate_myfenics_wsl.sh
python -m benchmarks.run_task037_extra_candidate_h h1r3-h5-watchdog --run-dir benchmarks/artifacts/task037_extra_h1r3_h5_v6_d25669d_20260810_run1
```

正式 checker 合同命令：

```bash
source scripts/activate_myfenics_wsl.sh
python -m benchmarks.run_task037_extra_candidate_h h1r3-h5-check --run-dir benchmarks/artifacts/task037_extra_h1r3_h5_v6_d25669d_20260810_run1 --h10-run-dir benchmarks/artifacts/task037_extra_h1r3_warm_repeat_v6_5529a01 --output benchmarks/cases/101_task37_extra_development/records/h1r3_h5_scaling.json
```

Raw 目录为 ignored 路径：

`/home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/artifacts/task037_extra_h1r3_h5_v6_d25669d_20260810_run1`

## 指标的通俗解释

- `retained payload / row` 是长期保留的数值缓冲区字节数除以全局行数，衡量每个离散未知量平均占用多少常驻内存。
- `alpha_payload` 比较 h5 与 h10 的 payload 增长相对于行数增长的指数：`log(M5/M10) / log(N5/N10)`。越接近 1，表示常驻 payload 越接近按行线性增长。
- `b_peak` 是 h5 相对 h10 的 process-tree 峰值增量除以新增全局行数，衡量每个新增未知量带来的峰值内存增量。
- `action seconds / row` 是 candidate 第二次 action 时间除以全局行数，用来区分算子作用本身的缩放，而不是把 setup 或输出写盘时间混进来。

## Gate 与实测值

| Gate | 实测值 | 限值 | 结果 |
|---|---:|---:|---|
| relative error | `2.868804640065144e-17` | `<=1e-11` | PASS |
| finite / deterministic | `true / true` | 均为 true | PASS |
| retained payload `M5` | `38,290,752 B` | — | measured |
| global rows `N5` | `1,127,502` | — | measured |
| retained payload / row | `33.9606954134006 B/row` | `<=45 B/row` | PASS |
| packed temporary | `23,708,160 B` | — | measured |
| packed temporary / row | `21.027155605932407 B/row` | `<=28 B/row` | PASS |
| `alpha_payload` | `0.9779306095631883` | `<=1.10` | PASS |
| reference / candidate 1 / candidate 2 | `7.448299763025716 / 7.41738795908168 / 7.548130201874301 s` | — | measured |
| candidate second / row | `6.694560366078553e-6 s/row` | `<=1.03171980264e-5 s/row` | PASS |
| h5 peak `P5` | `638,500,864 B` | — | measured |
| h10 peak `P10` | `340,541,440 B` | — | inherited baseline |
| `b_peak` | `312.42468700849327 B/row` | `<=512 B/row` | PASS |
| completed process-tree peak | `638,500,864 B` | `<=805,306,368 B` | PASS |
| swap | `0 B` | `0` | PASS |
| completion | `40.16706551914103 s` | `<=1800 s` | PASS |

本次实际规模为 `rows / cells / axes / constraints = 1,127,502 / 1,680 / (12,5,28) / 34,542`。Payload 的 local/global-sum/global-max 均为 `38,290,752 B`，组件之和闭合；packed temporary 每次为 `23,708,160 B`。

## h10 baseline 与 h1 derived 外推

| 项目 | 值 | 身份 |
|---|---:|---|
| `M10` | `6,151,104 B` | inherited h10 action evidence |
| `N10` | `173,802` | inherited h10 action evidence |
| `P10` | `340,541,440 B` | inherited h10 process-tree peak |
| `N_h1` | `116,527,176` | fixed axis identity |
| h1 axes | `(51,25,140)` | fixed axis identity |
| `P_h1_pred` | `36,692,207,894.33216 B` | derived action-only linear extrapolation |

`P_h1_pred` 约为 `36.692 GB`（decimal）或 `34.172 GiB`。它是用 h10/h5 两个 action 测量点计算的线性外推，不是 h1 实测，也不是 full solver/PDE 的内存资格化。该外推高于用户提出的 decimal `2,000,000,000 B` 目标，因此“MPI1 PDE 小于 2 GB 且有直接法可比物理结果”的最终目标尚未达成；不能把 action-only 的 H1R3.2 PASS 写成该目标通过。

## 禁止对象与 canonical 边界

| 审计项目 | 实测值 |
|---|---:|
| global matrix materialized | `false` |
| global constraint matrix materialized | `false` |
| global condensed Schur materialized | `false` |
| cell Schur matrix NNZ / materialized | `0 / false` |
| slab matrix NNZ / materialized | `0 / false` |
| retained dense cell tensor count | `0` |
| dense cell tensor per apply | `false` |
| cell metadata retained | `false` |
| factor count | `0` |
| KSP created | `false` |
| DtN used | `false` |
| ordinary default changed | `false` |
| canonical export / packet | `false / null` |

## 阶段 marker

Raw stdout 中的 marker 顺序为：

`mesh_build_started → mesh_build_ready → function_space_started → function_space_ready → floquet_mpc_started → floquet_mpc_ready → form_definition_started → form_definition_ready → form_compile_started → candidate_build_started → candidate_build_ready → reference_build_started → reference_build_ready → form_compile_ready → source_interpolation_started → source_interpolation_ready → reference_apply_started → reference_apply_ready → candidate_apply_1_started → candidate_apply_1_ready → candidate_apply_2_started → candidate_apply_2_ready → worker_summary_started → worker_summary_ready`

这些 marker 只说明阶段边界和顺序；action timing 不包含 marker telemetry、setup 或 canonical I/O。

## Evidence 索引

| 文件 | SHA256 |
|---|---|
| `run_summary.json` | `1696b0ca5fe436c96d0579d9e68ec3f1b3e129491e3e7f274a1f73f098135b3b` |
| `watchdog_summary.json` | `162fa11b6495b051477167674523ad021d18c661a766af7d262bf55e5d8eb630` |
| `watchdog_timeline.jsonl` | `5ce286a40398b29f2fdecb0a75164b7066957fe20c2ccded3df7476dafb3979f` |
| `worker_stdout.txt` | `38323d69cbd71118d0e70107f22f159d52ebb80e23b7fd1863a20d1ca8c993b1` |
| `h1r3_h5_root_pid.json` | `1ab21d7b8ab6a955407843f8e07c1637c2e8473253c26738ab9a9d62375d79ec` |
| compact record | [`h1r3_h5_scaling.json`](../../../benchmarks/cases/101_task37_extra_development/records/h1r3_h5_scaling.json) |
| compact file SHA256 | `83224635e201d1f56ca91016e00bb437e46a68c2c78fd883d6563bc053dae7d9` |
| compact embedded `evidence_sha256` | `76c8a538ad0f018336ab5d566694d426072ceb4a48a96a33441ee3f22cf08d41` |

compact evidence 的 `status=pass`、`problems=[]`，embedded evidence valid。H1R3.1 的历史 outcome 见 [`h1r3_mpi2_partition_identity.md`](h1r3_mpi2_partition_identity.md)。

## 一次非数值执行偏差

checker 实际只运行一次并返回 `0`，但最初的 output parent 写成了新建的 `101_task037_extra_development`，多了一个 `0`。没有重跑 checker，也没有修改 raw；生成的 compact 文件保持原字节不变，随后移动到合同固定的 `101_task37_extra_development` 目录，错误空目录已删除。这是输出路径操作偏差，不是数值测量失败。

## 验证与后续边界

| 验证 | 结果 |
|---|---|
| test285 | `15 passed` |
| tests 280--285 | `80 passed, 1 skipped` |
| compileall | pass |
| `git diff --check` | pass |
| Ruff | unavailable |

以上是本地 qualified 环境结果，不是 CI 结果。本轮没有运行 H2/H3/H4、KSP、PDE、DtN、RTA 或 physical field；H2 仍 locked，后续是否继续必须由新的 review 决定。
