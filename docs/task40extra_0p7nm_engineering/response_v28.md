# Task40extra Review V28 执行回应：完整 q0 CSR/native 通过，factor 资源准入停止

| 首先回答的问题 | 结果 |
|---|---|
| 完整数值 CSR 是否完成 | **完成**：777,644²、577,061,168 个结构槽；numeric nonzero 560,366,994、exact-zero 16,694,174；complex128/int32，有效 payload 11,544,333,940 B |
| 是否复用 V27 pattern | **复用**：旧 manifest/hash 保留；FE/MPC/native/producer/routes/pattern 重建0；原无hash的data清零重填，无整份CSR复制 |
| 四次 native 对照 | **PASS**：最大相对误差约1.91166e-14≤1e-11；输出和资格在factor前保存；主控独立重算保存输出也通过 |
| 吞吐、峰值与瓶颈 | numeric parent734.324s，readback parent286.435s；treeRSS12,497,358,848 B，cgroup13,044,125,696 B，task swap0；下一阻塞为factor准入 |
| 下一次如何执行 | [现有AUTO续作命令](outcomes/target_stage_handoff_v28.md)；当前COMPLETE+匹配PASS自动跳过fill/readback，直接factor准入；同16GiB条件不重试 |

CSR把稀疏矩阵的行起止、列号和复数值分别保存。本轮直接用已核验的保存贡献补齐数值；稀疏局部投影减少对零映射的计算，H按实际保存缩放计算，C/−D保留原复数与普通转置合同。收益是完成全部矩阵系数，代价是仍需保存和回读约11.5GB的CSR。实际模型为去掉notch/void的272×2×14=7,616-cell regular reference之q0；原尺寸parent target为50×25×140nm、0.7nm、272×8×14=30,464cells的真实非分离Si/air。此次未解target PDE。

## 身份与持久证据

| 项目 | 完整身份 |
|---|---|
| 分支 / 审阅结果base | `task40extra_0p7nm_engineering` / `4e04f2fe2b3ea22e67cbd93ee1ffebfd66b50a79` |
| Review / 最终科学source | `b52c8d47a9db7f4e9d7f6d134a7f307b8728a4ab` / `c6624391d8f96e257d1efa914cb38821e2a87eb9` |
| attempt / service | `20261012T002559.817050Z` / `myfenics-case-20261012T002548-2353316.service` |
| input SHA | `134ea5f08d5d5dbc366870f451ba0de0df5893c5cd73d227dac77f8a11aa2c0b` |
| physical-model SHA | `ea3bc109992cabeae2f13e6adc5d3eb779fb92a2c75dcd355426e88957680241` |
| window SHA | `dcefcfbf476f09b388554afc81a65ea85951d4d6162b6dad8743766e6742c9a0` |
| 固定窗口 | T0 2026-10-11T23:24:00Z；数值cutoff 2026-10-12T05:04:00Z；总deadline05:24:00Z；未刷新 |
| V28 COMPLETE manifest SHA | `ca3c8de9093fd1cfe9e17c8eb557cd2f96920a3ee110549f007e70835d4a2290` |
| native PASS SHA | `63babb2943b7e0f613a2c531afd09f931c4ee5504a345748c52f6ef38b0e9c81` |
| 原 V27 manifest SHA | `1ea707f3c201359c390b620a5122d0102f5b34bd74873b5f00e3a40b673b94de`；原incomplete状态与字节保留 |

manifest的`current_execution_identity`保留创建时source`52b435d2955c07b1890107b39939f8092ce954e8`；`numeric_fill_identity`、qualification与终态stage绑定实际source`c6624391d8f96e257d1efa914cb38821e2a87eb9`。producer`9d0f4dbfc730dd620b709d048e33e9da6c77520c`、V26科学source`f9093c87f81d52b75fbc156e562b3745df45ccf4`、V27 pattern source`61530133bd02b18052e3ba64a5f78b87424c57f6`分列。完整donor、数组和回执路径/hash见[operator compact](outcomes/records/target_operator_probe_v28.json)。

## 数值与进度

| 比较项 | 相对误差；限值统一1e-11 |
|---|---|
| x1 / x2 total | 1.9116580127740397e-14 / 1.9044249363689425e-14 |
| volume / −D | 1.9115170598605398e-14 / 4.0018002857899965e-15 |
| C / Hhat | 1.0992641636347272e-15 / 1.0985392495312836e-16 |
| trace+port重组 | 2.8011401775529595e-16 |
| 四个native off-block | 全部0 |

Hhat1/1、volume7,616/7,616、surface15,864/15,864，共23,481次成功回调。raw generic contribution count23,480不含一次direct H，不能解释为漏项。`contribution_cursor=null`，进度不构成恢复游标。主控从四份保存输出和旧native/input重算最大1.9116580127738185e-14，新增FE/native/refill/CSRmatvec均0；审计SHA`577dc063324a083cd285cceddb7cc60b1a4516cffb0149e3eb94af9e132a2469`已纳入索引。

最后progress的status仍为`READBACK_IN_PROGRESS`、surface ETA仍57.583s，但`readback_completed=true`且全部贡献完成。该状态/ETA已过期，终态以COMPLETE manifest、native PASS和`RESOURCE_CONTROLLED_STOP_AFTER_Q0_CSR`为准；原progress未重写。

## 两层计时与资源

| 区间 | monotonic/perf_counter秒 | UTC/保守预算秒 | 范围 |
|---|---|---|---|
| data clear+initial flush | 52.559229 | 未分录 | fill之前 |
| numeric parent | 734.323900 | 未分录 | 包含贡献生成、投影、scatter和回调 |
| data hash | 50.957251 | 未分录 | fill/最终flush之后 |
| readback parent | 286.435002 | 未分录 | 内含4次matvec |
| watchdog | 1251.751109 | UTC1392.471546 | 嵌套在run_case，不另加 |
| outer run_case | 1254.529095 | 1395.251160 | 包含准备、填值、回读和factor拒绝 |
| required checker | 60.846029 | 68.050427 | 与run_case不重叠；21/21通过 |
| 已记录完整service parent链 | 1316.226225 | 1464.152690 | 含activation/ABI/run_case/checker/间隙，未记录systemd首尾为UNKNOWN |

四个数值阶段互不重叠但不覆盖全部准备/最终flush/统计/保存；未分录部分保持UNKNOWN。generation/projection/scatter=203.372/278.819/136.587s已在numeric parent内；gate145.112s横跨若干子项，不能再相加。H/volume/surface callback parent1.463/203.094/476.283s不是完整父区间分割。读取与局部约束未单独计时，不能宣称某一项占绝大多数。UTC正差run_case140.722s、checker7.204s原因未证明，保守费用保留。V27 pattern2106.866994s、route计数/I/O为历史继承，V28执行0，不计本轮。

| 资源 / 停点 | 数值与范围 |
|---|---|
| 同时进程树RSS / 专用cgroup峰 | 12,497,358,848 /13,044,125,696 B；cgroup cap17,179,869,184 B |
| task swap / PSS | tree和cgroup均0 B；PSS禁用/null |
| WSL-global swap | pswpin+60页、pswpout0；宿主原有swap非零，全局活动归因UNKNOWN |
| adapter/maps释放后 | RSS414,957,568 B；cgroup12,303,282,176 B；file11,835,424,768 B，文件页仍收费 |
| staging上界 | generation167,923,712 B，projection121,200,496 B，combined167,923,712 B≤268,435,456 B；不相加 |
| raw旧max_staging_bytes | 98,244,536 B属于V27 pattern，不能冒充V28最大值 |
| factor host gate | 新增请求69,340,657,464 B vs可新增4,873,007,104 B；缺64,467,650,360 B |
| factor cgroup gate | current+新增81,647,519,544 B vs扣reserve额度17,045,651,456 B；缺64,601,868,088 B |

两种factor缺口不能相加。拒绝发生在`task40_v26_q0_factor_petsc_conversion`之前，没有PETSc转换、symbolic/numeric factor、probe或第二RHS。原`FAILED_Q0_FACTOR_LIFECYCLE`字段保留，科学分类为资源准入停止。80,884,991,404 B是现行派生envelope，不是实测factor峰值、数学下界或2TB不可行证明。

独立cgroup JSONL共15行、14行有实际内存，teardown行unavailable/null；anon/file/dirty按样本范围记录，不把样本峰当全程峰，不回填worker缺失值。leader exit0、descendants_cleared=true、后代列表空；exit0不等于PDE通过。原始字段与时钟见[time/resource compact](outcomes/records/time_resource_accounting_v28.json)。

## 失败、修复与验证

| 项目 | 实际结果 |
|---|---|
| 首attempt/source52b435d2 | `20261012T001226.307262Z`：clear/flush66.735125s后completion callback引用未定义generation_seconds；watchdog83.759734s，treeRSS12,454,760,448 B，cgroup13,042,233,344 B，task swap0；原失败保留 |
| 最小修复/sourcec662 | 先赋计时变量再回调，数学算子不变；同窗重新clear-all；debug/tests/协调/freeze相邻区间mono592.094932s、保守660.610497s，不称纯编码时间 |
| 初始source软件测试 | 77 passed、2 skipped；executor原log2.42s，main freeze另报2.54s，分列保留；formal NumPy2.5.3 header3 passed |
| 修复fixture首次 | 1 failed、3 passed in0.55s，断言读取错误audit key；原负日志保留 |
| 修复后最终source | 4 passed in0.82s；compileall/diff check PASS；未重跑初始77项整组 |
| 正式partial checker | 21/21 true、full_pass=false；完整CSR三数组hash已实读核验 |
| 主控独立数值审计 | 保存输出重算PASS；无新FE/native/refill/CSRmatvec |
| 文档收口 | 最终本地检查写入resource compact与test_summary；GitHub rendered view待主控发布后核验 |

full repository pytest、MPI2/MPI4未运行，Ruff不可用且未安装，未声称CI。初次管理receipt错用account API、旧NameError/fixture失败、V27 checker null、旧费用/unknown与行政超时全部保留。

## 下一步和发布边界

[summary](outcomes/summary.md)、[test summary](outcomes/test_summary.md)、[交接命令](outcomes/target_stage_handoff_v28.md)、[run index](outcomes/records/run_index.json)、[项目进度](../development_progress.md)与[两级模型总账](../development_model_registry.md)只追加当前结果。执行者不commit/push，主控审查后集中发布；本轮未改变ordinary default或合并master。

全q数值CSR、单q inverse、完整target KSP/PDE/A6 residual、R00_s/R00_p/R00_total、R/T/A/A_volume/衍射场、最终精度与2TB/48h均未资格化。下一具体依赖是主控安排已授权资源上的单q factor完整cache-miss父成本与业务RHS成本，再判断2TB可保留的相同精确因子数量。当前16GiB同条件不反复尝试。
