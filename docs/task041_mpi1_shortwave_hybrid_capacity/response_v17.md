# Task041 Review V15 执行回应：modal-row 新判据与 tiny FE 240 步终态

## 当前裁决

V15 将 PC 内部 modal-row 检查从“非零 RHS 按 RHS 自身做相对误差”统一改为按原 modal 行各组成项的未相消尺度计算分量后向误差。通俗地说，原 A 的 modal 行由 bottom/top 投影、约束项和输入 RHS 相加而成；现在检查误差相对于这些实际组成项的大小，避免只看相消后的很小 RHS，但最终解仍必须通过原 A 的完整残差门。本次 test347 真正构造的 tiny FE 已连续做完 240 次 PC apply，所有新 modal-row 检查均通过；原方程的独立残差仍高于 `5e-9`，因此该 tiny FE **未收敛**。这不是资源拒绝、脚手架失败或 V15 行门失败，也不能单凭这条曲线定性为停滞或已证实的 PC 实现缺陷。

| 项目 | 实际结果 | 结论与边界 |
|---|---|---|
| 本次 tiny FE | `test_task041_v13_real_fe_condensed_sides_build_same_fixed_b_ldu`；真实原 A 为 `2172×2172`；RIGHT FGMRES；requested restart 30、`max_it=240`、`rtol=5e-9`、`atol=0`、零初猜；PETSc reason `-3`、240/240 iterations | 本次获批预算用尽，未通过正 KSP reason 与原 A 残差断言；不等于证明模型不可解或 PC 数学错误 |
| 原 A 独立残差 | `‖Ax-f‖₂=0.29822161297582517`；`‖f‖₂=934946.4789603328`；relative `3.189718552739508e-7` | 原门 `5e-9`；实测为门限的约 `63.794×`，失败明确。RHS 在求解前后未变 |
| V15 modal-row 门 | attempted/successful/recorded 均240；序号连续8–247；240条同次记录、owner LU记录及行门均通过；独立重算 `max eta_inf=7.753508102198664e-14`，与记录最大差 `2.0194839173657902e-28` | 新门限 `1e-10`；不是完整原方程收敛门，也不能取代最终五项残差 |
| PETSc 报告曲线 | iteration 30/60/90/120/150/180/210/240 的 `rnorm`：144.8159 / 30.86116 / 13.89476 / 5.71560 / 2.76555 / 1.20295 / 0.606899 / 0.298222 | 数值持续下降；这是 PETSc monitor 报告范数，不是每步独立计算的真实残差。末端与独立 `Ax-f` 分子接近仅作一致性观察 |
| 60 步旧样本 | 独立 attempt `task041_v15_tiny_fe_serial_v15_row_schema_record_attempt_20261014T122009Z`；reason `-3`、60/60；独立 `Ax-f` relative `3.300847332920077e-5` | 该结果不与本次 240 步曲线合并；本次第60步 `rnorm` 与旧60步终点相同只记为数值一致 |
| 销毁后快照断言 | completion JSON 在数值断言前已写出；测试首先因 reason `-3` 失败，随后销毁后读取冻结快照的断言未执行 | 不称该项已通过；小现场及数值记录仍保存在本次 completion JSON |

V15 行门的实际量为 `d=w_modal-r_modal`，并按每行 bottom、top、constraint 与 `r_modal` 的组成项模长之和归一化；合同标识 `task041.v15.original_modal_row.terms_backward.v1`。原 A 矩阵乘法仍按实际实现执行并捕获本次三项，不从固定 B 或 Schur surrogate 代替原 A。固定 B 的作用是让 LDU 近似块与模态 Schur 构造保持同一预条件器近似的一致性；B 不是原方程算子 D 的精确逆。此实现级行检查本次通过，但原全局方程最终残差没有通过。

## 已通过的定向证据与分段边界

| 范围 | 实际证据 | 源码与判定边界 |
|---|---|---|
| 高精度公式 oracle 与同一固定 B 接线 | 084528Z serial attempt 中 `test_v15_original_modal_row_metrics_match_decimal_complex_oracle` 与 `test_v13_factory_passes_the_same_fixed_b_actions_to_modal_and_ldu` 两节点通过；同 attempt 第三个 builder selector 因捕获记录时序失败，整体结果为 `1 failed, 2 passed`，原 attempt 保留 | attempt SHA `1a33915fbce215039e5a2f83b3fbfb6e4e06fec8ea32d24cf5280ff3178ba2c8`；source map SHA `b263939b587577a8bda6a803dcb28aab11e746606124763e3313c95853871032`；该次 test350 SHA `2b0fb30cdfc10f3dc324dea6f19453cad0935959c30577d3b972e19e0eb343a8`。该失败后续作为 fixture 取证时序问题单独修正，不改数值门 |
| 合成 tiny builder / owner LU / RIGHT FGMRES | 095200Z 单 selector `test_v13_unmocked_builder_owner_lu_and_original_modal_row_math` 通过；小型合成 fixture 中 reason `2`、10次迭代，独立原 A `Ax-f` relative `2.895212452829667e-10` 低于 `5e-9` | attempt SHA `778a5594e18662fc470126d3451b59b7ba5b1e04d37e451fc5139907bbb9f391`；source map SHA `4c98c85efedb324bbae6a8110017d86434b963f46cc18f79906579647f52665b`；该结果是 test350 合成小例，不等于 test347 注册真实 FE |
| MPI2 writer/真实 builder 合同 | 110225Z 批次的 snapshot writer 与 builder 相关节点通过；第三个 owner-writer 节点因 fixture 对 owner/non-owner flag 断言不对称而失败。按授权修正 test350 fixture 后，112820Z 单独重跑该第三节点通过。三节点的通过覆盖跨两个 attempt，不能写成同一次全绿 MPI2 invocation | 110225Z attempt SHA `cfe233f6b9314be19dc449a9173092918f37f8b82df6ca2f7a4eac2d6f404bb6`、source map SHA `4c98c85efedb324bbae6a8110017d86434b963f46cc18f79906579647f52665b`；112820Z attempt SHA `01d1715adc1af74ed10d3ee475380bceac90a583e5a76b6bfca2f20c739714c7`、source map SHA `a1fdbb7164e89753e75767495cffdd2c640a903f38c9ca25d98a9255162f2231`。MPI 合并输出不能逐 rank 归属的摘要仍为 `not_persisted` |
| 注册 tiny 真实 FE，60 步 | 真实 FE 单 selector 在预算60步未通过：reason `-3`、原 A relative `3.300847332920077e-5` | completion SHA `20479fb31d40227a0d81ef8f2c2c8f7e334f482ad2007f07ae23a3234cd9fdfb`；该 attempt source map SHA `1112809b0eb987e0306cc2fff501e19ba72893fb79c59979253f58a2db8c6f20`；test347 运行字节 `0b7ada886e387dff2e6154a61e9de073809146d168ece94ef1bdba6f90e5e965` |
| 注册 tiny 真实 FE，本次240步 | 同一 test347、同 A/B/S_B/RHS 路径，预算从60改为获批240；完整数值见上表 | stdout SHA `9b93ffe62fb6d8f761ab1e9db6dd4290cdb2f0cfdf561e4f787c06dc0b6e7b6e`；pytest attempt SHA `8d483950f9d8e9f4e629b40e5c4ab85547727121fb1081e15c408536c816e2d5`；source map SHA `6de36431ff40ab856a676c649cc7908f0f5a766f974e8d79205582929f7befd3`；test347 SHA `30d15257d1b65871d6e77827f0ca05ca36754f4812887ec17888c332c952b067` |

前述公式、test350 合成 tiny 与 MPI2 测试证明的是行公式、固定 B 接线、owner/写入错误广播等受测路径。它们不能替代 test347 的真实 FE 外层方程验收。旧的 schema/fixture 失败 raw 也继续保留，既不改写为数值失败，也不与两次 FE 未收敛结果混为一类。

## 资源、计时和账目

| 项目 | 本次实际记录 | 解释 |
|---|---:|---|
| pytest parent monotonic wall | `471.35805576085113 s` | 本 attempt 唯一收费的测试父 wall；ABI 与 preflight 不计费 |
| resource authority peak 字段 | `973332480 B` | runner 的 process-tree/cgroup authority 口径，不是全主机 RSS |
| 运行配置 | CPU11；`system_default_unbound`；六个线程环境值均为1 | 本次 tiny serial，不资格化 MPI8 或正式服务 |
| V5 | 旧286项前缀逐条不变；287项；`charged_seconds=636119.0079768548 s`；SHA `54f0c0d524d1a584478dae6bb0f695e2c2a68be683fc82ba6a591c32c50a62d1` | 此账目汇总跨阶段研发/执行开销，不是本次 warm wall，也不把 producer/QEP 或 ABI重复计入 |

本阶段只运行上述一个 serial tiny FE selector；没有运行 producer、QEP、MPI 或正式 warm。`471.35805576085113 s` 是本次 pytest 父进程墙钟，producer/QEP既有阶段与本次测试各按自己的原始receipt计入V5，不把累计账目写成warm时长。

运行时与提交前执行分支 HEAD 为 `3d80e1876c29836dd292a33a283e45f079646b88`，protected stash `90e50393831cf8a9da6fe223ef8cae4d3cfa3976` 保持。运行时22路径 map SHA `6de36431ff40ab856a676c649cc7908f0f5a766f974e8d79205582929f7befd3`确认全部路径在 attempt 前后未变，其中 test347 是 `30d15257d1b65871d6e77827f0ca05ca36754f4812887ec17888c332c952b067`。该 map 含17条实现/测试源和5份文档；运行后更新了其中summary、test_summary、W0.7 outcome三份文档，另外17条实现/测试源及response_v14、response_v15两份历史文档仍与运行快照一致。提交前六个实现/测试文件仍为原有获批 dirty 文件，本阶段没有改它们；提交后live身份见最终报告及忽略目录提交收据。

当前 worktree 的 tiny 测试 runner 使用 kernel `MemAvailable` 合同；正式 warm 的 producer/authority/consumer/resource runner 尚未完成这一口径统一，不能把本次测试 runner 变更写成已覆盖生产 warm。

## 未完成项与需技术裁决的问题

| 事项 | 状态 |
|---|---|
| V15新一场正式 W0.7 M400/MPI8 warm、M400 五项最终原方程残差、recovery、EH、official R/T/A、A_volume、衍射及 physics | `not_run`；V14真实M400已完成S_B 800/800列及owner LU，随后原modal-row PC门失败，根因仍`UNCONFIRMED`。剩余大型额度的既有条件式授权未被撤销，但tiny完整收敛与生产内存合同前提尚未满足，当前不启动新M400 |
| V14大型构造额度 | 已用1/2；剩余1场保留此前条件授权，不是本记录新批额度；tiny完整收敛和生产内存合同前提未满足，当前不启动 |
| V14 首场 M400 outer modal-row 失败根因 | `UNCONFIRMED`；不得由本次 tiny 数据反推 |
| 停滞、PC 实现错误、原方程不可解 | 均未证实；本次只证明在获批240迭代预算内未过原方程门 |
| 下一步 ChatGPT 技术问题 | 是否另批同一 tiny、同 restart/PC/容差但更高的有限迭代预算；是否先检查 restart30 与固定 B/S_B 对外层收敛效率。两项都未获执行授权，也不是已经确认的修复 |
| 生产 `MemAvailable` 统一 | `not_implemented`；在任何正式 warm 前另行完成口径审查 |

本次 completion、独立复核、清场和账目证据入口见[轻量 V15 machine record](outcomes/records/task041_v15_tiny_fe_fgmres240_terminal_20261014.json)、[240步 completion JSON](../../results/task041_v15_tiny_fe_fgmres240_serial_attempt_20261014T125426Z/serial/pytest_basetemp/test_task041_v13_real_fe_conde0/v15-modal-evidence/tiny_fgmres_completion.json)、[独立 post-run review](../../results/task041_v15_tiny_fe_fgmres240_postrun_review_20261014T132641Z/independent_postrun_review.json)与[证据目录 selfseal](../../results/task041_v15_tiny_fe_fgmres240_postrun_review_20261014T132641Z/SHA256SUMS.sha256)。旧60步负结果与 V14 原始失败数据均保持独立，不回写、不合并。
