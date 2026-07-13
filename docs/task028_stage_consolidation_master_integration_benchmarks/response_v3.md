# Response V3：Task028 最终文档、Benchmark 与 2D 有损端口闭环

## 1. 总体回应

`review_report_v3.md` 的 15 项 P0 和 3 项 P1 已在同一 Task28 分支完成。核心求解器、ordinary direct 默认和既有 3D canonical 结果没有被改写；本轮新增真实数值只限 Case002/003 的轻量 2D canonical harness。

```text
branch = codex/20260712-task28-stage-consolidation
source evidence commit = e89fb632bb4318a739afd1ee702be3a17d109d7c
master merge = 未执行
h2 direct/iterative rerun = 未执行
Task29 = 未启动
review response status = ready_for_final_review
```

## 2. Worktree 迁移

V3 开始前已从远程 fast-forward 拉取 `review_report_v3.md`，把 Task28 分支迁回原项目目录：

```text
C:\Users\admin\Desktop\Code\fenics_vector_maxwell_floquet_demo_v2_parallel
```

Git worktree 登记只保留该原目录。占用旧目录的 6 小时残留测试容器在确认串行 `21/21 OK`、MPI 阶段挂起且当前原目录 MPI4 替代验证通过后被单独删除；旧空目录和迁移临时备份也已删除。用户未跟踪的 `papers/` 和 Task23 `raw_runs/` 保持不变且不进入提交；Task23 `system_metadata.json` 的 SHA-256 迁移前后均为 `9288C495...97616FBA`。

## 3. P0 逐项关闭

| P0 | 处理 | 证据 |
|---|---|---|
| 1. 2D lossy records | 冻结 TM/TE 两份完整轻量 record | Case003 `records/` |
| 2. lossy automatic gates | residual、非负、closure、A balance、aux/trace、probe identity | `check_benchmarks.py` |
| 3. lossless regression | zero contrast、Fresnel、below-cutoff 零功率、lossy propagating 正功率 | test03/test20、Case002 |
| 4. demo/target preset | demo 四个重命名；target h5/h3 直接复用唯一工厂 | `src/main.py`、test27 |
| 5. preset 资源身份 | 17 个 preset 均有 geometry/discretization/resource/status | `--list-presets --verbose` |
| 6. PyCharm MPI4 | External Tool 与 wrapper 两套真实配置 | Quick Start 40、Case031 |
| 7. Quick Start 深度 | 15 篇核心教程均为 16 节、103 至 181 行 | test26 |
| 8. 技术错误 | 修正 coarse vector 字段、PC 顺序、显式 inverse、H=I 限制 | walkthrough 31-33、theory |
| 9. Walkthrough 深度 | 11 篇核心文档均超过 100 行并含源码/尺寸/ownership/公式/Gate | test26 |
| 10. case-contained | 13 cases 均有 README + config/fixture + expected + run/test | cases + checker |
| 11. Case002 双解 | 同网格 explicit/auxiliary 完整 solve、场与 RTA 比较 | 3 records |
| 12. Case003 records | TM/TE 有损 records 与 artifact provenance | 2 records |
| 13. Case021 对齐 | target h5/h3 preset 与 `target_stage4_config` 逐字段相等 | test27、Case021 |
| 14. Case031 PyCharm | MPI4、candidate record、禁止普通单进程 qualification | Quick Start/Case031 |
| 15. 文档 contract | 深度、结构、records、技术错误、命名、链接均自动检查 | 11 个 test26 tests |

## 4. Case002：完整 explicit/auxiliary 等价

同一 10 x 10 nm、无损零对比、p1/h2 离散分别运行两次：

| 指标 | explicit | auxiliary |
|---|---:|---:|
| FE DoF | 139 | 139 |
| auxiliary DoF | 0 | 2 |
| matrix rows | 139 | 141 |
| matrix nnz | 727 | 673 |
| reduced rows | 133 | 135 |
| reduced nnz | 721 | 667 |
| true residual | 2.168271e-15 | 1.867404e-15 |
| elapsed/s | 8.334 | 2.811 |

```text
field relative difference = 2.7711962846232144e-15
max absolute R/T/A difference = 1.2212453270876722e-15
R = 0.000477654763895
T = 0.999522345236104
lossless closure = machine precision
```

这次比较使用 full FE coefficient array，而非只比较 auxiliary 与 trace 功率，因此同时保护矩阵、RHS、约束、解和后处理。

## 5. Case003：TM/TE complex absorption

两个 variant 各自冻结完整 resolved config；它们用于覆盖不同代码路径，不用于比较 TE/TM 数值大小。

| 指标 | TM auxiliary DtN | TE scalar DtN |
|---|---:|---:|
| geometry period/air/substrate nm | 100/100/50 | 10/5/5 |
| FE + auxiliary DoF | 14,452 + 30 | 56 + 0 |
| matrix rows/nnz | 14,482/247,114 | 56/418 |
| true residual | 3.322514e-14 | 1.485629e-15 |
| process peak RSS/MB | 365.30 | 287.48 |
| R | 3.662521e-6 | 8.745627e-5 |
| T | 0.8821724521 | 0.9903457798 |
| A_balance | 0.1178238854 | 0.0095667639 |
| A_volume | 0.1178238854 | 0.0095667639 |
| energy closure | -3.331e-15 | 5.829e-16 |
| probe closure | -0.021317 | 0.075125 |

TM auxiliary-vs-trace 最大绝对差为 `1.221e-15`。probe 明确保存 `identity=diagnostic_only` 和 `must_not_replace_official=true`。

## 6. 2D 有损修复影响范围

V2/V3 改变的是 2D lossy DtN/probe modal power 口径：

1. complex beta 的传播判据不再要求 `Im(beta)=0`；
2. 功率使用实际端口平面 coefficient，不使用搬回 reference plane 的报告振幅；
3. phase-normalized amplitude 仍保留用于相位解释；
4. 无损逻辑由 Case002、Fresnel 和 mode helper 回归保护。

3D Task27/28 official RTA 使用独立 `modes_3d/dtn_port_3d/rta_3d` 路径，本轮没有因 2D 修复重算 h5/h3/h2。

## 7. Preset 身份修正

```text
3d_stage4b_demo_direct_h5
3d_stage4b_demo_direct_h3
3d_stage4b_demo_mumps_ooc
3d_stage4b_demo_mumps_blr

3d_target_grating_direct_h5
3d_target_grating_direct_h3
```

target preset 由 `src/common/config_3d.py::target_stage4_config` 生成，只将 assemble-only 改为真实 direct solve。17 个 preset 分为 6 个 2D 与 11 个 3D；普通默认仍是轻量 Stage1，iterative 不由 main 静默启动。

## 8. Walkthrough 技术修正前后对照

| 主题 | 旧描述 | V3 准确描述 |
|---|---|---|
| `SparseCoarseVector` | 含 `global_size` | 字段为 indices/values/slab/eigenvalue/eigenpair_residual |
| 两级 PC | coarse-first | smoother -> residual -> coarse -> optional post-smooth |
| `SmallDenseInverse` | LU/factor | `np.linalg.inv(H_dense)` 显式 inverse |
| explicit condensation | 一般 H | 仅已验证 `H=I`；其他 H 抛 `NotImplementedError` |
| 3D DtN | 函数职责摘要 | 完整追踪 `(m,n,pol)` 到 C/D/H、RHS、a、R/T |

## 9. 文档深度与理论统一

| 层 | V3 contract |
|---|---|
| Quick Start | 15 篇核心教程，均有 16 个操作章节 |
| Walkthrough | 11 篇核心主线各 >=100 行；15 篇总覆盖 |
| Theory | 增加 2D/3D 坐标、法向、alpha/gamma/beta、TE/TM/s/p、F/C/D/H、R/T/A 统一表 |
| Power | 明确 2D 单位长度与 3D 单胞面积的 code-unit 常数差异 |
| Benchmark | 13 case README 均展开 8 个说明章节，不再只有摘要表 |

2D TM 弱式中的多余逗号已修正；代码引用优先使用 `module::function`。绝对 code-unit 功率不得跨 2D/3D 直接比较，归一化 R/T/A 可以比较比例。

## 10. Case-contained Benchmark

Recorded cases 002/003/010/021/031 均具有 `config.json`、`expected.json`、`run.sh` 和 records。Test-backed/experimental cases 具有显式 expected status 和 run/test command；022/040 用 fixture，030 保留 direct profile config。

Case010/021/031 的 case-local reference 通过 SHA-256 指向顶层 canonical records；Case031 candidate 输出默认写 ignored artifact，禁止参数扫描覆盖 canonical JSON。

## 11. 自动验证

| 检查 | 结果 |
|---|---|
| Docker compileall | pass |
| Ruff check/format | pass |
| full DOLFINx unittest | 115 passed，10 skipped |
| MPI4 condensation/PC | 4 ranks，各 14 passed |
| documentation contract | 11 passed |
| named presets | 17，全部真实 parser 接受 |
| benchmark checker | 143/143 passed |
| local Markdown links | pass |
| `git diff --check` | pass |

10 项 skipped 均为已有环境/可选后端条件，不是失败。

## 12. 保留限制

1. Stage2B PML、Stage2C Fresnel 仍为 experimental accuracy。
2. workstation iterative 只资格化 frozen p2 target、MPI4、h5/h3/h2 和固定 PC 参数。
3. h=1.5、near-Rayleigh、角度/波长/材料/几何鲁棒性未关闭。
4. complex MPC 基础镜像仍无公开 pull source，环境为 `qualified_local_image`。
5. `SmallDenseInverse` 显式 inverse 与部分内部 helper 依赖是非阻断技术债。

## 13. 合并建议

Task28 V3 已具备最终审查条件。建议审查通过且用户明确许可后再合并 `master`；不整体合并历史 research branches，不提交 `papers/`、raw runs、mesh、VTU、cache 或 OOC factors。
