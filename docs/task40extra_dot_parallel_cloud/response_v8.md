# Response V8：centered p2 原方程与 dense→sparse 小规模资格通过

**结论：有界三维 p2 架构资格通过。** source `7c4410dbc55bce804d148493760d4de68acd8405` 在新的 boundary-plane 存储算子上完成独立 dense authority、sparse 四个 q 因子、完整内部载荷恢复及真实三维缺口测试。dense checker 129项、sparse checker 164项均通过。此结果补上V7尚未运行的centered PDE阶段；旧V5/V6裁剪算子和V7组件结果继续保留各自历史口径。

这次先把端口模式的相位参考点移到实际边界，避免衰减模式极小的指数系数在装配截断中消失。随后直接求解完整原有限元系统，建立新算子的对照解；再用精确单元内部消元和全部y方向块因子求解、恢复每个原始三维未知量，并逐项与对照解核验。

对象仍是80 cells、p2、λ0.7nm、phi5、manual m±9/n±3的532模式小规模弱对比夹具。2048个独立原FE自由度中含全部480个interiors，四个q均保留；全部532个实际端口C/D非空。它验证实现与离散系统的一致性，不授予连续精度、目标截断、官方R/T/A、p4/p6或原尺寸2TB/48h资格。

## 原方程与完整恢复

| 已检查对象 | measured | 口径 |
|---|---:|---|
| dense/sparse全部原FE列 | 2048列；相对差0 | 每panel最多32列；sparse侧未新建全局dense矩阵 |
| regular四载荷原方程残差最大 | 3.1766e−13 | generic、interior_only、physical、notch_supported |
| 四个q因子残差最大 | 6.2886e−14 | 重复解差0；线性差最大2.4133e−14 |
| 缺口迭代数 | 4 /4 /3 /4 | 与上述四载荷顺序一致 |
| 缺口原方程残差最大 | 7.4874051e−12 | physical载荷 |
| 缺口相对新dense direct差最大 | 5.8732785e−11 | 新centered基准；不是旧裁剪场 |
| physical缺口非零q分量比例 | 6.2100442e−5 | 真实非零ky wrap及三维缺口耦合 |
| 每个checker的逐模式输出比较 | 40组均通过 | 每组532模式；最差局部运算误差1.5851e−12 |

四类载荷覆盖全部内部自由度和所有q，不把trace-only或physical近零内部载荷替代generic内部测试。完整原FE/DtN作用的两向量协变探针最大4.3671e−16，完整RHS约化协变最大1.3233e−16，modal off-block为4.1227e−16。前两项是采样作用，不是全矩阵范数证书。缺口右预条件器的四个采样缺陷为3.47e−5至9.04e−4，同样不称算子范数上界。

## 每次运行独立绑定实际装配

新流程在每个实际carrier上独立运行同Gauss/fullMPC live oracle，绑定实际loaded modules、Constant角色与哨兵，并恢复被哨兵修改的值。资格后、因子前及退出时的数值carrier身份保持一致；完整hash见[compact证据](outcomes/records/centered_p2_v8/centered_p2_v8_compact.json)。dense和sparse本次raw context碰巧均为27fe6c16…de7e，但资格来自各自实际运行的证据，不能假设不同进程或未来上下文会相同。

最初两次严格raw-C/context身份门停止仍为FAILED，未进入因子阶段。Constant创建顺序是上下文漂移的候选解释；旧运行未保存相应计数，不能写成已证实根因。修复以当前实际装配的独立资格替代历史上下文可复用的假设，没有放宽系数、Gauss、模式、MPC或原方程数值门。

旧clipped到新centered原FE矩阵的相对Frobenius变化为0.0061060864（分母为centered），physical RHS变化4.1606e−16。前者是全部2048列的诊断，明确显示存储算子改变，不是坐标等价误差，也不能与V7五状态action变化0.0308226混称同一个量。

## 失败保留与资源

| 运行/source | 实际状态 | 采样同时RSS / 监督wall |
|---|---|---|
| dense attempt1 /924c7bdd | FAILED：严格上下文身份门 | 392130560B /4.8126s |
| dense attempt2 /8a3b353c | FAILED：严格上下文身份门 | 340881408B /3.5288s |
| dense attempt3 /7c4410db | PASS；129项checker通过 | 633204736B /19.1875s |
| dense checker /同source | PASS | 460742656B /3.5745s |
| sparse attempt1 /同source | PASS；164项checker通过 | 464019456B /15.1345s |
| sparse checker /同source | PASS | 327389184B /3.2861s |

全部监督记录swap0且后代清场。RSS为父进程与全部后代同时采样；不同run不相加，采样不是cgroup硬峰保证，也不是目标容量或速度外推。原始矩阵、数组和完整日志保留在ignored artifacts；compact只发布结果、资源、命令、来源与hash。历史V5/V6失败及V7三次组件失败也不被本次PASS覆盖。

独立复核的[事后记录](outcomes/records/centered_p2_v8/independent_verification.json)及[复核说明](outcomes/records/centered_p2_v8/independent_findings_zh.md)记录了此前完成的只读核验：1247个冻结源码文件、712项artifact hash条目（dense424项、sparse288项）。712项并不全是数组；本次整理记录未重新扫描或运行数值计算。

## 工作站移交范围

复用现有精确静态凝聚、恢复、y方向离散对称及mode映射；本次新增的是新centered原算子的live资格和dense→sparse闭环。仍需高阶、强对比、目标尺寸/截断/连续误差、跨机器ABI、MPI、恢复重启与资源资格。当前不宣布可启动目标大运行。云端继续补足与MyFEniCSx_task37_extra同一次工作站启动的缺口，自动读取主线远程新提交；不依赖用户转发、不推断未发布本机状态。大型运行仍由用户执行。
