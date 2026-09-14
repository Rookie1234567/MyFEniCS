# Task041 review response v2

## 结论

本轮最终分类为 `RESOURCE_COMPARISON_INCONCLUSIVE`。13.5 nm 和 5 nm 的 exact/BAL_H 数值对照均通过；5 nm BAL_H worker 的自身残差和物理量也通过，但 public supervisor 父进程在 `2026-09-13T03:06:53.264Z` 附近、约早于结果落盘 34 小时丢失，candidate 的完整 public resource/exit authority 没有闭合。结果落盘后另有 orphan sampler 的终止竞态，故不能声称完整 workflow 内存节省或正常 MPI 退出。

H3 comparator 原始结果保持不变：

- `h3_final_comparison.json` SHA256=`7c3838fe565c10fac0b880b0fc2d7dce99f8cfcfef88d56e4f820df1f2f6a969`；
- `numerical_pass=true`、`comparison_contract_pass=true`；
- `consumer_resource_contract_pass=false`、`resource_contract_pass=false`；
- 原分类为 `TASK041_SIDE_BALH_NUMERICAL_OR_RESOURCE_FAIL`，命令 exit1；exit1 对应资源证据项 false，不是数值 Gate 失败。

H3h 的 base/review/source 身份为：base `50897c0c62d1f35abed5b196ae17997b2e7521cc`，review `7583acf85157770b027ef933f2a22cf4e435b807`，本轮准确 candidate source `51694bbc49d90e70eef87c953f07c695f5fc519c`。H2 exact/candidate 和 H3 exact/candidate 的 run root、输入、producer binding、artifact hash 均写在中心 report 和 compact record 中。

## 对 review §8 的回答

### 1. 方法和适用范围

BAL_H 用每侧一个准确 p4 粗因子和迭代平衡响应近似完整 p6 侧区逆，目的是减少 p6 因子驻留内存；它付出重复 Q/H6/A6、p4 回代和 Schur 列构造的时间。全局 Maxwell 方程、全局 action、RHS、P/PH 传递和正式 recovery 的定义不变。`inner=128/1e-2`、outer right FGMRES restart32、`max_it=2048`、true residual `5e-9` 是本轮冻结配置。

这只是 `research_only_approximate_candidate`。它没有被写入普通默认路径，也没有获得 production/master 合入批准。H4 只整理证据，不改变 solver、checker 或 runner 数值逻辑。

### 2. 数值结果

H2 13.5 nm 和 H3 5 nm 的两边自身五 residual、projection、traction、external-q、R/T/A/closure 均通过；H2 对照完整列出 80 channels，H3 对照完整列出 600 channels。H3 最大对照量仍远低于冻结门槛：selected E/H 相对 L2 最大 `2.297499717019377e-11`，四 canonical role 相对最大 `3.991963083778125e-10`，flux 相对 `5.876459704162639e-12`。H3 candidate 的 own `abs(A_balance-A_volume)=6.447059147096645e-7`、closure=`6.447059146541534e-7`（各自限值 `1e-5`）；pair 的 `ΔA_balance=6.317169010117141e-14`、`ΔA_volume=1.5467072067565368e-12`（对照限值 `1e-8`）。均未把 own 守恒误写成 pair 差值。

H3 candidate worker 为 `191662.819902868 s = 53.239672 h`，H3 exact consumer 为 `1868.4593736410607 s = 0.519016 h`，consumer wall 比约 `102.578×`；candidate Schur 为 `183016.74211002886 s = 50.837984 h`。candidate 五项 worker true residual（reported/global/bottom/modal/top）为 `4.779229557785769e-11 / 4.779530550208621e-11 / 6.242900074049634e-11 / 6.709147369393262e-13 / 4.427970644629166e-11`，projection 另为 `6.70932862848173e-13`。candidate 保留 p6 `0`、每侧 p4 `1`、每侧 nested KSP `1`，清理后均为 `0`。已有 H1 admission、P/PH、J/JH、Galerkin/凝聚 trace bridge 和 tiny inverse/particular evidence 支撑接线；这些是资格证据引用，不是另造 5 nm exact oracle。

弱 external channel 仍完整保留。H3 全部 600 行中的 26 行为 significant；significant amplitude/power relative 最大分别为 `4.740652e-9/9.243100e-9`。弱行的全量相对值较大只作诊断，不被丢弃，也不套用额外弱级 Gate。

### 3. 资源和生命周期

H2 consumer 资源合同通过；BAL_H consumer RSS 比 exact 低 `254894080 B`、约 `2.707606%`，但其 consumer wall 约慢 `7.68×`。这是同一已测 H2 对照的描述，不是跨模型或完整 workflow 的节省定论。

H3 exact 的完整 public-tree RSS/PSS/USS 为 `89123696640/87368944640/87121264640 B`。H3 BAL_H 旧 public 段观测 RSS 峰 `53221163008 B`，同时可读 PSS/USS 峰 `50485623808/50090246144 B`（226484 行中 2287 行可读、224196 行缺测）；该段 global used 的既有 baseline 为 `8192 B`，job swap=`0`，global used/pswpin/pswpout delta 均为 `0`，min MemAvailable=`2023682953216 B`。orphan 接管段峰 `53162483712 B`，二者各自有明确文件和时间范围，不能直接合成完整 candidate peak；candidate worker 的 rank-local `rss_drop` 也不能替代 MPI 全树释放。历史 producer 仅有 worker-tree `10039554048 B` 和 `11447.68326334795 s`，缺 public parent 采样，common workflow peak 为 unknown/unqualified。

三个 orphan record type 全在同一个 2GB `orphan_resource_samples.jsonl`（SHA=`eda1271c5eec3e90eb4b5d69b6d376c65355067c81a29038022f539713c59b7c`）：`sample=822`、`orphan_sample_read_only=6284`、`orphan_sample_gate_v2=442921`。最后 gate-v2 行 rank RSS 不可读并使 sampler gate false，但 job swap=`0`、global used 的既有 baseline=`8192 B`、新增 used/pswpin/pswpout delta 均为`0`，hard/reserve 未触发。结果落盘后实际发送了全部 9 个专属组 TERM，并对 rank0 组 KILL，最终无残留；这不等于正常 MPI 自然退出或全流程资源 pass。

### 4. 退出竞态与监控事故

public parent/outer wrapper 在 `2026-09-13T03:06:53.264Z` 附近消失，约早于结果落盘 34 小时；`run_summary.status=launching` 且最终 public exit 未验证。结果落盘之后，orphan sampler 末条 gate false，实际对全部 9 个专属组发送 TERM、对 rank0 组发送 KILL，最终无残留；这与父进程早期丢失是两个事件。authority、final cleanup marker、consumer summary 的 mtime 只能作为结果落盘与退出竞态的边界，不能冒充嵌入式样本时间。orphan notification 在 `notLoaded` 状态失败，后续人工通知送达。H3g 固定 PID sampler 与 incident artifacts 明确为 research incident、`do-not-merge`、`not qualified for reuse`。

H2 首次缺失 main-guard 的工程错误入口是 `/home/fenics/Projects/MyFEniCS/results/task041_side_balh_component_audit/h2_13p5nm_balh_20260912_cda7cc8a/h2_candidate_stdout.log` 及同目录 `h2_candidate_invocation.json`；对应 run directory 是 `/home/fenics/Projects/MyFEniCS/results/task041_13p5nm_balh_hybrid_iterative_p6h10_m120_mpi8/task041_13p5nm_p6h10_m120_mpi8_balh__hybrid_iterative__mpi8__M120/20260912T013022.784680Z`，该次 inner exit `0`、wrapper `3`、wall `3.523241758 s`，未产出 consumer/PDE。随后独立的 `/home/fenics/Projects/MyFEniCS/results/task041_13p5nm_balh_hybrid_iterative_p6h10_m120_mpi8/task041_13p5nm_p6h10_m120_mpi8_balh__hybrid_iterative__mpi8__M120/20260912T014006.920548Z` 是 BAL_H admission/MPC-space 工程失败，consumer 已进入 `top_construction_cleanup`。H3e `SETUP_COST_BLOCKED`、wrong-interpreter pytest exit139、沙箱/监控器启动错误均保留原始入口和分类；裸 pytest 的因果根因未完全确认，没有把工程失败重写为数值失败，也没有把 H3e 停止改成通过。用户后来授权的 H3f-C time override 只关闭本 candidate 的 cost/phase/batch 时间停止，不关闭内存、swap、身份、完整性或数值物理 Gate。

### 5. 可复现性和 artifact 边界

H3 legacy descriptor SHA=`175a2463e15e039ff4dec91eed6a1f011d8eca338e1d2cc98cd8e30e37d86c86`，selected manifest SHA=`306939dda3b70777204c11fbd65beac2db5dc0637bc9b6803f7794d0d7cbad2f`，external 600-key digest=`ba431ec6683f2123e53e8f9f3fb13fd35ae22a6a8f9c0ed2d85aa1f1cb15b04a`。candidate 的 E/H payload、4 canonical manifests/32 shards、8 checkpoint shards 均与各自 manifest/hash 一致；compact record 保留全量 80/600 external rows 以及 canonical 的比较指标、manifest/hash；实际 32 个 canonical coefficient shards 留在 ignored results，不塞入 compact。BAL_H 迁移依据的 Task39extra V5 donor 为 `094204b7281fe867744fe334e8753d2faebaf89b`，原始 solve source 为 `2bb6770ad00b35881558c576e7296e250656e571`，审核/结果证据 source 为 `4cbfadc4880c20aea775142168e6dd4e71870fda`。

H3h 已执行的简短复现命令（native activation 后）为：`python -m benchmarks.task041_side_balh_comparison --candidate /home/fenics/Projects/MyFEniCS/results/task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8/task041_5nm_p6h4_m480_mpi8_balh__hybrid_iterative__mpi8__M480/20260912T075551.700563Z --exact /home/fenics/Projects/MyFEniCS/results/task041_5nm_exact_side_hybrid_iterative_p6h4_m480_mpi8/task041_5nm_p6h4_m480_mpi8_exact__hybrid_iterative__mpi8__M480/20260912T045757.515452Z --output /home/fenics/Projects/MyFEniCS/results/task041_side_balh_component_audit/h3h_final_20260914_51694bbc/h3_final_comparison.json`。中心报告见 [side_balh_transfer_v1.md](outcomes/side_balh_transfer_v1.md)，compact 见 [task041_side_balh_transfer_v1.json](outcomes/records/task041_side_balh_transfer_v1.json)。

当前账本 `/home/fenics/Projects/MyFEniCS/results/task041_side_balh_component_audit/task041_compute_wall_ledger.json` 的 measured record sum/used scope=`203701.83937335422 s`，这是显式已登账记录的覆盖范围，不是所有未记录等待的完整批次墙钟；初始 `6000 s` 是 `derived_conservative_allowance`，不是数学上界。

### 6. 未运行和不作出的结论

`full3d_secondary`、H3/H4 的 5 nm 新 producer/QEP、全仓 pytest 和 CI 均 `not_run`。没有扫描旧 3 nm schema 来补证据，没有启动更短波长，也没有用 worker 局部内存下降推断完整 workflow 节省。没有足够证据声称 H3 legacy producer 的 public-parent 覆盖或共同 producer 的完整内存峰值。

## selective merge 结论

依赖组和合入边界已写入中心报告与 compact JSON：numerical/core、runner/watchdog、checker/benchmark、compact evidence/docs、research-only、do-not-merge 六组分离。本轮新增 BAL_H 数值组件和 Floquet empty-rank collective 修复；这些组件仍是显式 research opt-in，旧默认/exact 路径保持，未获 production/master 合入批准。

本响应不替代权威 review，不修改 task.md，也不宣称 H2/H3 之外的任务完成。
