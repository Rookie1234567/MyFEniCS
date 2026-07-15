# Task033 高阶 Floquet、QEP 与 graded-h 走读

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

聚合器要求解析 beta 误差和 p2 相对改进，不能以“finite beta”作为 pass。MPI2/4 PEP 若在规定 wall time 内不返回，外部 watchdog 生成 timeout negative record；该结果是已测扩展限制，不可改写成跳过或成功。

## Hybrid 漏斗

`run_task033_memory_watchdog.py --target hybrid` 包装单个 Hybrid shard。它在启动前读取 resource matrix、clean SHA、container limit、host available 与 swap；运行时按 `max(live worker RSS sum, cgroup current)` 判 warning/termination。

每个新 degree 的 h5 anchor 运行 M80/M120/M160；若 M120--M160 不满足 R/T/A 和显著衍射级复振幅 Gate，再考虑 M240。`task033_hybrid_funnel.py` 拒绝单个 M80、dirty SHA、缺少外部 watchdog、缺少 diffraction order 或缺少物理字段的摘要。

小规模 augmented direct 只用于与 Modal-Schur 代数锚定；主求解路径保持 `modal-schur-memory-minimal`。p4 只有 Case090/QEP/trace 通过、资源预测安全且 p3 已显示收益时才会运行 Hybrid。

## graded-h 与 buffer

`task033_periodic_graded_mesh.py` 构造 fitted axis 和周期同步的 conforming 六面体计划。它支持 physics-informed marks、Dörfler selection、cell indicator rebuild、neighbor-ratio 检查和相同精度候选资格。

`run_task033_adaptive_mesh.py` 分别以 uniform p2/h5 和 p2/h3 为 reference。候选只有同时满足 R/T/A、显著 order、interface E/H Gate 后才计算 local DoF/rows/NNZ/RSS/time 压缩，未达到 3 倍不会被自动判失败。

四个 buffer 使用 10/110、7.5/112.5、5/115、2.5/117.5 nm 接口。比较时同时计入 local FEM、QEP/mode storage 和 interface/Schur；不能只按 local cells 排名。

## variable-p 与 1 TiB

`task033_variable_p_capability.py` 探测当前 DOLFINx/Basix 公开 API 和运行时，并逐项审计 cellwise degree、切向连续、periodic p 同步、trace 与 MPI ownership。没有原生可维护路径时 fail closed，不构造任意 bespoke variable-p。

`task033_one_tib_projection.py` 只在输入真实 measured compression 时更新 1 TiB 路线分类。没有实测压缩、单位或 baseline 时输出 not-run/fail-closed；它始终是 analytical projection，不是 PDE solver pass。

## 统一证据入口

最终只通过 `benchmarks/check_task033.py` 读取 Case090/091 manifest。正式模式要求：

- Case090 core 和 MPI memory；
- QEP study 与 MPI timeout negative；
- p1/p3 M funnels；
- uniform p/h matrix；
- graded h5/h3；
- 四个 buffers 与 trade-off；
- variable-p audit 与 1 TiB projection；
- 所有正式角色使用同一个 tracked-source-clean SHA。

规划模式只验证 schema 和 NOT_RUN 结构，不产生物理通过结论。

