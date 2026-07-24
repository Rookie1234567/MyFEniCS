# Task035b 负结果与受控停止

所有 negative、formal failure 和 preflight stop 均保留；没有删除或改写为
通过。

| lane / record | 分类 | 主要原因 | 后续决定 |
|---|---|---|---|
| p4-trace p4/p6-interior h10 | `controlled_negative` | 88,994 DoF 成本通过；R00/R/T/A/orders/field 全失败 | p4 fixed-trace closed |
| p5-trace p4-low/p6-high N62 h10 | `controlled_negative_non_exact_sequence_space` | low space curl nullity 112 vs expected gradients 178 | preflight 禁止重复 |
| N62 postprocess failure | `formal_not_pass` | 历史正式失败 | 原样保留 |
| N62 wrong-control preflight | `formal_not_pass` | authority identity 错误 | 原样保留 |
| independent-condensation attempt | `formal_not_pass` | worker/result 缺失 | 原样保留 |
| global p6/h15 | `controlled_negative_full_same_error_gate` | scalar/field 通过；significant power 6/12、amplitude 8/12 | 不进 Hybrid |
| fixed p5-trace/p6-interior h15 | `controlled_negative` | preferred 74,890 DoF；significant power 6/12、amplitude 7/12 | 不进 Hybrid |
| Task035 tetra final p6 | `controlled_negative` | vector control 通过，strict-R control 失败；167,784 DoF | 只作顺序竞争 |
| structured-hexa local-h | `stopped_by_gate` | hanging-node/transition conformity 未实现 | 不发明局部网格 |
| tetra selected local-p6 | `stopped_by_gate` | reduced selected-p6 implementation 为 hexa-only | 不重复 heavy p6 |
| h37.5 fixed-mesh p6 | `stopped_by_gate` | refined p5 已超预算，缺少 selected-p6 | 不运行 |
| best-candidate Hybrid/M funnel | `stopped_by_gate` | 无同误差候选 | 不运行 |
| 0.7 nm PDE | `not_run` | 无 selected layout/accuracy authority | 不运行 |

## 两个连续成本/精度负信号的解释

fixed trace 的成本信号是真的：active rows、matrix/factor NNZ、peak memory 和
time 均下降。精度负结果也是真的，但 N62 后来被 exact-sequence audit
重分类，不能把它当作第二个独立、合格的 local-p accuracy negative。关闭
当前 lane 的依据是：

1. p4-trace exact-sequence 候选完整精度 Gate 失败；
2. p5-trace/p4-interior 本身结构不合格；
3. h15 global 与 fixed p5-trace/p6-interior 均在 significant channel Gate
   失败；
4. classifier v3 没有 target local-h 正信号，且 same-patch/local-h 架构缺失。

## 非负结果

以下项目不能因任务整体没有成功候选而写成失败：

- exact assembly-time static condensation；
- Floquet slave elimination；
- solver-object release、heap trim、MPI tensor dedup 与 exact preallocation；
- same-mesh DWR R00/R/T；
- 252-cell physical smoothness signal；
- fail-closed classifier fixtures。

它们是可复用工程/研究正结果，但不单独构成 same-error hp 压缩或 0.7 nm
可行性证明。

