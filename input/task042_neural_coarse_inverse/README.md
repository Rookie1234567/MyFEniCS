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
