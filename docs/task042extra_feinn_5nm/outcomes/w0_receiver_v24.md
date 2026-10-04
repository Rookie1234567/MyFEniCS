# W0 接收 V24：保留全部内部量的真实组件闭环

本轮推进原尺寸计算的第一道组件关。单元内的内部场先被准确消去，边界和端口上计算完后再完整恢复；这节省全局处理的对象，但必须证明没有遗漏内部载荷或端口影响。W0 用非零内部/端口载荷、真实有限元方向和周期映射验证这种等价性，完成全部科学数组和独立读回。它没有计算入射散射前向解。

| 范围 / 身份 | measured / derived / not_run |
| --- | --- |
| 规则同80组件 | λ0.7、φ5°、4×4×5/p6、q27/196面点、532完整端口；非原50×25×140nm缺口散射 |
| 完整 FE 空间 | 每cell882=450内部+432迹；全存储55950 / MPC后52992独立复量，内部36000、独立迹16992 |
| 全局物理 | double Floquet、原B/D/H、真实原局部张量与native方向；无新global p6 Maxwell CSR/factor、无PDE solve |
| 科学结果 | 955原数值门与4错误负控通过；制造态native1.00025e-15、恢复最坏1.50063e-12 |
| 保存 | 1619原件/3287字段、数值625046512B/文件625253744B，全部hash/字节读回通过 |
| 最终状态 | 数值 PASS、本接收批次 PASS_WITH_QUALIFICATIONS；初始进程优先级缺口保留，非production批准 |

## 实际路径和有界恢复

1. 原始一次 worker 在 `benchmarks/artifacts/task42extra/w0_receiver/w0` 保存全部原件；worker report hash固定为 `324d5962…`，未覆盖。
2. 原独立checker在soft1024因EMFILE失败，保存了真实失败及47.8775s成本。
3. saved-check启动前单核资源观察器自耗误判被定位；采用显式opt-in补偿自己实测CPU开销，保留两ticks安全量及原/调整忙率，其他worker/SMT排除不变。第一启动在数值前退出，未生成新FE。
4. soft2048仍被重复别名映射耗尽；新loader对3385次调用复用1619只读映射，原数学checker每次校验和原门不改。soft4096/hard1048576只作用自身检查器；第三次数学checker完整通过。
5. checker冻结并清場后，在pure2GiB监督中逐个关闭/重开所有原件，重算数值及file hash并fsync目录，复核133份原依赖字节。没有进行额外FE作用、factor或solve。

这不是恢复丢失状态，也没有用新文档HEAD替代实际源码。[逐次source/运行](records/run_index_v24.json)、[修复账](records/repair_log_v24.json)、[原门CSV](records/w0_metrics_v24.csv)、[读回](records/durable_readback_v24.json)。raw没有打压缩archive；本机fsync/reopen不是跨机存储、断电或dot后端资格。

## 源码、环境及资源

冻结主线 `d4b6ed6b6cb2a0431cb75bba9d8fc74dc9d9e382` 的133文件构成最小静态闭包，从已有canonical Git对象导出只读source cache，不进行clone/cherry-pick或维护另一套求解器。接收原worker source `1527e11582dde9038a35f3b819f47caf080ce9b3`，最终I/O checker/readback source `6eb24884c4443021150ce3d55fbf91a7395e21ee`，数学文件字节始终不变。

| 运行 / measured | wall s（嵌套不相加） | 同时树采样RSS B / swap B |
| --- | ---: | --- |
| 原FE worker | 3363.418657 | 2338578432 / 0 |
| 原W0整个父生命周期 | 3478.276792 | 2383208448 / 0 |
| 第二次EMFILE检查器树 | 71.808673 | 328142848 / 0 |
| 最后数学检查器树 | 142.490835 | 972025856 / 0 |
| 最后独立tmux父生命周期，含60s窗口 | 203.854294 | 972025856 / 0 |
| 本机逐成员读回 | 6.971519 | 105771008 / 0 |

独立已有native complex环境只读复用：Python3.12.13、PETSc3.25.6 complex128/int32、DOLFINx/Basix0.10.0、MPC0.10.5、MPICH5.0.1；与旧Task42extra FE ABI不混用，逐次ABI收据另绑hash。CPU-only/MPI1、数学线程1及3GiB组件/2GiB轻树、零swap、整机余量/384GiB邻增长均由原监督记录证明对应范围。native MPI有后台OS线程，但全部在自己的核上。

初始nice0/IO/终端宽亲和性的缺口没有删除或追认为PASS：现场只修改自己已验证PID/start/UID的进程，worker持续运行未重放；永久启动修复及最后checker的新原窗口均有证据。原采样不能证明连续内核峰或准备阶段全过程峰。局部450维LU及相应solve由原组件/独立checker调用并全计费；不宣传整批“没有任何因子或代数solve”。

## W1 接入契约与未验证项

W1需要已有冻结manifest：32060keys、36244923B、SHA256 `52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d`、ordered keys SHA256 `03c1965cc13d89b256ea61212a5baba9aa97ef7ec20d356b0a04f9d233e95dec`。[有限原址证据](records/next_input_and_handoff_v24.json)明确当前主机三个原路径/Git本体都缺失，已请求可读原件位置。Git中的30250B库存摘要和其他模型manifest不作替代，不重建AUTO。

有原件后仍须在有效接收合同内检 actual全key/RHS/H、真实材料/geometry、方向/MPC/内部恢复及原分母；V23 q60局部既有证据只绑定相同参数，不能授予全部模式PASS。W2另受dot C1c和主线后端前置约束，本轮没有复制它们的存储/PC。原尺寸求解、E/H/curl、六点、全部复通道及R/T/A/能量、h/p/mode精度和2TB/172800s合取均NOT_RUN/NOT_QUALIFIED。

旧NN训练仍暂停，M3600较好/Mfinal退化、所有失败/UNKNOWN、D0成本否决/D1未运行和旧费用不改；确定性W0工程闭环没有NN净增益。[一次回执](../response_v24.md)、[Gate](records/gate_decisions_v24.json)、[费用](records/resource_costs_v24.json)、[最小源码接收包](../../../benchmarks/cases/fresh_c1_receiver/README.md)。
