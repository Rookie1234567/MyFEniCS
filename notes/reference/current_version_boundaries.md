# 当前版本边界

更新时间：2026-07-14，Task29 已合并；Task30 Review V1 P0 已回应，compact physical-slab profile 等待 final review。

## 可声明能力

| 范围 | 可声明内容 | 证据 |
|---|---|---|
| 2D | TM/TE、Floquet、PML/Robin/DtN、real/complex index、R/T/A、A_volume | 普通 tests 与 2D smoke |
| 3D staged | Stage1 推荐；double Floquet supported；PML/Fresnel experimental；flat sanity 与 target block grating 有分层证据 | cases 010-031 与 ordinary regression |
| power | official DtN modal R/T + volume absorption | residual gate 后输出 |
| direct | ordinary auxiliary MUMPS；h5/h3 当前工作站可运行；Case050 分阶段内存遥测 | Task28 clean direct records + Task29 Case050 |
| condensation | exact explicit/matrix-free `F-C H^-1D`、RHS、transpose、back-sub | focused tests |
| iterative | 固定目标 p2 h5/3/2，MPI4，三残差 <=1e-6 | canonical records + automatic checker |
| memory | 所有 MPI ranks 总峰值 RSS；h2 迭代 13.08 GB | benchmark records |
| Task30 compact physical-slab low-memory profile | Task27-derived；h5/h3/h2 full true residual 与 R/T/A 通过；h2 1873 步、9.374729 GB | Case060；仍为 experimental，等待 final review |
| H(curl) transfer/Galerkin | nonmatching active-column transfer、MPI cache、exact condensed coarse action | Case060；当前 p1 coarse solver 性能失败 |

## Official 与 diagnostic

| 数据 | 身份 |
|---|---|
| DtN outgoing modal amplitudes 得到的 R/T | official |
| 有损材料体积分得到的 A_volume | official |
| R+T+A_volume closure | official consistency check |
| probe-plane Fourier | diagnostic_only |
| sampled net flux | diagnostic_only |
| 未通过 full residual 的任意 R/T/A | invalid for official use |

## Direct/iterative 资源边界

| 网格 | direct | iterative MPI4 |
|---:|---|---|
| h=5 | 2.29 GB，recommended | 1.99 GB，qualified |
| h=3 | 8.18 GB，supported | 5.08 GB，qualified |
| h=2 | 历史约 20.53 GB，超本机预算 | 13.08 GB，qualified |
| h=1.5 | not_verified | not_verified |

Task29 没有产生新的低内存或 threaded direct profile。最佳 h3 MPI2 simultaneous RSS 只下降 15.119%；当前 image 的 MPI1×4 在 KSPSetUp 仍约 1 核、相对 MPI1×1 仅 1.054× speedup，因此 `threaded_direct_capability=unavailable_in_current_image`。h2 direct 与 threaded h3 均为 `not_run`，ordinary default 不变。

Task30 compact physical-slab low-memory experimental profile 在 h5/h3 分别为 1.696/3.808 GB。h3 的 3.807503 GB 未过 3.8 GB 绝对线，而是凭较 Task27 canonical 降低 25.08% 的替代 Gate 通过；h2 同候选资格复跑在 1873 步、9.374729 GB 下达到 full residual `9.972e-7`，80 modes 与 official R/T/A 通过。它是 Task27-derived physical-slab/wave-coarse 架构的内存工程改进，达到 `workstation_success_experimental_opt_in`；但因 1873 步高于 1200、参数域外未验证，不能替代 canonical profile 或 ordinary default。

## Benchmark 状态

重型 benchmark 只能写 `benchmarks/artifacts/`；`results/` 保留给 ordinary runs。Task28 最终 checker 为 148 项；Task29 Case050 scaffold 后为 149 项；Task30 Review V1 数值化 Case060 后为 203 项，并新增独立 Task 回顾合同测试。Task30 h5/h3/h2 重型 artifacts 来自 `bfb6586e` 的 tracked-dirty 工作树，正式 records 已据实标注 qualification 并固定 SHA-256；没有为本次审查重跑重型计算。

2D Case002/003 是 V3 新生成的 lightweight canonical evidence。2D lossy 功率使用实际端口平面 coefficient；该口径变化不重算独立 3D official RTA 路径。

环境当前为 `qualified_local_image`，不是完全 clean-machine reproducible。基础 complex MPC 镜像已按本地 digest 固定，但没有公开 pull source；详见 `docker/STAGE4_ENVIRONMENT.md`。

## 不能宣称

| 声明 | 当前状态/原因 |
|---|---|
| h=1.5 production solver | not_verified；没有同口径 residual/RSS/RTA |
| 严格 mesh-independent | not_verified；迭代数 1201/993/1804 不单调 |
| 任意角度、波长、材料和几何鲁棒 | not_verified；qualification 只覆盖一个目标点 |
| 最终物理网格收敛 | not_verified；h=2 是工作站可达参考，不是连续极限证明 |
| spectral/GenEO production | research_only；Task27 目标问题失败 |
| AMS/HX full Stage4 production | research_only；只有 FE-only/低阶正信号 |
| benchmark clean environment 可公开重建 | qualified；缺公开基础镜像来源 |
| 当前 image 的 threaded MUMPS direct | unavailable；MPI1×4 KSPSetUp 仍约 1 核 |
| 真正 p/h GMG production | not_implemented；transfer 正确，但五个 p/h solver 候选 100 步均明确失败 |
| Task30 对任意参数保证收敛 | not_verified；当前只覆盖冻结 target 与 MPI4 |
| Task30 ILU0 已证明更少 factor nnz | not_verified；Task27 ILU1 与 Task30 ILU0 的 reported factor nnz 相同，measurement unresolved |
| factor-only 跨 PETSc 版本兼容 | requires_regression；当前仅验证 PETSc 3.24.0 complex build |

## 参数域外使用

runner 会对偏离 canonical profile 的参数打印警告并写 `qualified_profile=false`。此类结果必须先与 direct/可信 reference 比较，并重新完成三残差、official R/T/A、能量闭合、总 RSS 和至少一个网格变化检查，才能升级状态。
