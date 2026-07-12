# 当前版本边界

更新时间：2026-07-12，Task28 response v2 文档与 benchmark 契约整改。

## 可声明能力

| 范围 | 可声明内容 | 证据 |
|---|---|---|
| 2D | TM/TE、Floquet、PML/Robin/DtN、real/complex index、R/T/A、A_volume | 普通 tests 与 2D smoke |
| 3D staged | Stage1 推荐；double Floquet supported；PML/Fresnel experimental；flat sanity 与 target block grating 有分层证据 | cases 010-031 与 ordinary regression |
| power | official DtN modal R/T + volume absorption | residual gate 后输出 |
| direct | ordinary auxiliary MUMPS；h5/h3 当前工作站可运行 | Task28 clean direct records |
| condensation | exact explicit/matrix-free `F-C H^-1D`、RHS、transpose、back-sub | focused tests |
| iterative | 固定目标 p2 h5/3/2，MPI4，三残差 <=1e-6 | canonical records + automatic checker |
| memory | 所有 MPI ranks 总峰值 RSS；h2 迭代 13.08 GB | benchmark records |

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

## Benchmark 状态

重型 benchmark 只能写 `benchmarks/artifacts/`；`results/` 保留给 ordinary runs。Task28 V2 后 checker 额外核对 ID、qualified、KSP reason、coarse condition、physical model 与 actual/canonical artifact provenance。旧 h3/h2 artifacts 来自 source commit 的历史运行；record 分别保存实际来源命令/目录和规范重跑命令/目录，没有为元数据整改重复 h=2 重型计算。

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

## 参数域外使用

runner 会对偏离 canonical profile 的参数打印警告并写 `qualified_profile=false`。此类结果必须先与 direct/可信 reference 比较，并重新完成三残差、official R/T/A、能量闭合、总 RSS 和至少一个网格变化检查，才能升级状态。
