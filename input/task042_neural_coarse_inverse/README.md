# Task042 固定模型与受控共享运行输入

| 文件/组 | 一次明确运行的含义 | 实际范围 |
|---|---|---|
| `frozen_model.json` | 从base指定种子只读提取的physics/离散/采样 | original13.5nm、1°/phi0/s、p6/h10、同网格p4，未扫描 |
| `shared_profile_v1.json` | 用户共享授权、资源/线程/B0/inner/data/ranks/MLP及hash-bound资格 | CPU-only，16GiB整树、线程1、自有锁，所有Gate保留 |
| `f1_b0_shared*.dat` | 各一次独立F1完整p6/p4组件与8RHS B0 capture | 初次+4次局部实现修复均保留；retry4实际接口通过，B0非零失败 |
| `f1_reference_shared.dat` | 预备独立F1参考8RHS的研究输入 | 此独立dat `not_run`；实际参考8项在F2-teacher记录，不重复运行 |
| `f2_teacher_shared.dat` | 唯一原p4 operator，8参考及256/64/64数据，各batch<=32 | offline global LU仅本进程，逐对审核；退出后才能下一阶段 |
| `f2_oracle_shared.dat` | 同原p4、train/validation POD与4个固定rank诊断 | 无global LU；最高rank预登记正信号才继续 |
| `f3_train_shared.dat` | 单一residual MLP，隔离CPU-only FP64训练/冻结导出 | rank128、2hidden64、300epochs/7200s有载上限，validation选epoch |
| `f4_b0_shared.dat` | 固定B0、16未见RHS严格粗返回 | RIGHT32/max256/零初值，每次原A4/port/recovery<=1e-10 |
| `f4_linear_shared.dat` | 同B0+线性rank128，完全相同16RHS | 同精度/表示/归一化/数学线程/source，不读heldout teacher解 |
| `f4_neural_shared.dat` | 同B0/basis，冻结FP64 NumPy MLP，完全相同16RHS | 实际Torch probe再核验；无FE Torch/teacher因子共驻留 |
| `requirements-*`、`pre_size_memory_model.json` | 隔离依赖/解析lock及构建前尺度和容量预算 | 不是内存实测或数值资格；实际记录见outcomes |

所有research profile显式opt-in，普通case默认不变。一个dat只启动一个阶段，组件多RHS库存明示，不把teacher或capture当正式多场PDE。F4三路线均未通过，本轮没有F5输入、三次合格计时或p6物理输出；没有5/2/0.7nm、参数扫描或后台等待启动器。

重现任一FE阶段需干净已提交源码、已资格F1/teacher/basis及本地hash-bound artifacts。每次先按用户共享授权现场只读资源核查，runner选择当时空闲的物理核，不能硬编码CPU14或假定CPU0永远空闲：

```bash
cd /home/fenics/Projects/NN-Lab
source scripts/activate_task042.sh fe
python scripts/run_case.py input/task042_neural_coarse_inverse/f4_linear_shared.dat
```

训练独立`source scripts/activate_task042.sh ml`后使用`f3_train_shared.dat`。本轮交付后停止等待review，不自动执行这些重现命令；heldout16已consumed，不能用重放结果选型后继续称fresh终测。CPU ML Torch显式float64、intra/inter1、DataLoader0；编译/teacher/FE/后处理也限制线程1，只降低Task042自身优先级。

原物理SHA为`9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f`，F1真实p4 Schur CSR身份为`150f18e26f15783726f2ffeb362ef053450962a16fff13d5241cc93c8d018560`。完整branch/source/input/model provenance、失败、时间/内存及资源影响见[实际交付](../../docs/task042_neural_coarse_inverse/outcomes/summary.md)与[response_v2](../../docs/task042_neural_coarse_inverse/response_v2.md)。

## Review V1 的 V4 显式输入（旧输入合同保留）

全局空间保存少量跨域误差方向，并在原几何局部修正前后协调这些方向；它增加有界基存储和一次S作用，不能保证全局收敛。数值算法位于 `learned_two_level.py`，沿用原参数化入口，仅新增研究阶段编排。

| 单一dat / stage | 明确inventory | 运行前Gate |
|---|---|---|
| `v4_p0_shared.dat` | 同真实S的3方向配对和rank4复数两层检查 | clean source、ABI、共享资源、own lock |
| `v4_p1_shared.dat` | 原train固定16题，各最多64步/8误差快照 | P0通过；局部B停滞仍是有效采样 |
| `v4_p2_error_shared.dat` | 仅P1最多128个误差，固定秩规则，一条ERROR空间 | P1完成，构造前容量检查 |
| `v4_p2_oldpod_shared.dat` | 仅旧Q、截取后同Schur编码，一条OLDPOD空间 | ERROR空间审计完成，包括真实blocked |
| `v4_p3_oldpod_shared.dat` | frozen OLDPOD，已消费0/10/11各一次256上限 | 两个P2均完成；本路线数值合格 |
| `v4_p3_error_shared.dat` | frozen ERROR，同三题各一次256上限 | 同上；不改patch/shift/rank/预算 |
| `v4_p4_generate_shared.dat` | 同一已登记16项fresh RHS，只保存RHS数组后退出 | P3选择冻结、测试未消费；无候选PC、无teacher因子 |
| `v4_p4_shared.dat` | 条件冻结一条路线；seed420620，零+5族×3变体 | P3独立分流/选择通过，测试未消费，先冻结再生成 |

唯一配置为 `two_level_v4.json`；原task/review、V3几何PC及普通默认不改。每个worker退出、整树清场后才发布hash-bound阶段索引；P4消费标记采用独占创建防止重复终测。所有成本shared-workstation，monitor每步只保存廉价KSP标量，原方程在0/restart/final/异常及真正成功返回时检查；无NN/GPU/F5/短波。

P4的制造解只存在于独立RHS生成worker；清场后验证worker只读`rhs_fe/rhs_port`，packet中出现solution或initial_guess键即拒绝。该实施隔离在P1清场后、任何fresh数组生成前补齐，不改变随机序列、候选、16项库存或预算；已完成P0/P1的数值核心blob不变，不重跑它们。

## Review V2 的 V5 固定对象诊断输入

本批把同一保存状态留下的残差分别交给局部作用、粗空间和原两层作用，判断空间覆盖与投影是否分别限制效果；它测有限修正和最多16个补空间方向，增加审核成本，不开发或资格化新求解器。原S、B与两套Z/U/R逐字节冻结，数值诊断在`learned_fixed_localization.py`，唯一预登记为`localization_v5.json`。

| 单一dat / stage | 固定库存与进程边界 | Gate |
|---|---|---|
| `v5_d0_shared.dat` / V5-D0 | 原0/10/11的零初值particular recovery、V3 GEO和两V4最终状态，最多12项 | Git/ABI/资源；从保存向量独立重算，缺项不重跑KSP |
| `v5_d1_shared.dat` / V5-D1 | 同12项、逐个加载旧空间；仅三个已消费teacher离线检查误差覆盖 | D0释放；无新因子，只输出标量和hash，不输出准确解/系数 |
| `v5_oldpod_shared.dat` / V5-OLDPOD | 原OLDPOD，同D0库的B/C/B2及两小LS；固定补空间探针 | D0释放，固定对象/512MiB容量；不加载teacher或D1参考输出 |
| `v5_error_shared.dat` / V5-ERROR | 原ERROR，完全同库和规则，另一个worker | 上条同样的Gate；一次一个Task042阶段，先退出再换空间 |

四个dat均使用既有`run_case.py`、own lock和16GiB整树监督；候选不会读取seed420620新池、训练、重编码基、调用长KSP或进入F5。诊断最小二乘最多129列，以固定相对1e-10处理依赖方向，仅作反事实，不能反馈给求解器。全部成本为shared-workstation，完成后等待review，下一试验只建议而不实施。


## V7当前入口：用户材料固定后续跑

[Review V4](../../docs/task042_neural_coarse_inverse/review_report_v4.md)解除V6材料定义缺失。canonical材料为 [../materials/si_optical_constants_v1.json](../materials/si_optical_constants_v1.json)，ID `SI_OPTICAL_CONSTANTS_USER_20260929_V1`；0.7／2nm用户原值与5／13.5nm冻结旧输入均可离线读取，仅使用已授权alias。V7新输入另命名，V6 unresolved设计／dat和全部旧结果不覆盖。真实N1通过才运行三条路线，不重装环境或复活旧p4路线；每run须保存材料ID/hash、有效n／epsilon、完整端口与physical/source identity。


## V8 单次尺度与执行校准 opt-in

唯一冻结计划为 [calibration_v8.json](calibration_v8.json)。v8_reuse_inventory／v8_column_setup／v8_scaled_lsqr／v8_scaled_verification／v8_batch_equivalence各dat一stage；另六个v8_pair1–3_batch1或8按计划顺序各一独立micro。入口仍scripts/run_case.py＋Task042独立activation，canonical材料表复用；不扩模型或训练，结果见 [Response V8](../../docs/task042_neural_coarse_inverse/response_v8.md)。
