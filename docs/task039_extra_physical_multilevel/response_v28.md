# Response V28：Review V25 / V27 working-set 与 p6 setup

## 结论

本轮对象是 13.5 nm original Full3D、p6/h7.5、990 cells、80 个通道、q4 exact two-level condensation/BAL_H、MPI1 单线程。既有 r2 完整 workflow/KSP/setup 基线分别为 `3114.283619607013 / 2284.681783819 / 781.971881371981 s`；本轮没有新的整场运行，因此没有新增全流程收益数字。

R1 依照后续明确授权，对 BAL_H 探针接口 bug 做了一次且仅一次定向 replay。attempt03 的部分失败原样保留；attempt04 重建一次 p4 factor 和 p6 cache，补齐 BAL_H 与第112步的工程算子配对。最终 R1=`NO_REPRODUCED_IMPLEMENTATION_REGRESSION`，其范围限于六组保存向量的短操作：全部等价门通过，每组 R2/V26 输出差均为0。没有复现历史 V26 全 KSP 慢约18.9%的差异，但短操作不等同完整 KSP，也不能证明机器状态或供电影响不存在。

R2=`NO_ADOPTED_CHANGE`，保留 r2 速度基线与当前 ordinary default；R4 fresh formal PDE=`NOT_RUN`。没有新 solver true residual、场或 R/T/A。attempt04 在 dirty source identity 下运行，不把证据冒称为本次最后文档 commit 的 clean-source 结果。

## 按阶段回应

| 阶段 | 结果 | 说明 |
|---|---|---|
| R0 接线、ABI、资源策略 | PASS | qualified WSL Linux 环境，PETSc complex128/int32、MPI1；AC1 采样 online；CPU 频率、温度与 threadpool inventory 未知 |
| R1 同工作集短配对 | `NO_REPRODUCED_IMPLEMENTATION_REGRESSION` | attempt03 的 i16 A6/H6 保留；一次获准 replay 完成 i16 BAL_H 与 i112 A6/H6/BAL_H；全部门限通过 |
| R2 准备耗时与选择 | `NO_ADOPTED_CHANGE` | 精确 local kernel 占 builder audit 约94.38%；没有可证明安全且有效的候选优化 |
| R3 选择与回归 | PASS（保留现有路线） | r2 仍是速度 baseline；ordinary default 不变；最终 targeted tests 复核后记录 |
| R4 fresh formal solve | `NOT_RUN` | 本轮没有采用优化；不提供新残差、field、R/T/A 或 formal memory |
| R5 文档与证据 | READY FOR HANDOFF | 本 response、outcome、机器记录及 run index 统一反映四次尝试；D1 已在 `task39extra` 提交，D2 为本批证据收口提交；最终远端 tip 由 handoff 核验 |

## R1 重放经过与结果

attempt01 在 worker 启动前被 watchdog 专用父进程门拒绝，没有启动 factor；attempt02 因未注入 `phase_path`，worker 在 FE setup 前退出，watchdog elapsed 约2.023 s。attempt03 建成一个 p4 factor 和 p6 cache，在 i16 A6/H6 通过后，于 BAL_H 第一次应用前触发 `TypeError`：`InterfaceBalancedCoupling.apply(source)` 只接受一个 source 并返回结果向量，probe 却沿用了需要 `(source, target)` 的通用 `apply_owned` 方式。这是 probe adapter bug，不是数值或 PDE 失败。用户随后明确授权一次针对性 replay；attempt04 使用修正后的 probe 副本重建工作集并完成剩余配对，worker 正常退出。没有第二次 replay。

| 已保存向量步数 | 操作 | R2/V26 中位 wall（s） | V26/R2 | 数值与原始身份 |
|---:|---|---:|---:|---|
| 16 | A6 | 3.252565 / 3.243044 | 0.997073 | 输出差0；native相对差6.71e-15；SHA `7ced34db…7cbe`（attempt03） |
| 16 | H6 | 4.000405 / 3.976555 | 0.994038 | 输出差0；SHA `c5c99b02…6020`（attempt03） |
| 16 | BAL_H | 18.734961 / 18.635279 | 0.994679 | 输出差0；SHA `7295a18a…7f29`（attempt04） |
| 112 | A6 | 3.254658 / 3.260999 | 1.001948 | 输出差0；native相对差6.16e-15；SHA `56fa5316…4dfa` |
| 112 | H6 | 3.845772 / 3.762207 | 0.978271 | 输出差0；SHA `351077a9…0f3f` |
| 112 | BAL_H | 16.927638 / 17.181086 | 1.014972 | 输出差0；SHA `8243d575…6daa` |

各配对均有三轮 AB/BA/AB 与 warmup，具体 CPU/wall 数字见 hash-bound raw JSON 和 [R1 combined pair record](outcomes/records/workingset_p6_setup_v27_pair.json)。BAL_H 每次逻辑应用有2次 p4 MatSolve、0次额外 refinement solve；最大内部 A4 相对残差分别为 i16 `9.167487524231193e-12`、i112 `6.470229892354096e-12`。i16 BAL_H 的首个 V26 wall trial 是22.574 s，明显高于后两轮；两个候选路径随轮次都变快。AC在线并不等同固定了电源模式或CPU频率，本轮未能从记录中排除这些及其他系统状态影响。

这些操作以历史 V26 残差向量为输入，不是新的 Krylov 迭代。`||r16||=0.0059228472836568066`、`||r112||=3.879261627632226e-6` 是输入向量范数，不是新的 true residual。历史 V25 Q4 i112 baseline 的显式真残差 `2.71399585136905e-6`、累计 solve time `3437.2333360950015 s`、RSS/PSS `7384477696/7352336384 B` 仍只是历史参考，不能填充 V27 正式结果，见 [V25 Q4记录](outcomes/records/a6_h6_coarse_degree_v25_q4.json)。

### setup 花费与资源口径

两次实际 setup 的 p4 numeric factor 时间为213.987342 s、223.155029 s，合计437.142371 s。p6 setup 同时保留内部与外围两种明确边界：内部 setup total 为255.476535 s、249.130047 s（合计504.606582 s）；外围 retained-setup wrapper 为255.485893 s、249.145521 s（合计504.631413 s）。builder audit 是其内部子阶段，分别249.919023 s、242.479440 s（合计492.398462 s）；不得将该嵌套时间再加到 setup 总额上。

每次因子规模84680行、32320342 NNZ，`ICNTL(23)=4687` decimal MB。attempt04 builder audit 中 kernel 为228.841967 s、占94.3758%，local Schur为11.954928 s；12种raw tensor class、26种oriented Schur class，numeric cache 325283184 B，identity矩阵只读共享、唯一存储1.62 MB。与旧 V26 `p6_build_seconds=259.023949 s` 和 kernel `244.655193 s` 对齐比较所得是单次、未配对描述差，不是因果加速。旧的“V27 retained setup 对 V26 builder”的混口径比较已删除。

attempt03/04 watchdog elapsed 分别723.647/966.854 s；同步进程树RSS峰值分别7132229632/7148744704 B、从同一采样树重算的PSS峰值分别7100228608/7116825600 B；swap均为0。该 engineering worker 同时保留了一个p4 factor、p6 cache、ports/work vectors 和两侧 candidate actions，但没有完整 formal FGMRES basis/history。这些数值不能当作 production 单候选 solver 峰值，也不能排除正式 Krylov history 的内存影响。

attempt04 raw evidence位于 [attempt04目录](../../benchmarks/artifacts/task39extra/workingset_p6_setup_v27/r1_attempt_20260923_04)，复用的 i16 A6/H6 原始pair位于 [attempt03目录](../../benchmarks/artifacts/task39extra/workingset_p6_setup_v27/r1_attempt_20260923_03)。attempt04 identity：HEAD `bb541cf3286b89734181d1da1a0ecfd2a5078243`；dirty tracked diff SHA256 `1d9a5283c57acce7453baf52466e1d062a0bb8c8afcb905497800023cc41fb69`；source-state SHA1 `665a8528ac0ab0937189b40f254e6ca844c8b095`；probe SHA256 `3b81385fe019dfb31d758325129b85abd70f2807e39af6b4eb19b50ae1be7d4b`。该 hash 绑定 replay 原样状态，而非后续提交。

## R2/R4 与验证边界

R2 审计找到12种 raw tensor class，各自只有一份活动 kernel；26种方向Schur也已按唯一class生成。现有证据不支持重复做大量相同class计算，主耗时仍是精确 FFCx kernel。尚无兼顾局部物理检查并能降低该主项的已验证低风险实现，因此不新增 JIT/backend、不跳过检查、不作几何近似；后续研究入口只登记为 same-integral exact local tensor tabulation。选择不变：R2=`NO_ADOPTED_CHANGE`、r2速度基线保留、ordinary default不变、R4不运行。

qualified WSL activation 下 ABI preflight 通过（PETSc complex128/int32）。五文件 focused code suite 为 `47 passed in 8.29 s`；三文件 documentation contract suite 为 `21 passed in 0.07 s`。最终 JSON parse、原始 pair hash 对照、documentation contracts 与 `git diff --check` 均通过。未运行 full repository pytest、Ruff、CI；也未做 temperature/frequency qualification 或 fresh PDE。详细字段与负历史见 [V27 outcome](outcomes/workingset_p6_setup_v27.md)、[pair](outcomes/records/workingset_p6_setup_v27_pair.json)、[selection](outcomes/records/workingset_p6_setup_v27_selection.json)、[compact](outcomes/records/workingset_p6_setup_v27_compact.json)、[decision](outcomes/records/workingset_p6_setup_v27_decision.json) 和 [run index](outcomes/records/run_index.json)。

Git handoff：执行分支 `task39extra`，upstream `origin/task39extra`；Review V25 记载的 reviewed base SHA=`73d1f1f4ee3e13b85ceac6c37b667857f6d0576a`，本批开始时 HEAD/D1 parent=`bb541cf3286b89734181d1da1a0ecfd2a5078243`。D1 implementation commit=`cefb47c6d2039f82f441854e5d1edd8642de0c95`；D2 为本批文档和证据的当前提交。最终 D2 SHA、远端 ref 一致性及工作树状态在交付消息中报告。
