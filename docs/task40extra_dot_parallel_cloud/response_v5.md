# Response V5：sparse-p2 因子资格失败与端口表示诊断

状态：失败诊断检查点，保留负结果，后续运行另行准入。source `f2bd95ba813b3243bdfd052e90c53ccb0cf0e006`，运行开始工作树clean。本次严格保留 `FAILED` / watchdog `WORKER_FAILED`；尚无恢复后的稀疏参考逆通过，也未运行p4。

本候选把先前的小型稠密参考求逆改成“精确消去单元内部未知量，再按y平移分块的稀疏求逆”，以减少存储。与旧原算子相同是必要条件；实际分块求解能否处理任意载荷还要另测。本次前者通过，后者在第一个q0块失败。

## 通过与失败不得混同

仅针对云端80-cell、scaled p2、phi5、manual532模式；不涉及或推断笔记本尚未发布的本机运行。

| 阶段/身份 | 保存结果 | 结论与门限 |
|---|---|---|
| measured：原A0全部2048列对照 | 相对差0，panel最大32列 | 与旧保存离散算子完全匹配，门1e-11；没有新建全局稠密矩阵 |
| measured：凝聚增广对称性 | covariance9.9526129040e-17；off-block4.1158284865e-16 | 全4个右q、全部左q检查通过；不等于因子可用 |
| measured：首个q0块 | 468×468、26,264NNZ；CSR527,156B | SciPy公开SuperLU分解返回，但求解质量失败 |
| failed：单位量级混合FE/辅助载荷 | true residual最大1.434203246972e12；重复差0；linearity为NaN | 输入为确定性cos/sin复向量，覆盖全部468行；不是单个辅助基向量。norm出现overflow/invalid警告；NaN不能算通过；未保存xa/xb/xsum，不能据此断言解条目非有限 |
| not_run | q1–q3因子、完整恢复逆、外层notch、sparse-p2 bridge receipt、p4 | q0门触发即退出，不用后续只读诊断改判 |

保存的完整凝聚矩阵2100×2100、244,932NNZ；原全FE独立2048、trace1568、interior480；其他待因子块为544×544。原记录保留全部数组/hash、traceback、非有限linearity文字与负结果。

## 定位到端口表示，而非简单删模式

只读保存数组显示：full H最小1.0720025474e-194、最大3.3607681756；q0最小8.5862021405e-173。532个模式身份仍在，但C有172个全零列、D有174个全零行；q0有16个共同全零模式。巨大的坐标尺度与实际零支撑，是明确证据；“仅模式编号完整”不足以证明全部非零端口泛函被保留。

冻结源码 `dtn_port_3d.py:840–903` 的 `_vec_nonzero_owned_entries` / `_combine_owned_entries` 使用 `max(1e-30, 1e-13*global_max)` 的绝对/相对截断，发生在模式归一化前；:1119–1169的phase含绝对z，:1526–1530的H含边界相位模平方。端口耦合/投影各随相位及其共轭缩放，而H随模平方缩放，消去辅助变量后这些尺度本可抵消；因此微小原始向量被裁掉可能删除有限贡献。需要同Gauss/fullMPC的before-mask向量对照区分物理零与裁剪零。小H与上游截断支持“表示尺度是主要原因”的诊断推断，但尚未通过重新装配/对照证明每个零泛函均由截断产生，不能把物理对称零项一概归为错误。

对已经保存的同离散矩阵进行精确行列缩放，只能改善该矩阵坐标条件，不能恢复上游已经裁掉的C/D项。若复用旧Task35b在装配前采用端口平面参考gauge，必须重新证明新端口作用、原方程、输出幅值/功率和MPC等价；不能称为对本次同一已裁剪矩阵的无影响修复。不得为通过而删除零支撑模式、放宽残差门或把H简单改成1。

## 保存物理解的有限见证

外部 `read_saved_p2_witness.py` 只读已保存矩阵/场，核验hash后做乘法、范数与对角辅助坐标恢复，没有新PDE装配、分解、线性求解或SVD。36份本次数组、20份见证所用数组及脚本SHA256已再次核验。

| derived from saved arrays | 数值 | 可以证明与不能证明 |
|---|---|---|
| 旧物理解原A相对残差 | 4.4818275342e-14 | 该旧保存场在旧离散算子上仍成立 |
| 凝聚FE/端口见证 | 6.2334047877e-14 /4.3563232738e-17 | 支持该载荷的符号、凝聚和映射 |
| q0 FE/端口见证 | 4.0231282255e-14 /2.8349292703e-16 | 仅保存场代入，不是逆应用 |
| 原内部RHS范数/最大项 | 2.6782198767e-15 /6.8913319334e-16 | 接近零，不能授予任意非零内部RHS资格 |
| 辅助坐标范数 | 2.1438967047e24，有限 | 大坐标仍在；不抵消raw block随机样式载荷失败 |

旧phi0/phi5的小p2原A/direct/非零Bloch数值记录保持，但“保留全部532模式”须理解为编号、别名及当时已截断的离散operator identity。它不证明532个未裁剪物理泛函完整或截断/连续精度。不能追溯把旧记录宣称为此新稀疏增广逆的任意RHS资格。

## 资源、证据与下一门

| measured资源 | 数值/口径 |
|---|---|
| watchdog总时长 | 7.320493135s；worker约5.085s，二者不同口径 |
| sampled同时进程树RSS | 433,651,712B；30采样；独立父进程及全部后代 |
| swap/退出 | 0；exit2；descendants cleared；非资源Gate停止 |
| 准入合同 | 1.5GiB/600s、MPI1/math threads1；512MiB声明factor/workspace allowance、128MiB证据reserve，非数学内存上界 |
| ABI | 云端DOLFINx/Basix0.10、PETSc/petsc4py3.25.6 complex128/int32、SciPy1.18.1；不代表用户工作站ABI |

配套 [失败检查点](outcomes/records/sparse_p2_failure_checkpoint_v1.json) 保存精确source/tree、input、命令、原始记录/36数组SHA256、pre-factor事件、有限见证与未运行项；[保存场见证](outcomes/records/saved_physical_witness_v1.json)及[只读检查脚本](../../benchmarks/check_y_orbit_saved_physical_witness.py)保留可审计诊断身份。原始目录为 `benchmarks/artifacts/task40extra_dot_parallel_cloud/y_orbit_sparse_p2_phi5_attempt1`，raw不入Git。

下一步先确定同离散缩放诊断与装配前gauge所改变的对象，再冻结准确source/command/resource和独立验算。任何恢复资格都必须含真实非零内部RHS、全部辅助通道及明确坐标尺度的测试载荷、原A与端口检查；当前不自动准入p4或目标大算例。本次文档归档未发起新的数值运行。
