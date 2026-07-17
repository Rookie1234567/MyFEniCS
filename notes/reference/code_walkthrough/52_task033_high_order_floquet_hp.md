# Task033 高阶 Floquet、QEP 与 graded-h 走读

> 阶段状态（2026-07-17）：Review V6 接受 Task33 reduced scope，F0 已完成。
> fixed-p p3/h7.5 为 clear success（有 reference 资格）；legacy p1/p2 negatives
> 保留，variable-p fail closed。graded-h/1 TiB 移交下一任务，buffer 等待目标几何；
> 其 prototype 不进入本次 master 能力合并。

## 调用链

```text
SimulationConfig3D(nedelec_degree=1..4)
-> build_double_floquet_mpc
   -> resolve qualified topological-trace mode
   -> build_high_order_constraint_data
      -> distributed entity records
      -> Basix edge/face transforms
      -> phase-independent topology cache
      -> sparse phase coefficients
-> common_3d_case_flow / Fixture A,B
-> Case090 shard + MPI/resource aggregate

cross_section_spaces
-> exact cross_section Floquet C
-> K0,K1,K2 with resolved quadrature
-> distributed PEP / classification / tracking
-> matched trace
-> Hybrid augmented or modal-schur-memory-minimal
-> M funnel + equal-accuracy comparison

physics-informed marks
-> periodic synchronization
-> conforming graded plan/rebuild
-> h5/h3 reference comparison
-> four-buffer joint-cost comparison
```

## 公共 p1--p4 Floquet 路径

`src/constraints/floquet_3d.py` 的 `auto` 对 p1--p4 都解析为资格化的 topological trace 后端，并调用 `src/constraints/floquet_3d_high_order.py::build_high_order_constraint_data`。p1/p2 的历史 gather 路径仍可用于私有诊断，但不会被公共 `auto` 选择，telemetry 也不会把它伪装成 distributed。

高阶后端先按 vertex/edge/face 几何 key 构造周期实体记录，再由 `distributed_match_periodic_records` 把记录发往稳定 pairing rank。它只返回需要的配对，不全量聚集整张周期边界。边和面的系数变换来自 `high_order_floquet_trace.py` 的 Basix entity transformations。

`FloquetTopologyCache` 保存相位无关 block。配置的 Floquet 相位变化时，MPC 只重算稀疏系数。结果 telemetry 包含 slave/master 数量、constraint NNZ、topology/phase time、通信 bytes、cache hit、full-boundary-gather 与 dense-square 禁止标志。

## Case090 记录

`benchmarks/run_task033_case090_pde_core.py` 每个 MPI1/2/4 shard 运行固定 48 个小案例：Fixture A 16 个、Fixture B 主验证 16 个和低角 smoke 16 个。正式 aggregate 需要同一完整 clean SHA。

记录同时提取：

- 解析场相对 E/H 误差；
- 平坦 air--Si 解析 Fresnel r/t 与数值零阶复振幅/相位；
- `A_red q` 与独立 `C^H A_full C q` action 误差；
- p/h 趋势与 p4 是否有额外收益；
- constraint、cache、communication 和 MPI 差异；
- 外部 watchdog 的 RSS/cgroup/swap/limit 资源权威。

原始 VTU、日志和 memory timeline 写入 `benchmarks/artifacts/cases/090/`；tracked Case090 只保存紧凑 schema、NOT_RUN/正式摘要和校验 hash。

## QEP 资格矩阵

`benchmarks/run_task033_qep_matrix.py` 生成 air、lossy homogeneous 与 patterned Stage4 截面 shard。`task033_qep_measurement.py` 提取 beta、QEP residual、biorthogonality、tracking、full/reduced DoF/NNZ、quadrature 和时间；`task033_qep_qualification.py` 聚合同一 clean SHA 的 p1--p4 与 h5/h3/h2.5 矩阵。

聚合器要求解析 beta 误差和 p2 相对改进，不能以“finite beta”作为 pass。Phase A
以公共 Fourier fingerprints 的近简并块 principal-angle tracking 资格化 p3/p4；
legacy p1–p4 aggregate 仍保留 p1/p2 真实负结果。MPI2/4 PEP 若在规定 wall time 内
不返回，外部 watchdog 生成 timeout negative record；该结果不可改写成跳过或成功。

## Phase B matching trace

`benchmarks/run_task033_matched_trace.py` 在 `h10` matching-interface fixture 上执行一条
p2/MPI1 回归和 p3/p4 的 MPI1/MPI4 记录。3D 六面体 N1curl 与 2D 四边形 N1curl
使用相同 degree，并记录 Basix entity/trace DoF、matching mesh hash、bottom/top
normal convention、point ownership 和 ghost/scatter 行为。

`ModalTraceProjection` 只新增可选 `quadrature_degree`；普通默认调用不变。Phase B
显式比较 `2p+4` 与 `2p+6` 的稀疏 trace mass、`2×2` Gram、右重构、左 Petrov
projection 和 coefficient round-trip。切向值通信只传两个 complex128 分量，不 gather
3D 场或模态向量，也不形成 dense interface square。

`task033_matched_trace_qualification.py` 不信任 shard 自报状态。它逐条复算数值、空间、
积分、MPI 和存储 Gate，并以网格/DoF/NNZ、beta assignment、Gram condition/奇异值和
近简并块结构比较 MPI1/MPI4。p3 与 p4 判定链分开，p4 失败不会阻塞 p3。tracked
`phaseB_summary.json` 保存原始 ignored shard 的文件 SHA256 与 compact observed data。

## Hybrid 漏斗

`run_task033_memory_watchdog.py --target hybrid` 包装单个 Hybrid shard。它在启动前读取 resource matrix、clean SHA、container limit、host available 与 swap；运行时按 `max(live worker RSS sum, cgroup current)` 判 warning/termination。

每个新 degree 的 h5 anchor 运行 M80/M120/M160；若 M120--M160 不满足 R/T/A 和显著衍射级复振幅 Gate，再考虑 M240。`task033_hybrid_funnel.py` 拒绝单个 M80、dirty SHA、缺少外部 watchdog、缺少 diffraction order 或缺少物理字段的摘要。

小规模 augmented direct 只用于与 Modal-Schur 代数锚定；主求解路径保持 `modal-schur-memory-minimal`。p4 只有 Case090/QEP/trace 通过、资源预测安全且 p3 已显示收益时才会运行 Hybrid。

Phase C 的历史 C0 曾阻止 p3/h5 full3D；后续用户授权的受控 direct 以
7.781 GiB 完成，同阶 Hybrid 2.618 GiB 并通过 16 项 closure Gate。因此历史
`phaseC_summary.json` 已明确 superseded，当前 p3/h5 由
`full3d_closure_summary.json` 管理。

Review V6 最终版 `task033_reduced_equal_accuracy.py` 只聚合 p2/h3 baseline、
p3/h10 和条件 p3/h7.5。它同时复算 scalar、plane/interface field、diffraction
order、residual、M convergence 与六类资源指标，并绑定 raw SHA256。它还核对
image/digest/MPI4/zero-swap/solver/memory authority/source split，并把 wall time
限定为 indicative。结果为 p3/h10 accuracy negative、p3/h7.5 fixed-p clear success。

## graded-h 与 buffer（未合入的 research prototype）

`task033_periodic_graded_mesh.py` 构造 fitted axis 和周期同步的 conforming 六面体计划。它支持 physics-informed marks、Dörfler selection、cell indicator rebuild、neighbor-ratio 检查和相同精度候选资格。

`run_task033_adaptive_mesh.py` 分别以 uniform p2/h5 和 p2/h3 为 reference。候选只有同时满足 R/T/A、显著 order、interface E/H Gate 后才计算 local DoF/rows/NNZ/RSS/time 压缩，未达到 3 倍不会被自动判失败。

这些文件只存在于 Task33 research branch；Review V6 的 selective merge 排除 runner、
graded mesh 模块和 prototype tests。下一 adaptive task 必须重新审计后才能进入 master。

四个 buffer 使用 10/110、7.5/112.5、5/115、2.5/117.5 nm 接口。比较时同时计入 local FEM、QEP/mode storage 和 interface/Schur；不能只按 local cells 排名。

## variable-p 与 1 TiB

`task033_variable_p_capability.py` 已在 DOLFINx 0.10.0.post2 / Basix 0.10.0
运行时执行。mixed element、submesh 和 mixed-topology API 的存在不能证明
cellwise unequal-p H(curl) 语义；审计因此 fail closed，不构造 bespoke variable-p，
也没有触发 microfixture。

`task033_one_tib_projection.py` 是 research branch 历史规划器，不合入本次 master。
没有实测压缩、单位、baseline 和高阶模型重校准时，1 TiB 仍为 not qualified。

## 双层证据入口

当前 accepted reduced scope 使用
`benchmarks.run_task033_reduced_scope_completion --verify`。它 hash-bind Stage1、
QEP/tracking、Phase B、p3 closure、p4 negative、D1/D2、source audits、测试摘要和
exact merge manifest，并明确 `original_task033_full_scope_complete=false`。

历史 `benchmarks/check_task033.py` 继续读取原 full-scope Case090/091 manifest。
其正式模式要求：

- Case090 core 和 MPI memory；
- QEP study 与 MPI timeout negative；
- p1/p3 M funnels；
- uniform p/h matrix；
- graded h5/h3；
- 四个 buffers 与 trade-off；
- variable-p audit 与 1 TiB projection；
- 所有正式角色使用同一个 tracked-source-clean SHA。

规划模式只验证 schema 和 NOT_RUN 结构，不产生物理通过结论。
