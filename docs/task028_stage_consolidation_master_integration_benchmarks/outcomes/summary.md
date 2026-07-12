# Outcome Summary

## 任务

Task028 从干净 `master` 收口 Task000-Task027：审计历史、选择性整合 Task026/027 稳定能力、重建用户文档，并建立可从 clean checkout 复现的 benchmark 体系。

## 分支

| 项目 | 值 |
|---|---|
| base | `master@0465b5f` |
| branch | `codex/20260712-task28-stage-consolidation` |
| whole research branch merge | 否 |
| ordinary default changed | 否 |

## 主要改动

| 类别 | 内容 |
|---|---|
| exact condensation | 新增 `src/solvers/condensed_dtn.py` |
| physical slab PC | 新增 `src/solvers/physical_slab_two_level.py` |
| target runtime | 新增 `src/solvers/stage4_runtime.py` |
| workstation runner | 新增唯一成功profile的 `benchmarks/run_workstation_iterative.py` |
| RSS telemetry | 普通3D summary新增所有MPI ranks总峰值 |
| tests | 新增凝聚与physical-slab MPI聚焦测试 |
| docs | 重建README/architecture/solver/schema/capability/benchmark |
| history | 选择性归档Task021-Task027核心闭环文档58份 |

## 物理模型

| 参数 | 值 |
|---|---|
| domain | 50 x 25 x 140 nm |
| grating | 17 x 25 x 120 nm |
| wavelength | 13.5 nm |
| incidence | theta_from_z=80 deg, phi=0 deg |
| polarization | s |
| element | N1curl p=2 |
| materials | Si complex refractive index |
| output | DtN modal R/T + A_volume |

## Workstation 数值设置

| 参数 | 值 |
|---|---|
| operator | exact matrix-free `F-C H^-1 D` |
| outer | right FGMRES, restart=100, rtol=1e-6 |
| coarse | 24 z intervals，25 nodes x 3 components = 75D |
| local PC | 16 complete physical z slabs，overlap=0.25 |
| owner policy | deterministic largest-first balance |
| factor | shifted-F ILU1 |
| smoothing | two fixed GMRES steps |
| MPI | 4 |

## 核心结果

| h/nm | FE DoF | iterations | reported residual | full residual | total peak RSS incl. RTA | total time |
|---:|---:|---:|---:|---:|---:|---:|
| 5 | 44,698 | 1201 | 9.83949e-7 | 9.83949e-7 | 1.987 GB | 127.3 s |
| 3 | 198,438 | 993 | 9.93265e-7 | 9.93265e-7 | 5.082 GB | 411.8 s |
| 2 | 615,108 | 1804 | 9.99738e-7 | 9.99738e-7 | 13.080 GB | 2538.8 s |

三组迭代数与 Task027 的 `1201/993/1804` 完全一致。h2 是本次整合分支从零装配、无旧 coarse/basis cache 的独立复跑；相对 Task027 cached run 的 12.958 GB 增加约 0.122 GB（0.94%）。

## Direct 与迭代对照

| h/nm | direct RSS | iterative RSS | direct residual | iterative full residual | 说明 |
|---:|---:|---:|---:|---:|---|
| 5 | 2.290 GB | 1.987 GB | 6.33e-12 | 9.84e-7 | 两者R/T/A差约1e-9 |
| 3 | 8.182 GB | 5.082 GB | 2.74e-11 | 9.93e-7 | 两者R/T/A差约1e-8 |
| 2 | 20.533 GB reviewed upper | 13.080 GB | 历史direct | 9.997e-7 | direct未重复消耗>20GB资源 |

## 能量检查

| h/nm | R | T | A_volume | R+T+A | closure |
|---:|---:|---:|---:|---:|---:|
| 5 | 0.0890216032 | 0.4425882752 | 0.4683901190 | 0.9999999974 | -2.55e-9 |
| 3 | 0.00461303245 | 0.5836533646 | 0.4117336036 | 1.0000000006 | 6.18e-10 |
| 2 | 0.00134293630 | 0.5992132418 | 0.3994438284 | 1.0000000066 | 6.58e-9 |

official power source 均为 `dtn_port_modal_amplitudes`。probe 和 sampled flux 仍仅作 diagnostic。

## 验证

| 检查 | 结果 |
|---|---|
| compileall / py_compile | 通过 |
| Ruff lint；新增文件format | 通过 |
| full unit suite | 80 passed，10 skipped |
| focused MPI4 | 每个rank 10 passed |
| 2D DtN smoke | residual 1.56e-15，R+T=1 |
| 3D Stage1 MPI2 | residual 1.39e-16 |
| h5/h3 direct rerun | 通过 |
| h5/h3/h2 iterative rerun | 全通过 |
| local Markdown links | 通过 |
| ordinary default | 未改变 |

## 已知边界

1. 该 profile 是固定目标模型的 mesh-robust workstation candidate，不是严格 mesh-independent 算法。
2. h=1.5 尚未达到同口径 production gate。
3. 新角度、波长、材料和几何尚未做参数鲁棒扫描。
4. spectral/GenEO/HPDDM、sampled-Schur、cached-Q 与 FE-only AMS 不进入普通 API。
5. h2 direct 已审查参考约需20.53 GB，本轮不在14 GB配置上重复运行。

## 下一步审查

ChatGPT 应重点审查：稳定模块是否仍有任务脚本依赖、普通 default 是否真的未变、h2 record 是否满足三残差口径、benchmark/artifacts 与 results 边界、以及历史审计分类是否合理。审查通过后可把 Task28 分支合并到 master；不建议继续合并 Task027 整个研究分支。
