# Review V14 阶段回应：工程已测，正式证据仍缺失

本文件是阶段记录，**Q0–Q6 尚未完成，不能据此结项或批准合并**。本轮先核对既有产物，没有为了补远程记录重跑计算。已经找到的正式运行只有一次在文件系统 I/O 故障中断的 Q0；本工作区与 canonical clone 的已查产物中没有完成的 Q1/Q2 配对结果。若完成结果位于另一目录或环境，应先定位、校验身份并复用。

## 三个问题目前能回答到哪里

| 问题 | 当前回答 | 缺少的必要证据 |
|---|---|---|
| 准确 Schur 是否省内存？ | `COMPARISON_INCONCLUSIVE`。这种方法先消去每个单元内部的未知量，再解接口和端口，最终恢复内部场；减少接口方程的规模并不保证减少完整计算的内存。 | 同环境、同三 RHS 的 Q1/Q2 原 A4 精度，以及包含全部内部/接口因子、装配转换、恢复和清理的全过程 RSS、常驻库存、setup/调用时间。 |
| 唯一接口近似逆是否有效？ | `EVIDENCE_INCOMPLETE`，尚不能保留或关闭其数值结论。工程路径用一次固定的“内部消元—接口两级修正—恢复”替换旧 I4；它的代数测试不能证明真实 p4/p6 效果。 | 三份真实 p4 RHS 的准入、实际 BAL_H 耦合、同一步数和同时间附近的历史比较。 |
| 完整 p6 original/notch 是否通过？ | 没有正式通过证据。 | 原 A6 最终 `1e-6`、场/旋度与完整物理输出、最终父进程清理及全过程资源 Gate。 |

准确 Schur 没有内存收益不自动禁止 Q3；共同核心正确且资源准入通过后仍应执行唯一接口候选。Q3–Q6 的未运行状态只描述当前事实，不代替后续实现或最终收口。

## 已保存的 Q0 事实与源码身份

| 项目 | 实际记录 |
|---|---|
| Review base | `25c90229410ca4f75406307ff55ea1ebad343b7b` |
| 已有正式 Q0 source SHA | `efea244159d63a7c9db67ca091e29a9c19f9ce88` |
| Q0–Q2 五份紧凑证据本地提交 | `4b7175abe02a3a67c63a87234e24877eeab0a78e` |
| 已核对的远端 task39extra HEAD | `efea244159d63a7c9db67ca091e29a9c19f9ce88`，尚未包含上述证据提交 |
| 最后可靠 Q0 阶段 | 公共 setup，P64 transfer 已生成；没有 metric 完成、reviewed RHS 或 `q0_core_complete` |
| RSS / PSS | watchdog 有效前缀 373 行的进程树采样峰值 `1,417,695,232 / 1,385,432,064 B`，不是完整 workflow 峰值 |
| 常驻 inventory / 完整 setup / 调用时间 | `not_available`；启动空清单中的 0 不代表实际库存为零 |
| 直接故障 | `2026-09-12T12:38:19.308Z` 可见 outer exit 135；写 manifest 的 EIO 后，读取 ledger 结算再次 EIO |
| 最终终止、清场和 zero-swap Gate | 终态缺失，不能认证；有效前缀内 job VmSwap 为 0、全局交换增量为 0 |

完整时间线、input/resolved/physical SHA、原始文件 hash、三份冻结 RHS 的缺失字段和准确停止边界见 [阶段结果](outcomes/p4_schur_v14.md)、[compact](outcomes/records/p4_schur_v14_compact.json)、[comparison](outcomes/records/p4_schur_v14_comparison.json)。这里不拿 V5/V13 的数值填充本轮 Q1/Q2。

## 预算与续算边界

原 `review_v14/shared_workflow_ledger.json` 保持原样，SHA256 为 `b3ef68488207af8130cf906222f8699183881645ddbaa7e9cc5081b02eecf8f0`。Q0 attempt 1 仍为 `RESERVED`、600 秒预留尚未结算；`elapsed_seconds=0.0` **不是实际成本为零**。有效日志前缀支持保守时间下界 `104.12926405597166 s`，没有完整终态时间，不能把此下界当完整结算。

本次监督期间没有新正式 worker，没有清零、自动延长或手工结算账本。EIO 是已有基础设施故障证据，不能改称数学失败，也不能伪装为 Review V14 所允许的一次“真实实现 bug 修复重放”。工程修改、小型代数测试和只读证据核对单独记录，不能冒充正式 PDE 结果。

## 工程状态和继续顺序

工程实现已保存到 `5d239140d3931364bc16d35c45458189cd957808`：固定接口候选直接接入 BAL_H；FGMRES32 在同一 KSP 中执行 64 步及 1800/5400 秒进展线；25 秒在完整 PC 返回后请求停止，30 秒由父进程监督整个 PC。每 32 步先保存完整解，再用一次加载的既有参考评价场/旋度；参考不进入算子、PC 或初值。H6 setup、solve 和后续历史读取的费用分开，外层向量和参考/metric 临时副本计入同一个 1 GiB 工作区。

Q4/Q5 的独立 A6 残差、完整物理输出和最终父进程资源检查均已接线；Q6 复用这些检查，从原始范数、功率和资源字段重算，不能只信 `PASS`。原 A4 诊断额外保存 RHS 范数供独立复核，没有因此新增数值作用。最终联合测试 **104 passed in 9.71s**，compileall 和 diff-check 通过；源码字节与上述提交一致。测试包含小型非 Hermitian Schur、固定周期、P/Q、BAL_H、有限 KSP、父 watchdog、Q4 两条出口和 Q6 缺失证据分支，**不等于真实 p4/p6 准入**。

[工程证据](outcomes/records/p4_schur_v14_engineering.json)保存测试原始输出、负的工程测试记录、hash、ABI 和代码身份。输入 schema、旧 watchdog 和文档登记另有 **30 passed in 12.69s**。只读 Q6 smoke 对现有实际账本返回 `Q6_EVIDENCE_INCOMPLETE`，账本未改变。没有运行 full repository pytest 或 CI；当前环境没有 Ruff，因此没有新增 Ruff 通过声明。完整工程编辑/监督/等待时间没有单独计量，不能写成 0；pytest 实测时长与正式 PDE 成本分开。

后续先定位用户所述已完成结果并处理未结算的 Q0 身份；不能仅为补记录重跑。正式准入恢复后，按现有 Review V14 完成 Q1/Q2 配对，再依据共同核心及资源条件进入 Q3。Q3 通过后用同一 KSP 完成原始 p6 的有限窗口和条件续算；完整通过后立即执行同配置 notch。任何真实负结果保留实值、限值、动作和费用。旧 I4/C_U/S-p2、recycling、R64 和其他候选不进入本轮。

## 提交、推送和合并状态

五份紧凑阶段证据已经形成独立本地提交 `4b7175abe02a3a67c63a87234e24877eeab0a78e`，未因远端缺记录重做计算。该提交的推送尚未成功；正在等待针对确切仓库、分支和内容的明确批准。后续工程提交 `5d239140d3931364bc16d35c45458189cd957808` 也仍仅在本地。当前合入边界见 [V14 selective manifest](outcomes/selective_merge_manifest_v14.md)；没有合并 master，没有改变 5 nm 工作线。

自动批准审查拒绝了向 `https://github.com/Rookie1234567/MyFEniCS` 的 `task39extra` 推送，理由是认为此操作向尚未核实的外部 GitHub 目的地导出私有仓库内容。用户先前的推送授权已存在；本次额外阻断来自自动批准审查。没有通过其他执行路径绕过，也没有重试被拒绝的操作。
