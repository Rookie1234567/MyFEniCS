# M6A 全空间无矩阵 DtN 与后续时谐/PDE边界

## 当前状态

M6A 的作用是验证冻结的 80 模式端口 DtN（Dirichlet-to-Neumann，给定端口场后计算端口通量）在真实 p6/h10 全空间上可执行，并与独立的流式 direct modal-sum 对照一致。它只验证端口 action/恢复的数值和架构合同，不等于时谐 PDE 求解或最终物理结果。

| 路线 | 状态 | 边界 |
| --- | --- | --- |
| M6A matrix-free full-space DtN | `PASS / QUALIFIED` | 仅 action/DtN authority；checker 15/15，通过 MPI1/MPI2 对照 |
| M6B/time-harmonic screen | `not_run_yet` | 未运行 |
| full time-harmonic PDE / RTA / field recovery | `not_run_yet` | 未运行 |
| 最终 PDE `<2,000,000,000 B` process-tree 目标 | `not_run_yet` | 未测量，不能由 M6A peak 代替 |

## 固定模型与数值结果

| 项目 | 实测/合同 |
| --- | --- |
| source | `2a9dabaa13365373864814d7146ee9399395ed51` |
| mesh/space | p6、h=10.0、252 cells、173,802 global rows、9,210 constraints、local nloc=882 |
| port modes | 80；mode manifest SHA `8d7c396b5251365c6865b2fafefd37e1559794fe39f445ef8bccc3b8ff29cac5` |
| physical layout | `fine_space=uncondensed_fullspace` |

MPI1 与 MPI2 的 candidate action、独立 direct action、physical RHS、recovery 和 repeat 五项误差均为 `0.0`，且 finite。checker 的 cross-MPI source/action/RHS/recovery 与 mode-manifest checks 全部为 `true`；cross-MPI recovery relative error 为 `0.0`。

| 阶段 | peak RSS | swap | elapsed | compiler descendants | cleanup |
| --- | ---: | ---: | ---: | --- | --- |
| isolated stage | `527,859,712 B` | `0` | `13.230624606 s` | 有，属于隔离 JIT stage | `true` |
| MPI1 online | `388,956,160 B` | `0` | `21.308124773 s` | `[]` | `true` |
| MPI2 online | `693,411,840 B` | `0` | `14.421220687 s` | `[]` | `true` |

retained+work 为 MPI1 `16,673,350 B`，MPI2 每 rank `8,378,950 B`、global sum `16,757,900 B`，均低于 `150,000,000 B`。在线 cache 的 20 个文件满足 `stage == before == after == final`；online 未产生 compiler descendant。

## 架构边界

candidate 与 direct oracle 都不物化 PETSc C/D、global、augmented 或 Schur/trace matrix；explicit C/D count 均为 0，采用两个流式 direct assembly pass 和每次一个 80-complex modal Allreduce。无 static condensation、trace-slab PC、DtN retained matrix、FE-sized numeric allgather；输出/载荷使用 owner-local dual 语义，source 保持 primal 语义。M6A 仍不是 PDE、RTA 或 official physics qualification。

## 早期负证据

M6A run1 的 online-JIT/cache lifecycle negative 与 run2 的 watchdog JSON serialization negative 都是 execution failures，分别保留在原 raw/check 路径中；不把它们改写为算法 FAIL，也不把它们当作 PASS。run3 是修复后的唯一 positive authority，本 outcome 不覆盖 run1/run2/run3 raw 或外部 checker。

## 证据索引

| 证据 | 路径 / SHA |
| --- | --- |
| run3 raw | `benchmarks/artifacts/task037_extra_development/m6a_2a9daba_run3`；raw tree digest `665f3a02a13f73c0a949e817c3b2bc7fc915166c10f61dc844c09a242f7cff52`（82 files） |
| watchdog summary | `.../m6a_watchdog_summary.json`；`2a275b43f756a54e8285d0bc16d57947e6731d1615d91ecc37d2295182ffccd6` |
| stage summary | `.../m6a_stage_summary.json`；`a1f157314a5b3651090e61d9bc58523c15aaf6ace9f77fa1c15e992bb11046bd` |
| MPI1 worker summary | `.../mpi1_worker_summary.json`；`65bcb6cad5bf6cc856867f474fbeb8114f7da4509b58df667a728ba470f31341` |
| MPI2 worker summary | `.../mpi2_worker_summary.json`；`ad92cb53a6256b6a3c5081bccabd9c8d9a0d663a53aad2daca963cb48c3c1646` |
| external checker | `benchmarks/artifacts/task037_extra_development/m6a_2a9daba_run3_check.json`；`d121f19553576e1fcce947325edc35c1ef16ecbf370cab9b7ad1477fe16b0c2a` |
| checker embedded evidence | `9a412106a6428c1555b58945eeda6a5b1294bd0e1e85bc763c6c46a7314f30a4` |
| tracked compact | `benchmarks/cases/101_task37_extra_development/records/m6a_fullspace_matrix_free_dtn.json`；byte-for-byte copy of external checker |

M6A 的 action peak 不能当作 PDE peak；W5 time-harmonic screen 已正式运行，但 full PDE、field/RTA、direct-authority physics comparison 和最终 PDE RSS 仍等待后续阶段。

## W5 disk-backed time-harmonic screen（正式负结果）

W5 将 Krylov 基向量放到外部 scratch 文件，减少常驻进程内存；这解决的是内存生命周期问题，不会自动改善算子谱性质或迭代收敛速度。W5 的资源和证据检查通过，但真实残差数值 Gate 未通过，因此不能作为 PDE 或 RTA 结果。

| 项目 | 结果 |
| --- | --- |
| source / checker | producer `41cbbd454eb8336d9ea5378ed618447acfc60aac`；checker `9317e19e924e5b15297c168ea4f2271ae42172eb` |
| classification | `NUMERIC_FAIL`；`execution_evidence_ok=true`；`resource_evidence_ok=true` |
| peak / swap | `1,607,802,880 B` / `0` |
| true residual 20/100/150/200 | `0.3237575899853163 / 0.18105272614044404 / 0.15403613391023072 / 0.12750559935416836` |
| 150→200 improvement | `0.17223578573793497`，通过 `>=0.15` |
| 数值 Gate | 20、100 和改善率通过；200 要求 `<=0.08`，实际 `0.12750559935416836`，失败 |

W5 compact checker 为 RC1 的预期负结果，记录在
`benchmarks/cases/101_task37_extra_development/records/m6b_w5_disk_fgmres_screen.json`。full time-harmonic PDE、official RTA、direct-authority physics comparison 和最终 PDE `<2,000,000,000 B` 目标本轮均未运行。用户已授权继续针对具体收敛问题研究，但没有放宽 2GB、swap=0、true residual 或物理一致性 Gate；冻结的 W5 raw/watchdog 和更早负结果均保持不变。

## W6B-S0 固定多阶基的离线诊断

W6B-S0 只读取 W6A 的 390 列 `AZ` 磁盘 scratch 和四个冻结 W5 residual，比较旧 75 列与固定追加的 `n=0, m=-7..-1` 列集合。它没有重新生成 FE 函数、调用 physical/DtN action、运行 KSP 或 PDE；因此这里只能说明残差与已生成列空间的关系，不能称为 formal W6A Gate 或 PDE 结果。

| 项目 | W6B-S0 结果 |
| --- | --- |
| classification | `DIAGNOSTIC_ONLY` |
| full390 rho（20/100/150/200） | `0.9703655744743773 / 0.9818418639331844 / 0.980066335096579 / 0.9764446942793938` |
| iter200 相对 legacy75 改善 | `0.0235440355720149`，低于 `0.15` |
| 进程树峰值 / swap | `196,874,240 B / 0`（离线诊断实测） |
| AZ scratch | `1,084,524,480 B`，磁盘占用，不计作 RSS |
| formal / PDE / official RTA | `false / false / false` |

W6A 正式数值 Gate 已经给出 `rho390@200=0.9764446942793935`、相对改善 `0.023544035572015565` 的负结果；W6B-S0 在约 `4.6e-15` 内重算复现。iter200 的 component=1 追加组是主要信号（`rho=0.9767683658573292`），component=0 和 component=2 的收益很小；按固定阶次累计，完整 `m=-7..-1` 仍只达到约 `2.35%` 的改善。因此现有数据不足以支持“仅继续加入 n=±1 就能达到 0.70”这一假设，本轮不启动新的大规模 builder 或外层 screen。

compact 证据为
`benchmarks/cases/101_task37_extra_development/records/m6b_w6b_s0_5c34906_spectral_diagnostic.json`，file SHA `1a4e34e4f50d633986ef68c88222edab3a4f3bb1d247033a3389e98cc4be2a90`，embedded evidence `333d2dfb0822b21d24fc97ec0b7dc63325179051d14a7c977a674944acecf280`。W6B raw 和 watchdog 只读绑定，旧 W5/W6A 负结果保持不变；full PDE、field/RTA、direct comparison 和最终 PDE 内存目标仍未运行。

## W7-S1 固定重启 continuation：正式数值负结果

W7-S1 从冻结 W5 iter200 的解开始，把它作为新的初始猜测，然后重新建立一个最多 200 步的 disk-backed right FGMRES cycle；它不是把旧 Krylov 基扩展到 400 维。固定 local checkpoint 20/100/150/200 分别对应累计 identity 220/300/350/400。

| local / cumulative | true relative residual | 结论 |
| ---: | ---: | --- |
| 20 / 220 | `0.12661146396748116` | 记录 |
| 100 / 300 | `0.1253957238823895` | 记录 |
| 150 / 350 | `0.12438973880901087` | 记录 |
| 200 / 400 | `0.12141751388827249` | `<=0.08` 失败 |
| 350→400 improvement | `0.023894454230681927`（约 2.389%） | 诊断项，低于 15% |

独立 checker 分类为 `NUMERIC_FAIL`，但 `execution_evidence_ok=true`、`resource_evidence_ok=true`；唯一 hard numeric problem 是 cumulative400 residual。进程树峰值 `1,611,878,400 B`、swap `0`、进程已清理。预测 live set `1,666,871,296 B` 是 derived/not measured；外存 Krylov scratch 是磁盘占用，不能当作 RSS 或 PDE 通过。

W7-S1 compact：`benchmarks/cases/101_task37_extra_development/records/m6b_w7_s1_restart_disk_fgmres_screen.json`，file SHA `3fcabe2dbc753017158b7f587f025a73a4e5f2eb5b7539d264cd3984846a192d`，embedded evidence `6c92da32f39e4a82ab8cffc851a437e5adb804fa62ebffc13d4068d3c83b9f6b`。producer source 为 `7febc1e3aeb52613d098fd2aadede3b288c69b5b`，checker source 为 `5e72e45673b05dac3c2c15c7c7e1b7fb4dfdee39`；旧 W5/W6 负结果及 W7 run1/run2 受控失败保持不变。

本轮仍未运行 full PDE、official RTA、field/direct-authority physics comparison 或最终 PDE `<2,000,000,000 B` Gate；没有放宽 residual、swap、内存或物理一致性要求。
