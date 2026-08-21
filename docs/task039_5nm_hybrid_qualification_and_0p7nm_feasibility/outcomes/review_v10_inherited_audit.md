# Task039 V10-0：side factor 与响应基线继承审计

本文件是 Review V10 的独立 docs-only 起点。它只核对已经提交的 V7/V9 证据身份、数值
边界和停止条件，不修改 Python、配置、测试阈值或历史 record，也不启动 h4、MPI、factor、
solver、QEP 或 PDE。文中的“继承”表示引用已有 hash-bound 证据，不表示本轮重新测量。

## 1. Review 与 Git 身份

| 字段 | 值 | 口径 |
|---|---|---|
| task | Task039 | 5 nm Hybrid 资格与 0.7 nm 容量审计 |
| branch | codex/20260812-task39-5nm-hybrid-0p7nm-feasibility | 唯一执行分支 |
| V10-0 base HEAD | dc8042cfbff1d5e842ea34abe78db5efcfbf1e65 | 本轮 fast-forward 后的审计起点 |
| upstream | origin/codex/20260812-task39-5nm-hybrid-0p7nm-feasibility at dc8042cfbff1d5e842ea34abe78db5efcfbf1e65 | 开始时精确一致 |
| ahead / behind | 0 / 0 | V10-0 开始时 |
| worktree | clean | V10-0 开始时 |
| Review | [review_report_v10.md](../review_report_v10.md) | Review V10 权威执行边界 |
| Review SHA256 | 5213edb9ca7c8c716405de87384333805da04d642a4be92c3b5b33b00d9b8ca1 | 当前文件内容 hash |
| task SHA256 | f637ede5010d1bad7555b965fdd8aad3adcead7b828f1f80912f4127cb950734 | 冻结任务书身份 |
| inherited response | [response_v10.md](../response_v10.md) | V9 结项回应；不重写 |

本文件提交后，Git HEAD 将变为本 docs-only commit；上表的 dc8042cf 始终表示 V10-0
继承审计起点，不把后续提交 SHA 冒充为本轮运行身份。master 未修改，未创建新分支或
worktree。

## 2. 冻结物理输入、配置与 holdout

| 身份字段 | 继承值 |
|---|---|
| input | input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat |
| input SHA256 | 4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811 |
| physical model SHA256 | 8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c |
| resolved config SHA256 | f965c38abea08bee0ff83a6603e336ca4823deb932af7064aed3c571f8f63883 |
| model identity | task039_5nm_v4_1deg_s5_hybrid_iterative_m480 |
| physical case | 5 nm / 1° grazing / phi=0° / S / p6/h4 / M480 |
| formal MPI / threads | MPI8 / 1 |
| selected packet | results/task039_v4_h4_m480_shared_packet_eaad0f94；只作历史身份，V10-0 不打开 |

V7/V9 复用的 frozen exact-bottom holdout 为：

| 字段 | 值 |
|---|---|
| exact spool root | results/task039_v5_h4_mumps_blr_side_component_mpi8_7e5d9b57_1e3/numerical_output |
| producer/source SHA | 7e5d9b57a10b1093f0cb062eaf7bc12797c47e1f |
| catalog SHA256 | a2a7fb6fb01df4f795d31ff94f6ac6adf957ac4fe4a5c1a8d05176e3d64c0384 |
| catalog method | sorted relative path、byte count、file SHA256 rows 的 SHA256 |
| inventory | 8 producer ranks / 6 labels / 96 response artifacts |
| role | frozen oracle/holdout only；不进入训练 |

## 3. V7/V9 compact evidence 与 hash

以下 hash 是在 V10-0 落盘前对 tracked 文件重新计算的值；raw results 仍在 ignored local
path，不进入本提交。

| 阶段 | compact record | SHA256 | outcome / SHA256 |
|---|---|---|---|
| V7 setup-only | [task039_v7_exact_side_limit_setup_v1.json](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v7_exact_side_limit_setup_v1.json) | 746ca172aaa025fd49bac52c2d4212cc14d00b764b3b6056f9d97d0d6d73a85e | [v7_exact_side_limit.md](v7_exact_side_limit.md) / c2949060d5b152f904c504e85478ff1531bcc3157e62a2403010e37e91e8b289 |
| V7 full formal | [task039_v7_exact_side_full_formal_v1.json](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v7_exact_side_full_formal_v1.json) | 412610be438423e893c6886bf617132b3cb5f0241937243e3cd1fb1303104bd2 | [v7_exact_side_limit.md](v7_exact_side_limit.md) / 同上 |
| V9-1 bare-F/full-side | [task039_v9_bare_f_full_side_diagnostic_v1.json](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v9_bare_f_full_side_diagnostic_v1.json) | bbab2d6cf3f222f2883edd5f36ff7caf0b0cfe7a437f9e1f47d164bd7fc8d185 | [v9_bare_f_vs_full_side.md](v9_bare_f_vs_full_side.md) / 2d4589334b19815e953a8ae4f9cb64d41d1e138181daf936316a90616fce3bec |
| V9-2 supernode | [task039_v9_supernode_side_preconditioner_v1.json](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v9_supernode_side_preconditioner_v1.json) | 42536b938ee504766dbd7810298aad7916fd7009ad403fe5b82b0fdad779bd31 | [v9_supernode_side_preconditioner.md](v9_supernode_side_preconditioner.md) / 59a379bc70db3088877887bbe444caaf13dc44584f85337508a38cde0b4d9721 |

V7 Lane A 的 full-formal source 为 9e31ecf189081afcb8ca27b0374ec89af0094e2d；V9-1
source 为 2faf2a1a89a065e2985e46e462c6b7396f72b051；V9-2 source 为
266a1acc0eb7a4515815e34414f89e183c15e9ef。这些是各自 evidence 的 source authority，
不是 V10-0 的新运行 source。

## 4. 资源与 ABI 继承快照

以下环境字段来自已资格化 activation 下的 V9-0 只读快照；V10-0 不重复探针。它们是
继承环境记录，不是本轮 h4 readiness 或 resource Gate。

| 项目 | 继承测量 |
|---|---|
| activation | _MYFENICS_WSL_QUALIFIED_ACTIVATION=1 |
| interpreter | /home/Projects/MyFEniCS/.venv/bin/python |
| platform | Linux WSL2 x86_64 |
| MPI | Open MPI 4.1.6；probe world size 1；formal identity MPI8 |
| PETSc | Scalar complex128；Int int32 |
| SLEPc / DOLFINx | import available / import available |
| threads | OMP_NUM_THREADS=1；MKL_NUM_THREADS=1；OPENBLAS_NUM_THREADS=1 |
| MemAvailable | 235420132 kB |
| swap | total 33554432 kB；free 33554432 kB；used 0 kB |
| filesystem free | /home/Projects/MyFEniCS：817265295360 bytes |
| V10-0 fresh probe | measured at 2026-08-21T09:40:14.722429+00:00 UTC；qualified activation；world size 1 |

Fresh lightweight V10-0 probe（只读，无 MPI 多进程、PDE 或 solver）：

| 项目 | fresh measured value |
|---|---|
| activation / interpreter | _MYFENICS_WSL_QUALIFIED_ACTIVATION=1；/home/Projects/MyFEniCS/.venv/bin/python |
| platform | Linux-6.18.33.2-microsoft-standard-WSL2-x86_64-with-glibc2.39 |
| MPI | Open MPI 4.1.6；world size 1；formal identity remains MPI8 |
| PETSc | Scalar complex128；Int int32 |
| SLEPc / DOLFINx | import available / import available |
| threads | OMP_NUM_THREADS=1；MKL_NUM_THREADS=1；OPENBLAS_NUM_THREADS=1 |
| MemAvailable | 235432392 kB |
| swap | total 33554432 kB；free 33554432 kB；used 0 kB |
| filesystem free | /home/Projects/MyFEniCS：817259274240 bytes |

上表是 V10-0 fresh host/ABI 事实；前表的 V9 数值快照仍保留为历史 inherited measured
snapshot，不能互相替代。

## 5. 数值与内存基线

完整 workflow 与 component 必须分开。低内存 component 不能换算成完整 workflow saving。

| 路径 | scope | 关键实测与裁决 |
|---|---|---|
| matched h4 Hybrid direct | full workflow | 93.377006531 GiB，direct authority |
| V7 Lane A setup-only | setup-only | measured 81.056903839 GiB；84.039305878 GiB 是 advancement threshold，不是 measured peak |
| V7 Lane A exact-side full | full workflow | 80.025856018 GiB，10126.231902 s，1 outer；physics/recovery/checker pass；相对 direct 节省 14.298113646% |
| V9-1 J1 | bottom component | finite/fixed/repeat/linearity pass；worst bare-F r_F=50.7689715097；construction 23.8684272766 GiB；retained not_run |
| V9-1 F1 | bottom component | finite 但 residual negative；worst bare-F r_F=367.2128685567；construction 22.1353225708 GiB；retained not_run |
| V9-2 SN2-J/SGS | bottom component | construction 22.812664031982422 GiB、swap0、factors 3→0；mandatory output Inf/NaN；retained not_run |

V7 full formal 是当前唯一完整低于 direct 的正式正结果；它仍保留 full side factors，不能
被称为 0.7 nm scalable。V9-1 的 J1 是 finite、固定线性、可重复的 action，但不是一次
准确的 F^{-1}；F1 与 J1 的 residual 都未达到 1e-2。V9-2 的 SN2-J/SGS 对非退化
输入分别产生 Inf/NaN，不是资源停止，也不是已证明的通用 MUMPS bug。

## 6. J1、F1 与已关闭路线

V9-1 的五个 mandatory source 均为非退化；physical_side_rhs 只因零输入而
degenerate_uninformative，不进入 mandatory 最坏值。J1 的 finite、repeat 和 linearity
通过；两方法共享同一组六层 factor，J1/F1 的 K rank 为 296、condition 约 63.9433，
full-side/global direct/nested inventory 为 0/0/0。J1 因此可以作为未来 FGMRES PC 的
候选身份，但不能把其 residual 误写成 exact inverse 通过。

V8 固定 sweep 的 J1/F1/FB1/FB2/FB4 direct-inverse 候选已关闭；V9 原 SN2-J/SN2-SGS
重跑已关闭。V9-2 的 SN2-SGS 非有限事实原样继承，不能因 V10-1 tiny 语义测试而改写。

```math
r_F=\frac{\lVert b-FM_Fb\rVert}{\max(\lVert b\rVert,10^{-30})}.
```

## 7. V10-0 后续边界与禁止项

V10-1 只允许 tiny serial/MPI2/MPI4 factor semantics、zero-map、ownership/scatter 和
destroy lifecycle tests；不得读取 h4 exact spool 运行 solver。V10-2 才是条件性的唯一一次
真实 h4 three-supernode factor-integrity forensic；V10-3 只在明确 implementation failure
时允许最小修复；V10-4 的 J1-inner-FGMRES 已在本 Review 内授权，但必须严格按
V10-0→V10-1→V10-2→条件 V10-3→V10-4 顺序执行，当前 V10-1 阶段暂不进入。
V10-5/6 只按各自 Gate 条件执行；full formal 仍未授权。

本阶段及未获新授权前明确关闭/禁止：

- V9 原 SN2 rerun、SN2-SGS rerun、FB8 或更高 defect correction；
- supernode 分组、shift/damping/Robin/overlap 参数和 MUMPS profile 扫描；
- generic ILU、drop-tolerance、fixed-budget 或普通 Krylov budget sweep；
- Petrov rank >512、第三 BLR、V7 exact-side full rerun、Hybrid direct rerun；
- new Full3D heavy、top、both-side、full Hybrid formal 和完整 0.7 nm PDE；
- selected packet hydrate、new response packet producer、QEP、global direct factor；
- 并发 heavy、新 branch/worktree、master 写入或 raw artifact 提交。

ordinary defaults 保持不变。V10-0 的 status 是 inherited audit complete；V10-1 仍为
本轮接下来唯一允许的 tiny code/test 阶段，不能从本文件推导任何 h4 advancement 或
full-workflow qualification。

## 8. 轻量检查与提交边界

本文件只应通过 JSON/hash、Markdown 相对链接/表格/fenced-math、check_benchmarks
--no-write（若其仓库检查范围允许）、git diff --check 等轻量检查。V10-0 不运行
pytest、MPI、PDE、Ruff/compileall 代码检查或任何 heavy。提交只包含本文件，提交消息固定为：

```
docs(task039): audit v10 side factor and response baseline
```

所有 V7/V9 raw roots 保持 ignored local evidence；本审计只提交小型 Markdown，不提交 raw
matrix、factor、field、timeline 或 stdout。
