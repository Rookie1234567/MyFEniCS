# Fresh C1a 已闭合，下一项为同一缩放网格的 p4 全链

2026-10-04，own branch `task40extra_dot_parallel_cloud`。C1a worker 完成，独立检查器 955 项全部通过；完整原始数据和最终检查器包均已从 Library 新目录取回并逐项核验。生产者 `a580c72a` 与检查器 `16415427` 分别保留身份。p6 为组件作用/RHS/恢复资格，没有全局 p6 求解、quotient 或原尺寸资格。

- 完整 worker 包：Library `libfile_ac66834781108191a106e5517ae07c09` 是恢复索引；12 个部分重组为 392,240,642 B ZIP，1,627 文件、1,616 NPY 全部校验
- 最终检查器包：Library `libfile_8479ec542a008191b8b42264d072fd28`，776,001 B，19 个成员全部校验；检查器报告 SHA256 `cbde5fbfd5c31474a78afb9c5dabe20d8e1e10e84f1f1c5499faaeb88c3cf5a1`
- 原方程制造解 native 残差 2.4904492e-15，恢复状态差 1.4967087e-12；物理 DiXiB 范数 7.6890873e-27，只有数值非零意义，实质敏感性来自独立合成负控

## 最小下一步

C1b 复用以上已检查、已持久化的 p6 组件 admission，重新运行现有 p4-chain。保存的 p6 张量不能替代 p4 的基函数和 Gauss23/144 点证据，因此无需重做 p6 FE，仍必须新建 p4 实际载体及 same-live 532 字面 oracle。

网格是旧 7/135 缩放的同一 80 单元、phi5/manual532 和原两单元 notch。p4 存储 17,204、独立 15,872、全部内点 8,640、trace 7,232，四个 q 和全部 alias 保留。稠密 H/Hhat 只用于小端口表示；全局 FE/缩聚和每 q 矩阵使用原有稀疏路径。检查原始 A0 regular 四载荷，以及原始 A1 notch 的 FGMRES、完整内点恢复、原方程残差和 532 模式输出。这里“原始”指缩聚之前的三维算子，不指原始大模型尺寸。

当前最小改动只修三种源码角色：不可变 producer/report/provenance/worker watchdog；独立 checker/checker watchdog；新 consumer。两个 metadata 函数之外的 AST 必须保持不变，其他数值/配置/输入 hash 全部一致。历史报告/检查器和 Library 读回收据固定 exact SHA；不能把旧生产者改写为新 HEAD。相对解释器 argv 使用已审阅的外部监督方式，保持真实环境字符串一致。

## 预算与决策

每个 worker/checker 3 GiB、4,500 s、zero swap、MPI1、单线程；四个因子总额外声明 allowance 512 MiB，加 128 MiB 证据余量，始终以实际当前 RSS 加未分配对象计算。int32 维度/NNZ/offset 门槛先于分配。未知冷 JIT 和 LU fill 仍未知。C1b 原始数组预算保持 512 MiB，不继承 C1a 的 768 MiB。Library 原始包不裁剪，实际压缩量必须满足已授权 512 MiB、16×32 MiB、90 分钟传输及读回上限。

旧同 profile p4 worker 为 117.4464 s、913,350,656 B，checker 为 4.7910 s、524,525,568 B，仅供新执行的粗估，不能继承资格。预期新 worker 2–10 分钟只是估计。最坏 worker75分钟＋checker75分钟＋存储90分钟不可能保证在16:05检查点前全部完成；检查点如实报告完成阶段。

本次恢复以来的可加已记录成本为 source 1.060 s、worker 1349.135 s、失败 numeric checker 2.773 s、成功 checker 18.142 s、完整归档 21.698 s、Library完整读回 116.350 s；加已有测试/诊断后为1512.827 s。另有原始调用记录的 CLI失败0.391 s、环境失败0.750 s、归档导入失败0.184 s，全部保留。12:05至14:32共2小时27分钟，含并行运行环境恢复、工程诊断、审阅和没有完整 elapsed 的小包传输，不能用上述25分钟代替总耗时。旧失败成本另保留，不能追认通过。

C1b 通过会得到本次环境下实际 p4 全局 regular/notch 求解资格；紧凑 p4 quotient 的 C1c、公共 PETSc/AUTO 成本的 C2 仍需各自验证。原尺寸 50×25×140 nm、0.7 nm、2e12 B/172800 s 的最终全求解和场/功率精度尚未验证。
