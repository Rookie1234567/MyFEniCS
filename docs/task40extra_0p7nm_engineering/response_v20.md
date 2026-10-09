# Task40extra Response V20：原尺寸分阶段入口接通，E2 在符号准入处受控停止

| 项目 | V20 结论 | 证据边界 |
|---|---|---|
| 执行身份 | 分支 `task40extra_0p7nm_engineering`；父级冻结源码 `c319719433e99fe652754f2844c5d79669b111cb`；前一数值源码 `4b004d09b17d07a1f19f4c9d8443e76153e69a4b` | 执行目录干净后由主控冻结；执行者不提交、不推送 |
| B0 Ny=8 与 E1 p6 | 沿用 V19 正式小模型基线：A6 分别为 `1.2189184363e-8`、`1.40358436565e-8`；既有 R/T/A 与 checker 结论不变 | V20 没有重跑，也没有重写 V19 的残差、物理量或负诊断 |
| E2 p6 reference | 完成几何/局部/端口、四个 q 稀疏块和变换表；在 `one_q_symbolic_admission_v19` 由资源 Gate 停止 | `RESOURCE_CONTROLLED_STOP`；数值因子、KSP、场、R/T/A、official packet 均 `NOT_RUN` |
| 原尺寸 Ny=8 几何 | `272×8×14=30,464` 个 p6 单元；材料标签、周期配对和 60 个局部类别通过 | 只建几何库存；未建全局 p6 空间、MPC、C/D、q CSR 或因子 |
| 原尺寸局部/端口组件 | 60 类局部记录；两侧各一个局部端口分解；代表方向匹配 `17/60` | `PARTIAL_CANONICAL_LOCAL_COMPONENTS`；43 类方向仍未资格化，目标算子与全场未通过 |
| 源码入口修复 | 为 V20 原尺寸 profile 增加精确 campaign 路由项，共用只读 V10 campaign 投影 | 不改方程、离散、求解器策略或普通默认值；保留 heavy 授权为 false |
| 最终目标 | `50×25×140 nm`、十进制 2 TB、单场 48 h | `NOT_QUALIFIED`；不代表数学上不可计算 |

## E2 的资源停点与错误分类

E2 是唯一获准的条件增长小模型。四个 q 的 CSR（稀疏行列数据）和变换表已建立；q 是 y 周期边界上不同相位的子问题。内存 Gate 在建立首个 q 的符号因子之前检查下一步将占用的空间，因此本次没有进入数值因子或 PDE 求解。

| Gate 量 | 字节数 | 说明 |
|---|---:|---|
| 当时进程树 RSS | 10,079,617,024 | 同时驻留进程树观测值 |
| 请求的增量 | 486,803,844 | 下一步分配请求 |
| 请求的 workspace | 486,803,844 | 与请求增量分开记账，不能折叠 |
| 待生成逆变换表 | 315,109,440 | future reserve 分项 |
| 最大同时驻留阶段 | 219,340,224 | future reserve 分项 |
| 单 q symbolic guard | 1,947,215,376 | future reserve 分项 |
| 单 q numeric factor reserve | 0 | 本 Gate 尚未给数值因子分配 reserve |
| 固定 future workspace headroom | 134,217,728 | 小型 watchdog/evidence-write 余量 |
| 复算投影 | 13,669,107,480 | 上述项逐项相加 |
| 动态 launch cap | 13,519,601,664 | 投影超出 149,505,816 B，两个内存不等式均未通过 |

该投影不是一次真实峰值。E2 后续实测进程树 RSS 峰为 10,929,668,096 B、专用 cgroup 峰为 11,908,415,488 B；进程树/cgroup swap 均为 0；PSS 数值为 null，状态为 `DISABLED_BY_PROFILE`。WSL 全局 swap 有变化，但不能归因给本任务。空的通用 inventory ledger 也不证明所有实时对象均已释放。

执行、worker 与 checker 分类分别保留：候选 Gate 为 `RESOURCE_CONTROLLED_STOP`；worker summary 为 `WORKER_FAILED`、退出码 4；外层 `run_case` 返回 3，流程为 `CHECKER_FAILED_RAW_EVIDENCE_RETAINED`；required checker 返回 2、状态 `NO_PARTIAL_FOOTER`；service manager 状态 2。外层失败不把候选 Gate改写为 PDE 数值失败，资源停点也不被说成 solver pass。

## 原尺寸几何与局部/端口实测

有限元（FE）把几何切分为单元，并在每个单元上用 p6 基函数近似场。V20 先实际检查原尺寸网格和有限个局部单元，目的是验证入口及局部对象；这一步没有形成完整全局方程。

原尺寸几何使用输入 SHA-256 `f6726d005713b586f1bccfbf6904dd64f3f1f31dd3b069607b55e9b430d294c7`。30,464 个单元中 air/substrate/grating 分别为 18,080/2,176/10,208；60 个目标类别与 60 个 filled-reference 类别逐类共享，没有目标独有类。x/y 周期面配对数为每侧 112/3,808，z 端口面每侧 2,176，坐标配对检查通过。几何库存/读回检查用时 `0.48784481384791434 s`；该阶段计时不代表完整 mesh 构建耗时。

局部方程的原始限值是 `1e-10`，已知解前向误差限值是 `1e-11`，直接 trace carrier 门限是 `1e-14`。两侧保存的实际值如下：

| 端口侧 | 已知解前向相对误差 | 原局部 trace 方程相对残差 | 局部端口方程相对残差 | 局部恢复方程相对残差 | 原门限 |
|---|---:|---:|---:|---:|---|
| bottom | 4.38956601568474e-14 | 6.369701138645506e-16 | 3.0975794244638386e-17 | 4.495120381497924e-16 | 方程 1e-10；前向误差 1e-11；trace carrier 1e-14 |
| top | 4.456757248975752e-14 | 5.735468421207556e-16 | 6.41111060274916e-17 | 4.81676182886157e-16 | 方程 1e-10；前向误差 1e-11；trace carrier 1e-14 |

这些数值支持所测的两个边界局部组件。它们不覆盖所有 60 类方向：17 类有匹配的目标几何/排列，43 类没有匹配方向，仍待资格化。模式 manifest 共 32,060 个有序 key，bottom/top 各 16,030；每侧组件回执另记录 32,060 full-ordered rows、2,004 个批次、432 trace rows。两种计数来自不同回执语义，均原样保存，不互相替换。

## V20 入口失败与工程中断的保留

| 事件 | 身份与状态 | 处理 |
|---|---|---|
| 18:19 E2 full-input 入口 | 源码 `f88d0606a8c351e7185afd9e839e8c8ddfd9bb81`；campaign-window Gate 失败；worker 退出 4；run_case 3；checker 2、`NO_PARTIAL_FOOTER` | `WORKER_FAILED` / `CHECKER_FAILED_RAW_EVIDENCE_RETAINED` 保留；无 official result，无 PDE 阶段 |
| 18:28 E2 full-input 入口 | 源码 `9dad3ab4f48f62e1522437f7560111a364064e40`；ABI 入口 Gate 失败；同为 worker `WORKER_FAILED`、run_case 3、checker 2、`NO_PARTIAL_FOOTER` | 保留原始 manifest、summary、checker 与 outer record；不并入后续 E2 受控停止 |
| 原尺寸组件早期失败 | run `20261009T171009.169165Z`；`WORKER_FAILED / LOCAL_COMPONENT_GATE_FAILED`；约 1,199.55 s watchdog；任务 swap 0，descendants cleared | 后续部分组件记录不覆盖该失败 |
| full-component 工程 fixture 中断 | `INTERRUPTED_BY_CONTROLLER_SCOPE_CHANGE` / `ENGINEERING_ONLY_NO_FORMAL_GATES`；停止回执快照约 2 分钟和约 14 秒，均由控制器发出 SIGTERM；这不是独立计费时长 | 原 stop receipt 有 `campaign_window_charged=false` 字段，但它不是计费依据；固定 campaign window 包含这段时间，fixture 精确独立时长与费用为 UNKNOWN，不置零、不重复加账 |

前两次 E2 入口失败、早期组件失败和中断 fixture 都是独立记录。V20 没有覆盖旧费用、未知项或 run 分类；固定窗口仍绑定 `campaign_window_v19.json`，SHA-256 `b1591b7cf03b79aaf0820d352e636bdb79a6800bb19489eba92375cb73cbe6b0`。V19 sequence 55985 仅是当时的 as-of 快照；后续费用继续以共享 `campaign_accounting_v10.jsonl` 为准，由主控最终结算。

## 源码冻结、时钟与校验

主控在 `c319719433e99fe652754f2844c5d79669b111cb` 冻结原尺寸 runtime route 修复，父源码为 `4b004d09b17d07a1f19f4c9d8443e76153e69a4b`。修复只允许精确 profile tuple 通过只读 campaign 投影；heavy 目标授权仍为 false。路由与 ABI 定向套件为 **42 passed、1 skipped（0.58 s）**；target actual pre-mesh receipt 确认 `FE mesh=0、q CSR=0、factor=0`。没有因该路由补丁重跑科学算例。

E2 完整 user-service 父时钟由不重叠区间相加得到：monotonic **5,608.418476 s**，UTC **6,232.118781 s**，保守预算 **6,232.119266 s**。worker watchdog 子时钟单列：monotonic **5,605.714946 s**、UTC interval **6,229.415446 s**。它嵌套在 outer run_case 区间，不能再加到父时钟。两时钟差异 **623.700307 s**，原因未知，不猜测。

V19 旧成本记录中的 numeric factor elapsed sum 为 **223.134378 s**，只覆盖该记录所列的 28 次 numeric factor build。它不是完整的 factor build/probe 或冷启动总时长；conversion、cache-miss、eviction 与完整 cold path 均为 **UNKNOWN**，不把该子时间扩展解释或加到 V20 的父级时钟。

原尺寸 local/port 合并运行的同时进程树 RSS 峰值为 `665,841,664 B`，专用 cgroup memory peak 为 `700,948,480 B`，任务进程树/cgroup swap peak 均为 `0 B`；watchdog 完成后代清场。PSS=null，状态 `DISABLED_BY_PROFILE`。这些是合并运行峰值，没有拆分到 bottom/top；local-port receipt 的单类最大 unique backing 与带 alias 名数组 payload 均为 `34,260,316 B`，单独最大 owner 未汇总。

主控只读 campaign snapshot `benchmarks/artifacts/task40extra_0p7nm_engineering/local_v20_wsl/controller_closeout_campaign_snapshot.json` 的 SHA-256 为 `0dcd4752f762ac66516b954e64914fc09816a3a9ed92f37a2099507268c79de4`：tail sequence `83031`，tail cumulative `66,919.728418 s`，只读投影 `69,920.856944 s`，扣除 600 s closeout reserve 后暂余 `15,879.143056 s`。该快照未改 window 或 ledger，是 as-of 投影而非最终冻结余额；后续提交与等待仍占用固定窗口，需由主控最终结算。

最终文档合同 suite 的 ABI 预检、命令、日志与哈希登记在 [测试摘要](outcomes/test_summary.md) 和 [run index](outcomes/records/run_index.json)。full repository pytest、MPI4、Ruff 与 CI 未运行。本轮最终文档检查没有新启动 FE/PDE；此前已完成原尺寸局部/端口实测及 E2 四个 q CSR 与变换表装配，并在首个符号准入前受控停止。

详见 [V20 结果总账](outcomes/summary.md)、[目标阶段交接](outcomes/target_stage_handoff_v20.md)、四份 [V20 compact records](outcomes/records/) 与 [运行索引](outcomes/records/run_index.json)。主控负责最终文档审查、窗口结算及集中提交/推送。
