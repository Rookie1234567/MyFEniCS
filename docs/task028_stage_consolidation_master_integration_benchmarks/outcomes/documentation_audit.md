# 文档审计

## 审计范围

本轮从真实入口、runner parser、配置 dataclass、弱式、边界算子、求解器、后处理、tests 和 canonical records 反向核对文档，禁止仅按文件名推断能力。文档采用五层职责：Capability/Progress、Quick Start、Code Walkthrough、Theory、Benchmark。

## 五层信息架构

| 层 | canonical 入口 | 职责 | 自动检查 |
|---|---|---|---|
| Capability / Progress | `docs/capability_matrix.md`、`docs/development_progress.md` | 能力状态、开发进度、限制 | 状态与用户入口映射 |
| Quick Start | `notes/quick_start/README.md` | PyCharm/CLI 操作、参数、输出、错误处理 | 文件和相对链接 |
| Code Walkthrough | `notes/reference/code_walkthrough.md` | 模块、符号、数据流、对象生命周期 | 索引和链接 |
| Theory | `notes/theory/README.md` | 强式/弱式、边界、功率、求解器依据 | 索引和链接 |
| Benchmark | `benchmarks/cases/README.md` | 冻结问题、证据、Gate 和限制 | 13 cases、22 字段 |

## Quick Start

| 项目 | 数量/状态 | 结论 |
|---|---:|---|
| canonical 文件 | 17 | 覆盖环境、参数、输出、2D、3D、direct、iterative、scan |
| 旧指南 | 8 | 保留，不删除；增加历史/迁移提示 |
| PyCharm preset | 15 | 6 个 2D、9 个 3D |
| CLI 等价入口 | 全部 | preset 参数由真实 parser contract 验证 |
| qualification 说明 | 全部新指南 | 区分安全修改、超出验证域和 experimental |

## Code Walkthrough

总索引之外新增 15 篇逐模块文档，覆盖全部当前稳定路径：

| 范围 | 覆盖内容 |
|---|---|
| 入口 | `src/main.py`、2D/3D runner dispatch |
| 2D | config、mesh/material、TM/TE 弱式、Floquet、PML、Robin、DtN、RTA |
| 3D | Stage1/2A/2B/2C/4A/4B、double Floquet、PML、DtN、RTA |
| Direct | PETSc/MUMPS、OOC、BLR profile 与生命周期 |
| Iterative | exact condensation、75D coarse、physical slabs、sm2、FGMRES runtime |
| 输出与质量 | result schema、ParaView、tests、benchmark contracts |

每篇均包含文件职责、关键符号、输入输出、调用者、理论映射、测试和已知限制；`src/solvers/_old/` 明确为弃用历史。

## Theory

| 主文档 | 理论范围 | 代码映射 |
|---|---|---|
| `maxwell_strong_weak_and_fem.md` | 时谐 Maxwell 强式、弱式、H(curl)、TE/TM | 2D/3D forms |
| `floquet_periodicity.md` | Bloch/Floquet 相位、配对、衍射阶 | MPC/constraint builders |
| `pml_robin_and_open_boundaries.md` | 复坐标拉伸、PML 张量、Robin | 2D/3D PML 与 port forms |
| `dtn_modal_ports_and_condensation.md` | DtN、explicit/auxiliary、Schur 凝聚与回代 | DtN/condensed modules |
| `official_and_diagnostic_rta_methods.md` | modal power、Poynting、A_volume、身份 | `power_metrics.py`、3D RTA |
| `3d_stages_and_validation_ladder.md` | Stage1 到 Stage4B 的增量验证 | stage runners/solvers |
| `direct_solvers_and_factorization.md` | MUMPS、OOC、BLR | direct profiles |
| `iterative_solver_and_preconditioner.md` | FGMRES、slab Schwarz、coarse、sm2 | workstation runtime/PC |
| `research_routes_and_negative_results.md` | 负结果与适用边界 | research-only history |

理论不是孤立公式：每篇均回链 Code Walkthrough、Quick Start、tests 或 benchmark，并引用官方/原始来源。

## Benchmark catalog

| ID | 功能 | 当前声明 |
|---|---|---|
| 001 | 2D TM PML + Floquet | path smoke，非精度证明 |
| 002 | 2D TM DtN explicit/auxiliary | 等价性 test-backed |
| 003 | 2D TE/TM complex absorption | test-backed + 本轮真实有耗 smoke |
| 010 | 3D Stage1 | 验证 |
| 011 | 3D Stage2A double Floquet | smoke/test-backed |
| 012 | 3D Stage2B PML | experimental/not_verified_accuracy |
| 013 | 3D Stage2C Fresnel | experimental/not_verified_accuracy |
| 020 | 3D Stage4A flat DtN | sanity/energy path |
| 021 | 3D Stage4B direct | h5/h3 records，h2 reviewed reference |
| 022 | DtN condensation | algebraic equivalence test-backed |
| 030 | MUMPS OOC/BLR | direct fallback，非独立迭代法 |
| 031 | workstation iterative | h5/h3/h2 qualified records |
| 040 | MPI/p/algebraic regression | regression collection |

每个 case 文档均包含审查规定的 22 项字段。没有 canonical record 的 case 明确说明证据来自测试或仅为实验路径。

## RTA 文档一致性

| 方法 | 文档身份 | 代码审计结果 |
|---|---|---|
| auxiliary modal amplitudes | official/recommended | 2D/3D 主 R/T |
| boundary trace/modal projection | reference/cross-check | 与 auxiliary 共用模态基 |
| volume absorption | official | 有耗材料积分 |
| E/H Fourier probe | diagnostic_only | 不替代 official closure |
| sampled Poynting/net flux | diagnostic/consistency | 依赖采样面和分辨率 |

有耗介质功率文档已同步实际代码：complex `beta` 可以携带实功率，功率使用实际端口面 coefficient，参考面归一化 amplitude 仅供报告。

## 一致性与自动 Gate

| 检查 | 结果 |
|---|---|
| Quick Start 索引文件存在 | pass |
| Walkthrough/Theory 索引链接 | pass |
| 全部本地 Markdown 相对链接 | pass |
| 13 benchmark case 模板 | pass |
| Stage2B/2C 状态 | experimental/not_verified_accuracy |
| capability -> usage/theory/benchmark | pass |
| 15 preset 名称唯一且 parser 接受 | pass |
| invalid `stage2_all/stage4_all/both` | 不存在 |
| ordinary default | Stage1 lightweight direct |
| iterative MPI4 requirement | 显式可见，不由普通 main 静默启动 |

## 保留边界

Task021-Task027 的 58 个核心闭环历史文件继续保留；未加入 raw runs、mesh、field、cache 或其他大型 artifacts。普通求解仍写 `results/`，正式 benchmark 重型产物写 gitignored `benchmarks/artifacts/`。
