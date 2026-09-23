# Task39extra：p4版本后续提速与分阶段线程研究备忘

## 0. 身份与用途

```text
repository = Rookie1234567/MyFEniCS
branch = task39extra
record_date = 2026-09-23
reviewed_base_SHA = 55ceb4c84a9041f715dc0c34c72fca689e753cce
current_review_response = review_report_v25.md / response_v28.md
status = RESEARCH_DIRECTIONS_RECORDED_NOT_EXECUTED
```

用户要求记录A6/H6值得尝试的优化，并提出：在内存较低的setup阶段使用多线程，完成后切回单线程迭代，争取总峰值不增加。

本文只记录讨论、技术判断和后续任务设计依据，不是新review或重型运行授权。不修改当前数值配置、历史线程合同、资源政策、ordinary default或其他分支；未实施线程切换，未启动PDE。后续执行须由用户指令或新review明确授权。

最终目标仍为约2 TB整机内存内的0.7 nm任意非可分三维周期Maxwell。下面的本机固定案例收益不能外推为目标规模资格。

## 1. 保留的p4研究主线

**固定p6外层、准确p4凝聚逆与BAL_H/H6，优先优化公共细层内核。p3以后复用这些改进，并进行相应回归，不在本阶段重复粗阶筛选。**

### A. A6体积作用的公共步骤融合

现有curl与mass分别调用完整作用，见[组合动作](../../src/solvers/fullspace_physical_action.py)和[物理快速后端](../../src/solvers/physical_equivalent_fast.py)。候选是共用输入gather、方向处理、Nédélec到多项式系数转换，在原积分规则下分别计算两项，再尽可能共享反向转换和scatter。

不同积分点的curl/mass仍保留各自规则，不为融合降低积分；slave identity只计一次，Floquet共轭与主从语义不变。保留独立native A6见证，不把新内核用作唯一oracle。共享参考数据不等于已经共享在线运算；当前尚无融合后的实测收益。

### B. A6/H6张量收缩中的共同子表达式

检查[张量积内核](../../src/solvers/fullspace_n1e_sum_factor.py)中六个交叉导数的共同前向收缩及反向投影，减少重复算术与搬运。固定批量及有界scratch，不把曾未获收益的projection-buffer开关原样重新包装成新成果。

### C. 相同积分定义下的局部矩阵生成

最新定位显示p6凝聚准备的大头是完整单元矩阵生成，不是局部LU或hash。后续可研究同积分的分块Gram矩阵乘法或张量化矩阵生成；完整物理项相加后再凝聚，不分别凝聚curl与mass。此方向与下面的类型并行可以独立选择，不要求同时更换积分内核和线程模型。

## 2. 已知规模、时间与内存边界

全部为13.5 nm original、p6/h7.5、990单元、80通道、q4；GB=10^9 B。

| 对象 | 数值 | 身份与证据 |
|---|---:|---|
| r2完整workflow / setup / KSP | 3114.283619607013 / 781.971881371981 / 2284.681783819 s | measured；[V26对照记录](outcomes/records/setup_efficiency_v26_compact.json)绑定r2历史字段 |
| r2全树RSS峰值 | 7390937088 B | measured；[r2记录](outcomes/records/v25_q4_ac_swap_observe_r2_result.json) |
| 较早同模型Q4 setup / 全流程RSS | 7147806720 / 7389360128 B | measured；[Q4记录](outcomes/records/a6_h6_coarse_degree_v25_q4.json)，不是r2阶段峰值 |
| 上一行差值 | 241553408 B，约0.242 GB | derived；仅说明晚期setup距总峰值可能很近，不是新任务可直接使用的安全额度 |
| V27 attempt04 p6 raw kernel | 228.84196730799158 s；12类raw tensor | measured engineering，非新PDE；[Response V28](response_v28.md) |
| 同一attempt的p6局部Schur / 内部setup | 11.954928313018172 / 249.1300467460096 s | measured，父子区间不可相加 |

当前p4 stack建立后，H6/retained adapter继续构建；p6缓存并不天然都在大factor之前。代码入口见[完整求解组织](../../src/runners/physical_p4_schur_v14.py)和[外层适配器](../../src/runners/physical_retained_outer_adapter.py)。因此“setup全部内存低”不是现有记录支持的结论。

## 3. 用户的分阶段线程想法：可行，但峰值中性有条件

总峰值是各阶段峰值的最大值，不是各阶段峰值之和。因此允许低内存阶段使用适量额外临时空间，只要它不制造新的更高峰值，且不遗留额外常驻内存。

```text
M_peak,new = max(M_setup,parallel, M_factor,new, M_iteration,serial,new, M_post,new)
```

保持原峰值至少需要：并行局部准备和factor阶段都不超过原预算；切回单线程后，仍需保留的数据布局、factor和工作集没有增加；线程栈、运行库缓存和allocator保留内存计入实测。仅把活动线程数改为1，不是释放这些对象的证明。

**推荐首先验证“局部准备并行，p4 numeric和外层迭代仍单线程”，而不是一开始把整个setup统一开多线程。** 并行MUMPS属于独立条件候选，不能默认分解内存不变。

## 4. 优先候选：前移并行局部准备，避免与大因子叠峰

```text
串行冻结网格、材料、FE、积分与只读kernel输入
→ 必要JIT串行完成，编译不与大factor重叠
→ p6实际raw tensor类别用2个worker线程并行生成
→ join全部worker，释放临时缓冲，保留唯一数值结果
→ 准确p4装配和numeric按已验证单线程执行
→ 完成p6后续单元消元、H6、桥和其余必要准备
→ 明确验证线程限制为1
→ 原单线程FGMRES、完整原A6核验和后处理
```

这是候选依赖重排，不是当前已实现的顺序。优先只前移raw tensor生成，不提前建立全套p6缓存或Krylov工作集，后续借用已生成结果而不重复计算。只前移不依赖p4解或H6窗口的p6局部数据；保留相同源码/物理/积分身份，不保存跨进程全局因子。前移后的p6常驻缓存可能抬高factor阶段峰值，也必须纳入整个生命周期；不能只报告前面并行阶段较低。

现有[raw tensor cache](../../src/solvers/hcurl_assembly_time_condensation.py)对12类分别调用CFFI kernel。可在主线程准备只读输入与函数入口，让各worker只调用已编译的纯局部核并写独立输出；最终缓存登记、方向映射、全局装配、PETSc和MPI操作由主线程执行。不并发写同一tensor，不并发调用同一MUMPS对象，不复制整个求解进程。

CFFI通常会在进入C库时释放GIL，但这不保证被调核可重入。先核对实际生成核是否有可写静态数据、共享scratch或回调；每个线程独立输出和临时数据。不得仅因接口是CFFI就宣称线程安全或已经并行。

设置BLAS内部线程为1，再在外层并行局部类别；不要形成“4个worker各调用4个BLAS线程”。2线程先验证，4线程仅在内存/CPU资源和实测收益支持时考虑。此处是后续实验建议，不授予当前运行权限。

## 5. 线程切换及内存实测要求

受支持的BLAS/OpenMP运行库可以使用runtime API控制线程数；仅在Python运行中修改OPENBLAS_NUM_THREADS或OMP_NUM_THREADS环境变量，不能视为已完成切换。threadpoolctl是可核验的候选工具，不是已确认安装或能控制本机全部库。

主线程在阶段边界统一设置线程上限，所有worker完成后再切换；不要在并发worker内部争抢修改进程级线程策略。读取实际加载库及线程状态；缺失原生支持就保留单线程，不升级整个ABI来强行实现。核对CPU affinity/cgroup，不能让新增worker仍全部绑在一个核。

停止worker活动不等于其栈或库缓冲已回到系统；共享线程也不等于零额外内存。目标是不增加全流程实测峰值，而不是每个阶段字节数必须完全一样。应报告setup、factor、切换后、KSP和全流程RSS/PSS，并单列新增scratch、常驻payload及后端allocated/used；采样精度及跨次波动如实保留。

MUMPS numeric若另行并行，先核对实际PETSc/MUMPS及BLAS构建支持，保持矩阵、排序、主元和精度合同，不推定并行后的factor/workspace大小等于串行。转换回单线程不改变已产生的分解成本与存储。

原A4有界精化、原A6<=1e-6、同p6场/模式/功率回归不变；允许合格的浮点求和差异，不要求所有hash或迭代数机械相同。资源安全、系统余量及监督合同由下一份正式授权规定，本文不修改它们。

## 6. 收益量级与后续排序

仅对228.84秒局部核作理想平均分工：2线程约可省114.42秒，4线程约可省171.63秒。这是derived的无开销理想情景，不是实测或性能承诺；线程调度、核大小差异、带宽及CPU状态均会影响结果。

r2完整setup约13.03分钟；若假设整个setup耗时减半且其他不变，完整流程约45.39分钟，而非25.95分钟。实际只并行一部分setup时收益更小。因此阶段并行值得做，但不替代A6融合与H6共同收缩对约38.08分钟迭代段的研究。

建议后续review先明确一个“阶段局部并行+单线程迭代”的受控实现，和一个公共A6/H6算术优化；局部测试无需无关的p4全局factor，组合后再用同p6/h7.5做完整回归。不给尚未运行的组合填入r2速度或低内存资格。

## 7. 外部接口依据

以下为2026-09-23核对的上游文档，不代表本机已安装相同版本或所有能力可用：

- [CFFI线程安全与GIL](https://cffi.readthedocs.io/en/latest/overview.html#thread-safety)：调用C库释放GIL不提供底层共享数据的线程安全保证。
- [threadpoolctl](https://github.com/joblib/threadpoolctl)：可按代码区间限制受支持库，控制具有进程级影响，不应在多个worker里并发切换。
- [OpenBLAS运行变量](https://www.openmathlib.org/OpenBLAS/docs/runtime_variables/)及[使用说明](https://github.com/OpenMathLib/OpenBLAS/blob/develop/USAGE.md)：启动环境、runtime控制与缓冲配置不是同一件事。
- [oneMKL线程缓冲](https://www.intel.com/content/www/us/en/docs/onemkl/developer-reference-c/2026-0/mkl-thread-free-buffers.html)：运行库可能保存每线程内存池；此例不表示本机采用MKL。
- [PETSc/MUMPS](https://petsc.org/release/manualpages/Mat/MATSOLVERMUMPS/)：并行能力取决于实际构建；不把新版本控制项直接套用旧ABI。

本文仅为研究备忘，未执行项目测试、线程实验或PDE。
