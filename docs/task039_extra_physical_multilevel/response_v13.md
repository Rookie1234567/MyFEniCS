# Task39extra response_v13：完整 PC 有界实测与排除结论

## 本次补充结论

**根据完整 64 步实测及历史同模型对照，排除本轮冻结的 `physical_macro_dd4_v12 + BAL_H` 配置，不继续投入本轮计算。** 用户先授权“不要求收敛，跑几十步比较”，随后明确“太差就可以停止”。这一结论依据修正效果与成本，不以“没有达到最终收敛”作为唯一理由，也不外推其他块配置或更长迭代的结果。

PC 是每次外层迭代用来估计误差、给出修正的计算步骤。本配置用 42 个完整物理 p4 局部块和已有全局粗修正构成 `B4`；每次内部 `I4` 从零开始最多调用 4 次新 `B4`，再通过选定的 `BAL_H` 组合修正原始 p6 方程。局部回代准确、接线恒等式成立，仍可能给不出足够有效的全局修正，本次实测正是这种情况。

| 评审问题 | 本次证据与判断 |
|---|---|
| 内部质量 | 42 块构建及库存合格，6 条 p4 误差/残差控制完成；完整 R32 的 128 次 I4 均合法遵守四步限制，但 **0/128 达到内部 `1e-4`**。 |
| 框架耦合 | 3 组同一输入的 BAL_H/ONE_C 比较有效，按原规则选择 BAL_H；ONE_C 更省单次组成操作时间，但没有满足场误差和残差改善条件。外层最后一次保存的耦合闭合相对误差为 `1.4796776236757317e-13 < 1e-8`。 |
| 完整 PC 效果 | R32 完成 64 个实际外层步，原始 A6 全显式相对残差仅降到 **0.7666389832389989**；相对离散参考场的 L2 误差为 **0.9488237463600627**。第 32→64 步残差下降，场误差反而增大。 |
| restart | R32 为两个有限 32 步周期。R64 按用户要求停止，保存的 8/16/24 步解与 R32 逐字节相同；没有完成所需的第 32 步一致性及 R64 终态对照，**不作 restart 选择结论**。取消逐段 MR 不等于取消 restart。 |
| 总成本 | 四次补充运行共计 **4361.388890249411 s** 保守经过时间，包含首次 R32 工程失败和主动停止的 R64；全过程最高采样进程树 RSS 为 **3350794240 B**。工程编写、审阅及整理的完整耗时未完整测量。 |

## 原始方程与历史对照

所有下表残差均来自同一原始物理模型与模式身份。时间取保存节点的保守外层求解时间，不含 setup；历史方案的诊断频度、PC 工作量不同，不能把相同步数解释为相同计算量。V5 是已有全局 p4 因子的历史诊断对照，本轮没有重建该参考，也没有把它新增为第三框架。

| 配置 | 第 32 步残差 / 外层秒数 | 第 64 步残差 / 外层秒数 |
|---|---:|---:|
| **本轮完整 PC，BAL_H，restart32** | **0.802589 / 803.399** | **0.766639 / 1540.207** |
| 历史 V5 exact-p4 BAL_H | 0.073123 / 346.127 | 0.019157 / 692.572 |
| 历史 V7 entity I16 | 0.122313 / 1414.353 | 0.061294 / 2854.520 |
| 历史 V7 projected-seq2 | 0.173168 / 1959.473 | 0.107669 / 3930.345 |

新 PC 的每步残差改善明显弱于这些历史对照；相对 V5，它在较长外层时间后仍留下大得多的残差；相对 V7，它虽然用时较少，但修正质量显著更差。完整建造成本、其他历史节点及计时边界见[中心结果](outcomes/physical_macro_v12.md)。

![同模型的实际残差节点与外层耗时对照](outcomes/charts/v12_supplement_comparison.png)

图左横轴为外层步数，右横轴为保守外层秒数，纵轴均为原始 A6 的全显式相对残差；点间连线仅帮助阅读，不代表额外采样。图不包含 setup、工程失败及主动停算费用；这些费用单独计入下表。

| R32 节点 | 全显式残差 | 相对参考场 L2 误差 | 相对 scaled-curl 误差 |
|---:|---:|---:|---:|
| 32 | 0.8025891203479081 | 0.9384007607744688 | 0.9382432819659642 |
| 64 | 0.7666389832389989 | 0.9488237463600627 | 0.9486448577201997 |

因此原 A6 最终 `1e-6` 残差 Gate 和 `1e-4` 场误差 Gate 均为 **`measured_not_met`**，不是 `not_run`。官方场/功率恢复、R/T/A、`A_volume`、80 模态输出及守恒等后续物理 Gate 未运行，也没有追加 O3 原始收敛验证或 notch 验证；这些要求保持原限值，未把有界试验当作正式物理解。

## 费用、内存与未完成证据

| 补充运行 | 源码身份 | 真实终态 | 保守计费秒数 | 进程树 RSS 峰值 / B |
|---|---|---|---:|---:|
| O1，42 块及全部控制 | `7d9df5e19d324776588aaa9efc4996cc3fe36d8e` | `COMPLETED` | 601.0369560300772 | 3250446336 |
| 首次 R32 | 同上 | `WORKER_FAILED`，场诊断 metadata 的 TypeError | 1028.6465685711235 | 2534461440 |
| 修复后 R32 | `d39261bb17e8d9042c03d4d4990258da5043b621` | workflow `COMPLETED`；64 步数值未达标 | 1846.2808846201353 | 3350794240 |
| R64 | 同上 | `USER_CONTROLLED_STOP`；最后保存到 24 步 | 885.4244810280746 | 2552774656 |
| **合计** | 四个不同运行，失败账没有清零 | 预算上限 10800 s；剩余 6438.611109750589 s | **4361.388890249411** | **取峰值，不相加** |

修复仅补上场评价在辅助对象释放前读取积分元数据的正确路径；失败运行已保存的前 24 步与修复后逐字节一致。严格 R32→R64 前置检查保留。首次工程失败和 R64 的最终 candidate/I4 计数未落盘，按 `not_available` 保留，不能从步数伪造实测计数。R64 的停算原因来自用户收窄范围，不是 R64 数值失败；watchdog 已清除全部子进程，未使用 SIGKILL。

局部账的 allocated/used padded 分别为 `1671000000/888000000 B`，保守 retained inventory 为 `2180383916 B < 2684354560 B`；旧 profile 的 2 GiB cap、V11 配额公式、ABI 和整机安全线均未改动。局部库存与进程树 RSS 是不同口径，不能相互代替。四次运行的 RSS 采样均可读，均无 job swap 或新增全局 swap；R32 退出阶段有 1 个 PSS 缺样，其可读 PSS 最大值为 `3316318208 B`，不声称 PSS 全程完整。历史 V5 notch 参考的 448 页全局 `pswpout` 归因仍为 `UNRESOLVED`。

R32 实测 build/rhs/candidate 分别为 `295.230015322/5.230602902/1542.916955076985 s` 保守时间；完整外层单调计时为 `1413.8653707560006 s`。三类已计时外层 PC 组成操作 A/C/H6 分别为 `180.7259436650238/915.0338269800122/151.25650010298705 s` 单调时间，五次场诊断合计 `49.257860040001106 s` 单调时间。I4、B4、C_U、M_D 是嵌套成本，不再加到父时间中；I4 的 `seconds` 使用保守时钟，也不能与这些单调计时直接相减。完整工程时间为 `unknown`，ledger 中的 383/407 s 仅为局部观测区间。

## 证据与交付身份

review base 为 `96e5d5fcfc3e801ef33d4a2d241ea7571937f734`，本次 supplement base 为 `395d02c6c16d7abf155b570d00072967fce4423f`；运行源码按上表保留，最终文档提交不替换运行身份。固定模型为 13.5 nm、Full3D、p6/h10、252 cells、80 模式、MPI1×线程1；physical/mode SHA 和环境绑定见[完整记录索引](outcomes/records/v12_supplement/README.md)。现有参考只读取和校验，没有重建全局参考，没有参数扫描，没有影响 5 nm 工作。

修复源码的 51 项定向测试和 2 条 metadata/独立范数算术 smoke 通过。独立审计包括每次构建的 759 项库存检查、6 条 p4 的 132 项检查、shared-q 的 96 项检查，以及 R32 的 1187 项记录/计数/解哈希检查。审计范围是保存记录重算和已资格化算子路径核对，没有重新运行 PDE 或独立重放 A6；完整测试边界、旧文档缺件和最终文档检查见[test summary](outcomes/test_summary.md)，不声称 full pytest 或 CI 通过。

统一入口：[中心结果](outcomes/physical_macro_v12.md)、[compact](outcomes/records/physical_macro_v12_compact.json)、[run index](outcomes/records/run_index.json)、[补充证据包](outcomes/records/v12_supplement/README.md)、[最终费用审计](outcomes/records/v12_supplement/audits/task39extra-v12-supplement-final-budget-audit.json)。全部提交到同一 `task39extra` 分支待审阅；当前配置仅保留研究负结果，普通默认不变，不包含 master merge approval。

以下保留首次 V12 预算停止的原有历史记录。

---

# 历史：Task39extra Review V12 response：O0–O4 真实物理验证收口

## 结论

本轮已经在 review base `96e5d5fcfc3e801ef33d4a2d241ea7571937f734` 之后的 source `e8c3c82bab2687a811a11f0798a2879c725532b5` 上完成 V12 O0 预检、42 个真实物理宏块的 O1 构建/库存审计、4 组有限 p4 控制、O4 finalize 和最终轻量回归。O1 的 4 组 p4 控制均只执行了合同允许的 4 次 I4 `B4` 作用，均以 `INNER_APPROXIMATE_RETURN` 返回，未达到内部 `1e-4` 目标；共享 O0/O1 保守账本随后受控停止。

准确状态是：

`PARTIAL_PHYSICAL_CONTROLS_WITH_PERFORMANCE_CONTROLLED_STOP`

不是 OOM、MUMPS numeric failure 或 Maxwell convergence failure，也不是完整物理 solver pass。O2 restart、O3 original/notch 和全部新的 official R/T/A 等字段均 `not_run`。普通默认保持不变，`master merge` 未获批准。

完整中心结果见 [physical macro V12](outcomes/physical_macro_v12.md)；机器记录见 [compact](outcomes/records/physical_macro_v12_compact.json) 和 [lossless raw JSON evidence](outcomes/records/v12_raw_json_evidence.json)。原始 raw evidence SHA256 为 `0ff0246b6c1212b5d1c2706cd1954884626b828192697d1a7d0c9e99d06e6710`，tracked normalized copy SHA256 为 `329ed513c351896c3db09ea5899389a060b71ff36805daf456132e304fdd1580`。

## 阶段结果

| 阶段 | 结果 | 关键边界 |
|---|---|---|
| O0 | `O0_PRECHECK_COMPLETED` | 2.0600177589932294 s；RSS peak 147095552 B；swap 0；清场完成 |
| O1 | `PERFORMANCE_CONTROLLED_STOP` | 42/42 numeric inventory、84 witnesses recounted；资源审计无 cap violation、swap 0；p4 records 只记已持久化下界 |
| O2 | `not_run` | O1 未完成，未形成 ONE/BAL framework selection |
| O3 | `not_run` | O2 未运行；没有 original 或条件 notch |
| O4 | `O4_FINALIZED` | 2.0538921670007735 s；未新建 reference factor/solve；清场完成 |

O1 的终止是 shared O0/O1 budget exhaustion：`7201.319691806935 s` 对 `7200 s`，保守账面超出 `1.319691806935 s`。这个差异保留在 ledger 中；实现活动、阶段费用、未单独计时的间隔和 O4 费用没有混称为一个 gapless CPU 时间。

## 真实宏块和 p4 结果

42 个物理 block records 覆盖 p4 全部 `48960` 个独立行；42 个宏块各有独立 numeric factor record。另有 18 个 C_U 元素内部响应的 `local_classes/local_factors`，它们是不同层的类因子，不能替代 42 块物理构建。最大局部回代相对残差 `2.1772149386553977e-15`，6 个 native witness 最大 `8.243915633632588e-16`，cached/native relative bridge `2.787784119354311e-15 < 1e-11`。C_U 已构建并通过 inventory 记录，但 closure scalar 没有持久化，故不写 closure PASS。

S/p2 同时存在但与 local inventory 分开计账：rows=`7326`、NNZ=`818100`、allocated/used padded=`270000000/65000000 B`、derived matrix+reported-factor=`341069688 B < 536870912 B`，symbolic/numeric=`0.025815314998908434/0.371230351000122 s`。这是 derived policy budget，不是 RSS；原始 `stages.jsonl:247` SHA256 为 `4b1fd995693c14177c028304916b964a21cde7a23f833fd24d7b98ac9ac0ca40`，并已绑定到 compact/inventory audit。build/JIT/其他检查没有独立终态时钟，记为 `unknown/included`，不能从 O1 阶段费用中扣除 p4 小计后冒充 build 实测。

四条 p4 记录如下：

| record | bare field L2 / scaled curl | I4 true residual | I4 field L2 / scaled curl | I4 seconds | 真实不足 |
|---|---:|---:|---:|---:|---|
| `A2R160_BAL_H_p4_01` | `0.8489923330716638 / 0.8488357966287257` | `0.9502310252350668` | `0.9647147926182198 / 0.964639027200986` | `6.0514075710001105` | residual改善但场误差变差，且仍远高于 `1e-4` |
| `A2R160_BAL_H_p4_02` | `0.9146177153493735 / 0.9142807117909154` | `0.1012649488434464` | `0.8777570760481551 / 0.8773717677729929` | `5.5842256810014685` | residual和场误差均改善，但仍约 `10^3` 倍高于目标 |
| `LIGHT448_BAL_H_p4_09` | `0.8581820338128715 / 0.8581222874792352` | `0.9778952412775763` | `0.9928176043406823 / 0.9928022756707928` | `5.449962579003718` | residual改善但场误差变差，4 步内部纠错不足 |
| `LIGHT448_BAL_H_p4_10` | `0.9154309172609856 / 0.9151104456074007` | `0.10194959659698315` | `0.8775511199054001 / 0.8771869820432219` | `5.575606445003716` | residual和场误差均改善，但仍未达 `1e-4` |

四条 record 名称中的 BAL_H 是历史 g/reference packet 标签；本轮只做 bare B4/I4 内部检查，没有执行完整 BAL_H 或 ONE_C 外层 PC，因此不能推出框架优劣。reference residual 约 `1e-11` 和 A4 identity 约 `1e-13` 是评价/身份字段，不是 I4 收敛证据。已完成工作量的保守下界为 4 I4、至少 20 B4、至少 840 次局部 `M_D` solve；停止时的 in-flight work 未计入。

## 资源与 official 边界

新 profile 的局部库存 cap 为 `2684354560 B`，旧 V10/V11 cap 仍为 `2147483648 B`。O1 retained lifecycle 的最大记录值为 `2180383916 B`（C_U 后），W transfer 后为 `2180380092 B`，均低于新 cap；tree RSS/PSS 峰为 `2574671872/2539922432 B`，样本无 cap violation、swap 为零。这些字段分别代表 derived inventory 和 measured process-tree memory，不相互替代。

未运行项包括 restart32/64、p6 full residual、original/notch、E/H、near-field、R/T/A、`A_volume`、modal amplitudes、衍射级、守恒和 official result；p6 原方程 `1e-6` 门槛没有检验。V5 原始/notch 成功 baseline 仍保留，但其条件参考 workflow 的 448 页 global `pswpout` 归因仍为 `UNRESOLVED`。不得从局部残差、p4 reference residual 或低 swap 推导 official physics pass。

## 测试和交付

最终 changed-source focused regression 为 `27 passed in 0.72 s`；停止安全性 smoke 为 3 个 `PASS`，包括 monitor-at-10 保留安全解、external-at-50 保留 iteration48、真实 `FloatingPointError` 原样传播。9 个 V12 dat 的 public `--dry-run` 均 exit 0 且 PDE 未启动；qualified activation 下 `complex128/int32` ABI、`compileall` 和 `git diff --check` 也通过。Ruff 只做 parent 保存的 changed-file F821/F822/F823 检查通过，不作 full-repository Ruff 或 CI 通过声明。

raw stdout/stderr 已保存在 [focused stdout](outcomes/records/v12_final_root_focused.stdout.log)、[focused stderr](outcomes/records/v12_final_root_focused.stderr.log)、[stop smoke stdout](outcomes/records/v12_stop_smoke.stdout.log)、[stop smoke stderr](outcomes/records/v12_stop_smoke.stderr.log)，哈希和完整测试边界见 [test summary](outcomes/test_summary.md)。

## 分支状态与后续

本轮正式运行的 source SHA 为 `e8c3c82bab2687a811a11f0798a2879c725532b5`，review base SHA 为 `96e5d5fcfc3e801ef33d4a2d241ea7571937f734`；代码提交已推送至 `origin/task39extra`。本次 docs/evidence closeout 仍只提交到 `task39extra`，不得合并 `master`。审阅入口为 [V12 selective merge boundary](outcomes/selective_merge_manifest_v11.md) 的最新 V12 节、[workstation handoff](outcomes/workstation_handoff.md)、[development progress](../development_progress.md) 和 [model registry](../development_model_registry.md)。

若要继续 O1/O2/O3，必须先有新的 review、独立预算，并重新绑定新的 source/input/artifact identity；本轮不自动升 cap、延长 I4、扩 MPI、启动 5 nm/0.7 nm 或 workstation heavy case。
