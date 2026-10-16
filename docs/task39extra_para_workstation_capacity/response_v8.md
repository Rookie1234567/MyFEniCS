# Response V8：P0/P1 阶段归档与未关闭的 A4 返回门

**状态：`P0_P1_STAGE_ARCHIVED; V8_OPEN; A4_RETURN_GATE_OPEN`。** 本次按用户要求停止后续根因研究与计算，只归档已完成的失败包审计和 action-only 诊断。P1 诊断正常结束不等于求解器通过；没有据此修复或关闭 BAL_H/A4 门。

## P0：原始失败输入得到保留并核验

失败源运行是 `20261013T225710.255482Z`，失败分类 `P4_NUMERICAL_UNQUALIFIED`，source `d62c20fd2e6f77006edc80f6449447b39efcfdfe`。输入 SHA-256 为 `488d50b4028b5a2fb84ee000af807cdb2d1a5255a17a0482113338f3bb8d2865`，physical SHA-256 为 `d394308fe4dfcc8e0c25cdaa707fb8ff4bf4a394c268a8702b4afa069b78681a`，resolved SHA-256 为 `cb80a526ebdcd77b7a5d36986538199c7abf0e3cc7c63a962ff50efd8324f7e7`。

失败包 `p4_failure_0017.npz` 的实测 SHA-256 是 `79f7865f8d425a9ffa416d1d55fcd8b1a1dcdb427cdcb2531979061c8c86155a`，与失败索引一致。包内 `g` 是 p4 RHS；`g/c/r` 各为 `9,757,120` 个 `complex128`，有限且形状、类型与描述相符；端口状态和闭合数组各为 `572` 个 `complex128`。g/c/r 原始成员 SHA-256 分别为 `f519b094eabc39998a7bb2c4b522dc4dd9c9db1852e76a40527b1875132ed533`、`b0efc4deac3c22ef418713018d2657038476fa430e680e50edd762632d6b9c27` 和 `f9c6d52e47520270247feda4c9e5365aa3a122d540065e01458ff9b0c385b4bc`。

独立分块审计得到 `||g||₂=0.7348417462869885`、`||c||₂=1085.6279867370547`、`||r||₂=8.232710732993795e-11`。包中记录的 RHS 范数为 `0.7348417462869713`；差 `1.72e-14`。P1 按保存 g 的 action 路径使用 `0.7348417462869812` 作原分母。载入后的数组互不共享内存，只能说明审计时的独立载入状态，不能倒推运行时缓冲区是否曾被别名覆盖。

P0 记录在 [payload audit](outcomes/balh_review_20261016/p0_failure_0017_payload_audit_20261016_v1.json)。未重新读取失败 NPZ 或旧资源流。

## P1：同一保存输入上的 action-only 诊断

诊断对象为原失败 A 网格身份：`46,800` cells、轴计数 `100×2×234`、`9,757,120` 个 p4 行、572 个 active 模态、surface quadrature degree `160`。P1 只对保存的 c/g 作算子作用、端口代数与恢复核对；它没有创建全局 A4、factor、KSP、PC，也未执行 MatSolve 或完整 BAL_H。该次运行分类为 `P4_ACTION_ONLY_NOT_SOLVER_QUALIFICATION`，source scope 是 development worktree，不能冒充正式 PDE provenance。

| 检查 | 已测结果 | 原合同解释 |
|---|---:|---|
| fast fused A4 保存输入残差 | 范数 `8.232710732994972e-11`；相对原 g 为 `1.1203379196396136e-10` | 原门 `1e-10` 未过；按 P1 分母对应绝对限值约 `7.348417462869812e-11`。超限约 `8.84e-12`，门槛与分母均未改 |
| fast 重复作用、与保存 r 比较 | 两次作用差 `0`；重算残差与保存 r 差 `0` | 对该输入未见重复调用漂移；这不单独证明算子正确 |
| native A4 作用对照 | 残差 `4.416695785068115e-09`，相对原 g `6.0104040188038554e-09` | 比 fast 残差更大，因此 native 路径也不是裁判 |
| fast-native full A4 差 | `4.416607833216028e-09`，相对原 g `6.010284330649867e-09` | 两路径有可测差异；差异尚未归因到正确性缺陷 |
| curl / material-mass 分量 | 两分量范数均约 `7.9234e4`；fast-native 分别约 `2.3789e-09`、`2.5659e-09`，相对分量约 `3.0e-14`、`3.24e-14`，相对原 g 约 `3.24e-09`、`3.49e-09` | 大分量相消；不能用分量相对误差小来忽略 A4 返回门 |
| fast curl+mass 分项和 vs 生产 fused volume | 向量差 `2.7335657754249012e-11` | 另一次对已保存向量的有界顺序对照得到分项和路线残差 `8.504540334507726e-11`、相对值 `1.1573295035944254e-10`，比 fused 路线更差；此结果不能证明根因 |
| port closure | `4.61763554081302e-14`；relative `2.996833748130505e-14` | 通过独立端口闭合门，但不替代 A4 门 |
| `B H⁻¹ e` | 范数 `3.454393504554807e-15` | 增广恒等式一致性量，不等价于 A4 返回通过 |
| 恢复的内部系数 vs 保存 c | 差范数 `3.1340296421298603e-11`，relative `3.749272228593682e-14`；最大系数差 `1.8825124173281097e-13`，row `5,467,737` / cell `26,188` / orientation `32769` | 这是系数差，不是 `A_ii` 加权局部残差 |

最坏 fast residual 行是内部 row `7,801,079` / cell `37,388` / orientation `32769`，幅值 `5.480533829858543e-13`；fast-native 最大差行是内部 row `9,509,334` / cell `45,608` / orientation `32769`，幅值 `3.4024582116798896e-11`。这些位置彼此不同，现有保存结果没有原始逐单元矩阵或完整 cell-to-global DOF 映射，不能据此把差异绑定到局部积分、几何分组、MPC/映射或累加中的某一项。

因此已确认的是：失败可在保存输入上重现；fast/native 有数值差，分项和与 fused 的顺序差也可测，而更换为 native 或简单改变分项相加顺序都没有关闭 A4 门。**实际根因及生产修复均未证明。** 此前 P64 方向修复和联合端口修正的历史证据保留，但不能让本次第 17 次 A4 失败变成通过，也不能用端口门替代 A4。

P1 compact 为 [action-only terminal compact](outcomes/balh_review_20261016/p1_action_only_terminal_compact_20261016_v2.json)，SHA-256 `659dc72c12021a11f13b10b5fa0b5a855a43e027900d4e13abd05976cac84ad9`；其中绑定 worker report SHA-256 `e0575602c770b0e909dc72d84767c419518f6f7960eb252aa059106e6cc759e7`、12-array 文件 SHA-256 `9e05f64e98ab74f584021c6191d6dc82e816d4fc52ec0f27138786cfdb6d6c7b`、5-array 文件 SHA-256 `b93c0eab02c46e96c147d3db36501796af523813af2701080f4bd3bdff1f1c5a`。原始数组与运行日志继续留在 ignored results，不提交 Git。

本轮已有的一遍资源归并记录 2,720 条、tree RSS 峰 `14,339,940,352 B`、tree swap 峰 `0 B`、全机 swap 增量页数为 0；PSS/USS 按合同关闭。样本可读性汇总和资源文件 SHA 未取得，未做第二遍扫描。P0 审计进程自身 peak RSS 约 `522 MB`，这不是求解树峰值。

## 未运行项与接续边界

| 项目 | 状态 | 边界 |
|---|---|---|
| 原 g4 初解及最多两次同因子联合精化 | `NOT_RUN` | P1 是作用诊断，没有 inverse 重放或新 factor |
| 完整 BAL_H / 原 A 迭代 / 第 17 次之后的延续 | `NOT_RUN` | 当前 A4 门仍开；不得从 c2 追加精化 |
| E 桥接、P2/P3、任何其他 FE/factor/PDE | `NOT_RUN` | 按本轮用户指示不再启动 |
| 求解器资格、完整物理结果资格 | `NOT_QUALIFIED` | action-only 结果不构成场解或 solver pass |

本文件只记录这一阶段，不把 V8 总任务标记为完成；之后如何处理须由新的用户指示决定。
