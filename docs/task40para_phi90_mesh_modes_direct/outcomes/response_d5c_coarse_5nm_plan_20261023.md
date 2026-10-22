# D5C: 5 nm 粗网格单轴序列准备

本补充记录用户新授权的 D5C 序列，不改写历史 D5 输入、D5 运行或原 Task40 任务书。历史 D5-B 的物理参数、材料表、R5 模态实现可作输入来源；它的网格、FE 向量、因子和场结果均不作为 D5C 的运行复用对象。

机器可读轴计划、完整坐标、LE-f64 轴 SHA、每个输入 SHA、静态中点材料标签和轴向几何检查见[静态计划 JSON](records/d5c_static_axis_plan_20261023_v1.json)。该记录是 planner/metadata 证据，不是 live mesh QA 或 FE 结果。

## 网格表

轴段分界固定为 x=`[0,16.5,33.5,50]` nm、y=`[0,15,35,50]` nm、z=`[-10,0,120,130]` nm。每段均匀分格，周期和材料面端点精确保留。表中三段数依次对应各轴的三个材料区间；标签顺序为 air/substrate/grating，是独立几何中点分类的静态预测。

| 展示名 | x 段数 | y 段数 | z 段数 | cells | tags air/substrate/grating | 最大静态长宽比 | 相对 B 坐标嵌套 |
|---|---:|---:|---:|---:|---:|---:|---|
| D5C-B | 2/2/2 | 2/2/2 | 2/2/2 | 216 | 136/72/8 | 8.00 | 基准 |
| D5C-X1 | 2/6/2 | 2/2/2 | 2/2/2 | 360 | 216/120/24 | 21.18 | 是，x |
| D5C-X2 | 5/6/5 | 2/2/2 | 2/2/2 | 576 | 360/192/24 | 21.18 | 否，x |
| D5C-X3 | 7/6/7 | 2/2/2 | 2/2/2 | 720 | 456/240/24 | 25.45 | 否，x |
| D5C-Y1 | 2/2/2 | 2/6/2 | 2/2/2 | 360 | 216/120/24 | 18.00 | 是，y |
| D5C-Y2 | 2/2/2 | 5/6/5 | 2/2/2 | 576 | 360/192/24 | 20.00 | 否，y |
| D5C-Y3 | 2/2/2 | 7/6/7 | 2/2/2 | 720 | 456/240/24 | 28.00 | 否，y |
| D5C-Y4 | 2/2/2 | 5/10/5 | 2/2/2 | 720 | 440/240/40 | 30.00 | 否，y |
| D5C-Y5 | 2/2/2 | 10/6/10 | 2/2/2 | 936 | 600/312/24 | 40.00 | 是，y |
| D5C-Z1 | 2/2/2 | 2/2/2 | 2/6/2 | 360 | 264/72/24 | 2.67 | 是，z |
| D5C-Z2 | 2/2/2 | 2/2/2 | 5/6/5 | 576 | 372/180/24 | 5.00 | 否，z |
| D5C-Z3 | 2/2/2 | 2/2/2 | 7/6/7 | 720 | 444/252/24 | 7.00 | 否，z |

这些格数是用户指定的每段分配；X2/X3、Y2/Y3/Y4、Z2/Z3 并非 B 的逐点嵌套网格。Y3/Y4 都有 20 个 y 格，但分配不同，按同层数的两种网格分配单独比较。

B 在 z=0…120 nm 内只有两层、每层 60 nm。Y 系列最小步长为 1.5 nm，造成最高约 40 的静态单元长宽比。它们是明确需要观察的精度和求解风险，不构成改动用户网格或预判结果的理由。静态正体积只由轴差乘积确认；真实 Jacobian、单元标签和拓扑必须由每场 live mesh QA 再核。

## 不变合同与比较

全部输入由旧 5 nm 物理/材料设置派生，R5 矩形仍含传播与倏逝模态，不使用 D15 的 K1–K4 截断。固定模式数 3772、mode SHA `752333bb…aa531bc`，surface q39/default、volume q15/default、`scale_homogeneous_relative_only_v1` cutoff `1e-13`。方法仍为 p6 H(curl) 单元凝聚和直接 MUMPS；每场单独建立矩阵/因子，QA 与求解使用同一因子。

原门保持：凝聚相对残差 `1e-9`、独立原始 A6 有限 R5 active rectangle 残差 `1e-6`、能量 `1e-5`、至多两次同因子校正。该 A6 是冻结的 R5 active rectangle witness，不代表无限模态或完整 DtN。网格比较保持 global R/T/A_balance/A_volume `1e-5`、全 3772 signed 通道（含所有 power-carrying 模式）的逐通道 R/T `1e-6`、无相位拟合的边界复幅和同坐标复 E/H 相对 L2 `1e-4`。每个变体与 B 比较，并另列同轴相邻层级：X 为 B→X1→X2→X3，Y 为 B→Y1→Y2→Y3→Y4→Y5，Z 为 B→Z1→Z2→Z3；Y3/Y4 同为 720 cells 的分配差也单独比较。单场数值门通过不代表网格比较通过。

每场按标准 run_case 做独立 fresh，串行运行并在下一场前确认清场。输入为兼容旧 schema 保留 `warning_memory_gib` / `terminate_memory_gib` 字段；D5C 生效的监督合同是 `host_available_floor_v1`，64 GiB 主机余量下限、无固定 RSS cap、无 wall/solve deadline、swap 只观察，标准 manifest 应记录 `legacy_resource_fields_enforced=false`。其余合同为父 CPU9/worker CPU24、MPI1/math1、NUMA interleave 0–1、PSS/USS/smaps 关闭；仅承认逐场精确绑定的 Task41 并行例外，未知 solver 仍拒绝。粗单元数不保证 MUMPS 内存或时间，fresh 准入和运行期 RSS 监控仍需逐场通过。

## 当前验证状态

定向测试覆盖 12 个输入的 resolver/profile、真实 stage4 planner 坐标、独立中点标签、直接 runner 的实际 mesh-evidence 接口、manifest→worker payload gate，以及旧 D5 回归。最新定向回归共 `103 passed`，覆盖 D5C 12 组 resolver/profile/mesh/manifest-worker、旧 D5 回归及 Task41 并行例外的 12 组精确 profile/run_id 正例、错配拒绝和默认拒绝。另有 Ruff、compileall 与 diff-check 通过；尚未创建 FE mesh、MUMPS 因子或运行 D5C 场。`resolved_config_sha256` 将在每场标准输出目录绑定后生成，当前静态计划未冒充正式 resolved 身份。
