# Task037b response v1：H5 controlled negative closeout

## 结论

本轮唯一 H5 MPI8 formal 已完成并完整写出 22 个 RHS 的 H5b 记录，随后按数值 Gate 受控退出，正式分类为 `LOCAL_INVERSE_FAMILY_NEGATIVE`。

| 项目 | 结论 |
|---|---|
| H0 | pass |
| H1 direct authority | pass |
| H2a/H2b | pass |
| H3 exact block-LDU | pass；outer iterations=1 |
| H4a exact Sₘ | pass |
| H4b G-only | bounded diagnostic complete；non-stopping negative，不作 H4 失败 |
| H5a | pass；bottom/top exact reference 各 11/11 |
| H5b | controlled negative；bottom=1/11、top=0/11 |
| H5c | not_run |
| H6-H10 | not_run；H5 双侧失败触发停止 |
| H5 official R/T/A、field、12+12 | not_run |
| ordinary defaults | unchanged |
| formal return | 2；完整 record 后的数值 Gate 受控退出 |

## 冻结身份与证据

正式条件为 p6/h10、modal p6/h10、M120/candidate240、MPI8、S、10° grazing、10/110 nm、static-condensed、`full3d_uniform_cg`/`scalar_cg_discrete_derivative`。测试源码 SHA 为 `216437c6f13b3a3bf46e74451f63779189453c6f`；分支为 `codex/20260807-task37b-hybrid-iterative-development`；本 docs-only 编写快照的 upstream 为同一 SHA，docs closeout commit 在本文件编写时仍 pending，最终 SHA/clean/0/0 以交付报告为准。H1 whole-direct authority 的 evidence source 是 `2990f357f7dec23b1713bd0088bdc43c3ce6f5bc`；`216437c` 只新增 H5 explicit-opt-in 路径，ordinary direct path 未改变，不能把 H5a 误写成在 `216437c` 上重新跑过 whole direct Hybrid。两份 authority 沿用 H3/H4，未改变。执行入口为 `python -m benchmarks.run_task033_memory_watchdog`，H5 explicit opt-in，普通 augmented 默认未改变。

| raw evidence | 相对路径 | SHA256 |
|---|---|---|
| summary / memory sampler | `../../benchmarks/artifacts/task037b/h5_local_inverse_216437c_mpi8.json` / `../../benchmarks/artifacts/task037b/h5_local_inverse_216437c_mpi8/memory_sampler_summary.json` | `feb689c5faff607555f7ae894a7836020771145b30800d48eed4a595a3f8edb4` |
| solver record | `../../benchmarks/artifacts/task037b/h5_local_inverse_216437c_mpi8/solver_record.json` | `887be236f9edc0f3140e0124b82895f14761d22260d79477f8d7c0f00ee90d92` |
| memory stages | `../../benchmarks/artifacts/task037b/h5_local_inverse_216437c_mpi8/memory_stages.jsonl` | `a27af6f56fb1028ec0174d1fd08c632279fc4af9258e06918d1166c1021aaabc` |
| memory timeline | `../../benchmarks/artifacts/task037b/h5_local_inverse_216437c_mpi8/memory_timeline.csv` | `8b060e61c04419abc19d4bee08bbafa572b9ca7ed484978e7d540eaf339e2f2f` |
| worker stdout | `../../benchmarks/artifacts/task037b/h5_local_inverse_216437c_mpi8/worker_stdout.txt` | `dcab0800a76be977f57d18b3b1fccdcb940b14a76cb4582e71f850b62d5c2178` |

这些文件均为 Git ignored raw artifacts；tracked docs 只保存 hash-bound 引用。

## H5a 与 H5b

H5a 用 direct local factor 做 reference，bottom/top 各 11/11 通过；bottom/top direct max=`2.107282966996484e-12 / 2.1971754846774315e-12`，action max=`2.0973803488508764e-12 / 2.1957548735380243e-12`，两侧 factors 均释放。结合 H1 source `2990f357f7dec23b1713bd0088bdc43c3ce6f5bc` 的 whole-direct authority，这证明 exact local action/RHS 接线正确，但不替代 H1 whole-direct evidence。

H5b 的冻结 local inverse 是 x-axis 六 slab、overlap `0.125`、partition ASM、shifted ILU(0)、factor-only、right FGMRES restart=30/max=300/rtol=`1e-10`。bottom 仅零 physical RHS 通过；top 0/11。随机与 modal RHS 的重复解 relative error 均为 0，但 reason=-3、max_it=300 与残差平台说明 deterministic 不等于 convergence。完整逐 RHS 表与 1/2/4/8 诊断见 [local endcap inverse evidence](outcomes/local_endcap_inverse_matrix.md)。

## 资源与解释

| 阶段 | worker RSS/PSS/USS MiB | process-tree RSS MiB |
|---|---:|---:|
| action/coupling | 6064.90625 / 4960.2822265625 / 4777.046875 | 6079.53125 |
| H5a direct | 7705.8203125 / 6586.92578125 / 6401.30078125 | 7720.4453125 |
| H5b candidate | 6910.75390625 / 5788.64453125 / 5602.4375 | 6925.37890625 |
| post-direct trim | not_observed（0 samples） | not_observed |

swap=0，warning/termination=false/false，总时长 `795.0781892240047 s`。H5b process-tree RSS=`6925.37890625 MiB`（约 `6.763 GiB`），高于 H9 后续定义的 eventual `MPI8 resource-positive <=6.0 GiB` 参考线；但 H5b 数值失败且 H9 未运行，不给出正式 resource qualification。candidate 峰值低于 H5a direct reference，不能把内存下降包装成 qualified solution。

## 与既有 authority 的关系

当前-source direct Hybrid 在同一物理条件下已经通过 H1 authority，并与 Full3D frozen reference 完成 12/12 power 与 12/12 complex amplitude 对齐；H3 exact block action 与 exact block-LDU 也通过。因而本轮负结论只针对冻结的 local inverse family，不是否定 Hybrid 模型本身，也不证明其他未经授权的算法家族不可能。

Hybrid-P、低秩 direct Hybrid 与本轮 iterative candidate 均不得称为 production-qualified；ordinary defaults unchanged。

## 测试与收口

H5 implementation 收口沿用 source `216437c` 的本地证据：40 passed，Ruff check、compileall、`git diff --check` pass；full pytest 未运行。此次只做 docs closeout，不重跑 PDE/MPI/full pytest。

| 后续阶段 | 状态 |
|---|---|
| H5c | not_run；H5b 数值 Gate 未过 |
| H6 | not_run；双侧 H5 失败触发停止 |
| H7-H10 | not_run；同一 task stop |

建议：未经 review 不整体 merge。H5 candidate 作为 research-only negative evidence 保留；若要探索新算法家族，必须新建 review，不由 response 自行扩 scope。

更多连续证据见 [summary](outcomes/summary.md)、[resource ledger](outcomes/resource_ledger.md)、[test summary](outcomes/test_summary.md)、[changed files](outcomes/changed_files.md)、[H6 boundary](outcomes/one_sided_replacement.md) 与 [H7-H10 boundary](outcomes/double_iterative_funnel.md)。
