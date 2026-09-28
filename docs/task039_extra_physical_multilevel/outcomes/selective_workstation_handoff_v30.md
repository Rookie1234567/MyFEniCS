# V30 选择性交接清单：工作站尚未迁移

本清单说明哪些笔记本成果可供后续独立 review，哪些内容已被证据否定或仍缺工作站身份核对。它是移交说明，不改变工作站工作树、不授权迁移或启动工作站 PDE，也不授权 master merge。V30 的单机 PASS 不等于跨 ABI、不同端口数或不同几何的资格。

## 三类工作与最小依赖

| 依赖组 | 文件范围 | 数值行为 / 已有证据 | 建议顺序与限制 |
|---|---|---|---|
| 已有笔记本成果 V26–V29 | 保留原版本代码、profile、a4_tensor_h6_v29.md、各自 compact/checker 和 response_v30.md；V29 同离散场是 V30 对照分母 | 包含既有双层凝聚、完整 A4、p6 tensor、外层迭代与候选收口；本批没有重新宣称这些旧结果 | 作为历史基线引用，不把整段历史分支或全部文件复制进工作站；先按目标 ABI 和接口逐个 diff |
| V30 本机通过、供 review 的 explicit profile | 核心候选：src/solvers/fullspace_metric_positive_diagonal.py、src/solvers/p6_cell_condensed_action.py、src/solvers/p4_cell_condensed_inverse.py、src/solvers/physical_interface_balanced.py、src/solvers/physical_light_setup.py、src/runners/physical_p4_schur_v14.py、src/runners/physical_dual_cell_condensed_lowmem_v20.py、src/io/physical_intermediate_profile.py；接线依赖：scripts/run_case.py、src/io/input_schema.py、src/io/input_validation.py、src/runners/task038_full3d_iterative.py、src/runners/task038_launcher.py、benchmarks/subreaper_watchdog.py、benchmarks/task038_full3d_jit_staging.py | 参考能量实际 affine metric 对角差 7.13e-16、H6 apply 差 8.11e-16、power10 max 差 9.34e-16；V30 一场残差及离线场/物理对照通过。代码和 dat 有显式 profile dispatch；这些证据只覆盖本机 MPI1/int32、990 cells、80 modes 的身份 | 先审最小核心数据流，再审 runner/profile/watchdog，再审记录与 tests。逐文件迁移时保留显式 opt-in；不得将其设为普通默认。输入 input/task39extra/v30_workstation_guided_original_h7p5.dat 仅供对照，不直接移用于工作站 |
| research-only / do-not-migrate | src/test/test_task39extra_v30_*.py 和关联 diagnostics；docs/task039_extra_physical_multilevel/outcomes/records/workstation_guided_local_v30_l*.json；L3/L4 临时配对 runner（若在分支中） | L3 候选虽等价，真实配对慢约 14.66%，完整 C 未测；L4 streaming apply 慢 65.48%、三操作总时间慢 3.129%，只省约 1.8 MB 唯一 payload；geometry cache 键数不是物理形状数。H6 pre-move 无合格唯一 owner 路径。约 600 行 full-C probe 已移除，full C 结论为 UNKNOWN_NOT_MEASURED | 不提升为 production default，不为保存代码而迁移被撤回候选。保留测试和小型结果供 review；ignored 的场、矩阵、factor、cache、timeline 不进入 Git 或移交包 |
| compact evidence / docs | response_v31.md、outcomes/workstation_guided_local_v30.md、本 handoff、outcomes/summary.md、outcomes/test_summary.md、outcomes/records/workstation_guided_local_v30_{components,monitor_policy,selection,compact,checker}.json、outcomes/records/run_index.json、docs/development_progress.md、docs/development_model_registry.md | 指向同一 source/input/geometry/mode identities；旧 V25 checker 的 backend_identity FAIL、PSS unknown 和 observe-only swap 限制均保留 | 最后按审核过的源文件和依赖组随分支提交；不能通过文档或 compact record替代工作站 fresh evidence |

## 接口和身份核对

| 项目 | 本机 V30 已确认 | 工作站迁移前必须从其当前权威 manifest 复核 |
|---|---|---|
| PETSc scalar/index ABI | 本场使用资格化 WSL/Linux 栈；本机 PETSc complex128、IntType=int32 | Review 指定关注 int64/PORD64 兼容。实际 PETSc.IntType、MUMPS/PORD64 build、MPI ABI、库路径必须读取工作站当期预检；不能将本机 int32 测试等同于工作站 int64/PORD64 资格 |
| 模式与端口 | 80 个有序 DtN modes、78 个 propagating；有序 key SHA dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2 | 从目标当前 input/resolved config 重新导出完整有序 key 列表、端口数、传播分类、排序与归一化。目标值在本次交付副本中未重新读取，登记为 NOT_REVALIDATED，不假定等于 80 |
| 几何和网格 | entity SHA 539460eec567dd89bb75cab8c72926c337be40fc5cfab54765f56117ee0ae5ba；axis-plan SHA b5bab6aae4668be60aacbb49265b4c875def42e2620256cd168d8c26207dc157；990 cells [9,5,22] | 逐项核对工作站 target geometry/entity/material/axis-plan hashes、周期边界、真实 cell 数和局部方向；工作站当前身份未在本批重新读取，登记 NOT_REVALIDATED。禁止用本机 84/124 个缓存键推断目标几何类数 |
| 方程与收敛合同 | 13.5 nm original，1° grazing，azimuth 0、s 偏振；最终完整显式残差门 1e-6 | 对照工作站当前正式 task/input/review，确认波长/几何/边界/材料/加载、MUMPS 设置、KSP/PC 与残差算法逐字段兼容 |

Review V28 提到的工作站旧记录中，MUMPS internal used 约 916.7 GB 是历史工作站因子统计，不是 V30 新测值，也不代表全局因子扩展问题已解决。V30 没有改动工作站 source/process。

## 获得单独授权后的 5 nm → 2 nm 资格步骤

1. 先只读确认工作站当前 branch/source SHA、approved input/task、PETSc/MPI ABI、PORD64、端口 ordered keys 和 geometry identity；记录所有差异，并在任何 PDE 前完成环境 gate。
2. 只迁移经 review 批准的最小依赖组；按工作站实际整数宽度重跑相关 pure/FE/MPI targeted tests。若 index width、mode key、方向或几何身份不能逐项闭合，停止在工程 gate，不启动 PDE。
3. 在单独授权的 5 nm anchor 上做一次分级 preflight/assembly/factor/full solve；完整记录真残差、官方物理量、完整 observable vector、stage wall/resource、进程树和 scratch。资源控制停止只记为 controlled stop，不重试到通过。
4. 只有 5 nm 数值和资源 Gate 全过且当前授权覆盖 2 nm 时才进入 2 nm；沿用同一核对表并重新计算预测容量，不能把 5 nm 的时间/内存线性外推当作 2 nm 通过。
5. 0.7 nm、普通默认提升及 master merge 都不在本交接授权内。当前状态是笔记本结果等待主控 review，工作站迁移 NOT_STARTED。
