# Task40extra Review V29 执行响应

**已完成 regular-reference q0 的准确分解、同一因子的两组不同 RHS 求解及独立保存数据复核。** 矩阵为 777,644 × 777,644、577,061,168 个结构槽；纯 CSR 载荷 11,544,333,940 B。它是原尺寸 regular-reference 的一个 q 分块；本轮没有求解真实非可分 target 的完整 Maxwell 场。

因子分解把矩阵整理成可反复回代的形式。第一次构建昂贵，同一因子上的第二次回代便宜；本轮实际测量两种成本，供下一步选择因子驻留方式。数学矩阵、MUMPS 配置和精度门没有改变。

| 阶段/指标 | 实测秒数 | 范围 |
|---|---:|---|
| CSR→PETSc conversion | native 10.592528；父段 14.997011 | 不重建 FE/CSR |
| symbolic | native 19.370445；父段 19.504676 | 同一次因子 |
| numeric | native 625.776310；父段 625.862622 | 仅数值分解 |
| 完整 F_q | 742.097546059 | 从严格身份/初始 CSR loader 到 fresh factor 资格完成；包含 loader 30.286357418 |
| F_q 中已加载矩阵后的父段 | 711.811188641 | 是上一行的子段，不重复相加 |
| fresh MatSolve | native 17.544153；完整测试父段 22.092013 | 真残差 1.977628323114713e-14 ≤ 1e-10 |
| S_q 同因子 MatSolveRepeated | 12.919099 | 第二不同种子 RHS；真残差 1.6069609784650353e-14 ≤ 1e-10 |
| 第二 RHS 完整测试父段 | 17.433398 | 包含制造 RHS、Vec、回代、残差、保存/读回；不是纯业务求解时间 |
| eviction | native destroy 3.352984；父段 3.863306 | 在 F_q、S_q 之外 |
| lifecycle 总父段 | 758.410191 | 不含初始 loader；不是 F_q |
| 原完整 service 父段 | 834.108298 | 包括入口身份/hash、run_case 795.066189 和旧失败 checker 2.138518 |

父子计时不重复相加。两次启动失败 32.873265、42.121692 秒，加原 service 834.108298、新 metadata checker 31.717409、saved-vector audit 73.240248，共 1,014.060912 秒，是互不重叠的已测服务父段和；**不是连续冷端到端时间**。传输、ABI、工程修复/等待及既有 producer/pattern/fill 未藏入 F_q。原准备父区间保守下界 7,676.157757 秒包含较早 4,008.509563 秒，不能重复计费；前缀和未记录子项仍 UNKNOWN。

## 资源与身份

| 口径 | 数值 | 解释 |
|---|---:|---|
| 任务 cgroup 历史峰值 | 84,891,103,232 B | 独立任务，不等于因子独占字节 |
| 同时 process-tree RSS 峰值 | 84,767,309,824 B | subreaper 与全部后代；身份采样完整 |
| Task swap 峰值 | 0 B | 独立 cgroup 与进程树均支持 |
| PSS | null / DISABLED_BY_PROFILE | 未采样，不填 0 |
| INFOG19 allocated 上界 | 63,959,000,000 B | raw=63958 decimal MB；包含后端口径，非独立 factor-only 驻留查询 |
| INFOG22 used 上界 | 55,243,000,000 B | raw=55242 decimal MB；不以 used 绕资源门 |
| INFOG9 | raw -2599；约 2.599e9 因子条目 | 百万粒度近似，**不是字节或 MB** |
| 同时 native objects | factor 1、matrix 1、vectors 2 | 最终 destroy 成功、当前计数均归零；后代为空 |

峰值采样时刻不同，不相减归因。销毁前 RSS 样本 73,172,611,072 B 不是峰值；因子独立常驻、源 CSR/PETSc 共享 backing 的精确拆分仍 UNKNOWN。宿主初始已有 swap 20,787,200 B；Task swap=0 不代表整机历史 swap=0。早期复制在共享 session 中的观测不能作为独占任务峰值。

执行位置是用户批准的 `fenics-ws`（10.14.35.46）`/home/fenics/Projects/laptop_share`，其他项目未修改。固定 cap=549,755,813,888 B（512 GiB）、host reserve=68,719,476,736 B（64 GiB）、MemorySwapMax=0、MPI1/数学线程1；cap 未变成 ICNTL23。实际 native_linux ABI 为 PETSc 3.25.6/complex128/int32、MPICH 5.0.1；fresh receipt 哈希 `1c4277c83a0ac6daf02197086264b9e5b337caee1b33d7cc1dd22a7dfcefe57d`。仅目标 petsc.cfg 中旧绝对路径改为目标私有 prefix，原配置备份与初次导入失败均保留，未升级 ABI。

Review source_at_entry=e85992c79d7e2b3f41cd1396ffb06edccdd93421；数值 source=bee9a1f0e33076e372607581f790bda3a4a0072f；checker source=9a9a9d31f4aebf1564d5f09177c1d3481d64371f。manifest run_id=`task40extra_0p7nm_target_original_ny8_operator_probe_v22`；attempt_id=`20261012T071945.212305Z`；service=`myfenics-case-20261012T071907-236011.service`。数值 worker PID 236201，mpiexec 236199/proxy 236200；run_case wrapper 236184、workflow 236018 分列。

T0=2026-10-12T05:49:12.144309894Z，numeric cutoff=11:29:12.144309894Z，deadline=11:49:12.144309894Z；对应新加坡时间 13:49 开始、19:29 数值截止、19:49 收口截止。窗口从首次目标准备冻结，无刷新。实际工作包观测已收费 14,195.026549 秒（包含等待/修复/测试），是收口编辑前的快照，最后交付前同账观测收费 15444.751282536 秒（包含实现/传输/修复/测试/等待/审查），所有相关服务 MainPID=0。之后很小的 Git 提交/推送费用未单独实测，保留限制；服务子段不重复累加。

## 独立检查与负结果

- 原 required checker exit 2，四项路径/窗口绑定 FAIL，outer 分类 CHECKER_FAILED_RAW_EVIDENCE_RETAINED；原文件没有改判或覆盖。修复将旧 V28 科学 window/CSR/PASS 与 V29 执行 window/source 分开，沿 approved resolver 读实际字节。
- 新 metadata checker exit 0，28 项身份/payload/window 检查通过，父段 31.717409 秒；它本身不重算新 factor 的两组残差。
- 另一个独立只读 numeric audit 对两组全部 777,644 行重算 `A@input_x` 和 `A@solution-rhs`；RHS/residual 均与保存数组逐位相同。NPZ 与各数组 hash 通过、三 CSR 文件 hash 未变，7 项通过。内部审计 70.666563 秒，服务父段 73.240248 秒，不双计；4 次新 factor 相关 CSR MatVec，backend MatSolve/factor/FE/MPC/旧 native replay 均为 0，后代清场与 task swap=0 通过。

新结果 `full_pass=false/official_result=false` 表示 Task40 整体目标仍未完成，不表示 q0 生命周期失败。新旧原始小收据原字节已发布在 [收据索引](outcomes/records/v29_published_receipt_index.json)，大 CSR、两组 NPZ 和 timeline 留在 ignored artifact。

固定窗口内保留两次数值前失败：5bb1040 源的 `_resource_snapshot` 导入错误（没有 factor）；bee9a1f0 源的 pinned mode 文件漏部署（attempt 20261012T071046.659698Z，未 numeric）。后者补齐同范围两个身份文件并复核后续作；原 39 项 24,317,319,033 B 收据不改，补充 36,250,728 B 独立记录，41 项总 24,353,569,761 B。runtime regular transferred 2,625,158,288 B 单列；精确最初 rsync 起止未知，不能用后续观测相减猜时长。

## 下一步与最终目标边界

当前单 q0 已在批准环境完成 conversion→symbolic→numeric→fresh probe→同因子第二 RHS→evict→独立审查；原 WSL 16 GiB 条件没有重复尝试。q1–q7、all-q resident、原尺寸 target KSP/A6/释放后残差、内部/端口恢复与 official R00_s/R00_p/R00_total、R/T/A/A_volume/衍射均未运行。本轮不能宣布原尺寸精度或 2 TB/48 h 达标。

下一唯一主候选是**在完整对象账允许时保留同样准确的全部 q 因子（ALL_Q_RESIDENT）**，减少 ONE_Q_REFACTOR_V19 在固定 8-q 循环中每次重新做 conversion/symbolic/numeric/fresh probe 的费用，数学逆不改。下一批需授权逐 q 建立其余实际 CSR/资格/因子与完整同时库存，含源 CSR、仍保留的 PETSc 输入、factor、target/reference FE/映射/局部 LU/port/inverse bank、构建暂存、Krylov/恢复/输出和系统余量；不以 q0×8 当实测。如果不足则评估固定保留高重建成本因子＋一个流转槽，小于 8 的普通 LRU 在固定循环可能每轮全 miss，不按槽数线性估计收益。

48 h 账需包含必要首次 producer/pattern/CSR/JIT、每次实际重建 F_q 和业务回代 S_q、外层作用/投影/传递/局部恢复/augmentation、target/Krylov、输出及独立检查。当前 q0 数据足以表明重建与重复回代成本明显不同，无法代替其余 q、原尺寸收敛或最终网格/mode 精度证据。本轮不自动开启后续计算，不改 master/ordinary default。

## 软件验证与入口

原准备 15 项 targeted PASS；import 修复的真实 resource fixture 1 PASS；checker focused 79 PASS/1 SKIP，随后仅 CSR containment-order leaf 1 PASS/5 deselected（没有冒称最终整组重跑）；新路径、错误 hash、两代 window 与越界反向验证保持拒绝。文档/JSON/引用的最终检查与日志单列在 [test summary](outcomes/test_summary.md)，不声称 CI/full pytest/MPI2/4/Ruff 通过。

- [实际 q0 执行回执](outcomes/records/v29_execution_receipt.json)
- [operator compact](outcomes/records/target_operator_probe_v29.json)、[资源/费用 compact](outcomes/records/time_resource_accounting_v29.json)
- [metadata 原始 PASS](outcomes/records/v29_metadata_checker_fix02_result.json)、[保存向量原始 PASS](outcomes/records/v29_saved_factor_vector_audit_result.json)
- [summary](outcomes/summary.md)、[run index](outcomes/records/run_index.json)、[真实命令与环境交接](outcomes/target_stage_handoff_v29.md)
- [批准前原回应快照](outcomes/response_v29_preapproval_snapshot.md)：仅历史，不是当前状态。
