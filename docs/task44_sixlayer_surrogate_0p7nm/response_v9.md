# Task44 Response v9：B9–B12 收口与离线文件核验

## 当前结论与范围

本轮只核对既有输出、监控记录、求解器阶段计时，并整理文档。没有启动 PDE、没有新增 GP 评估，也没有重跑既有测试。精度额度已用完 `12/12`。B9–B11 是监控受控停止，B12 是唯一完整的 boundary-plane 数值对照；原始失败证据均保留。A–D 仍为 `gp_eligible=false`，因为 y 与顶部空气稳定性对照超限；z 方向单独通过不能覆盖这些问题。历史 DtN 倏逝壳层运行真残差失败，故截断稳定性没有得到证明。用户本轮明确取消继续扩展该壳层，这不再是待办复算；拟议的后续代理范围须披露固定 160 个 DtN 模态。

| 尝试 | service wall | 进程树 RSS / cgroup peak | 分类与首因 |
|---|---:|---:|---|
| B9 | `3688.507526768837 s` | `7,955,501,056 / 8,586,076,160 B` | `MONITORING_FAILED / not_run`。两次外层 owned-member 快照均含同一 PID/start 的 `cc1`，内层 membership 结果为 false，触发旧监控拒绝。内层 listing/syscall 时序未保存，具体竞态机制未证实；无 full residual 或 official R/T/A。 |
| B10 | `922.6288379072212 s` | `5,034,360,832 / 5,278,961,664 B` | `MONITORING_FAILED / not_run`。PID/start、cgroup 和 affinity 稳定，PPID 变化触发旧 frozen-parent 检查；无 full residual 或 official R/T/A。 |
| B11 | `619.4444286893122 s` | `4,894,605,312 / 5,288,202,240 B` | `MONITORING_FAILED / not_run`。首因是一次 `systemctl list-units` 错误；随后独立的 `systemctl show` 也报错。最终回执确认 Task44 子树已清空；无数值结果。 |
| B12 | `2806.5004601851106 s` | `7,891,423,232 / 8,588,120,064 B` | `official_result=true`；MPI1、swap `0 B`，完整显式残差和能量闭合均通过。 |

B9、B10、B11 均因旧监控/服务查询 Gate 停止，不是 Maxwell 离散或 MUMPS 数值失败。B9 已知证据是两次外层 owned-member 快照都列出同一 PID/start `cc1`，内层 membership 却为 false；内层 listing/syscall 时间没有保存，因此不能把具体 race 机制写成已确认根因。B10 的 PID/start、cgroup、affinity 稳定，PPID 改变触发了旧 frozen-parent 检查。B11 记录了一次 `list-units` 错误和随后独立的一次 `show` 错误，不是两次 `list-units`。service summaries 位于 `benchmarks/artifacts/task44_native_services/task44-sample-boundary-plane-b{9,10,11}-r1-20261101.service/`。它们的 service-summary SHA-256 依次为 `5e3a4efd491b52e8b76c1dbfe2c00f58803ef847fddc26b8491c4d3adeee5d66`、`1bd1d65be2fae519653d1eb39d1318bcdf3fb974dbdf57fdfca1d1eef0e64122`、`f0209038d799aac64f03e1c551deacfb435ee23276f09a0f92d4bb75dda1336e`。

B12 pre-admission r1 的 CPU selector 读取 PID 298254 失败，后续观察时该进程已不存在；没有捕获可用的 start ticks/errno，且没有启动 systemd service。r2 未找到两段忙度都严格低于 20% 的可用 CPU，也没有启动 service。两者均无 PDE 或结果目录，不计入资格 attempt；原始记录为 `/tmp/task44_b12_admission_failures_20261101.json`，SHA-256 `7cd601366509671c088e260b6913dcb59fb6973b0ad6d3d96ae713c2c4cf62aa`。

## 批准后的运行期 CPU 监控规则

批准的监控修复提交为 `9fc3728f73068ddc703f576b1ed8ce2bb10afc30` 和 `95087dae26822c8c989b9653b4580d18f03f8b0e`。正式运行时，外部 claimant 的 PID/start ticks 构成身份键；PPID/comm 变化及外部生命周期信息不可读只记录为诊断和性能隔离信息，设置 `performance_not_isolated=true` 后继续。运行期全用户 `list-units` 查询失败可容忍，但精确 owned Task44 unit 身份仍须核验通过；启动期 inventory 继续严格检查。Task44 自身 unit/Invocation、主 PID/start ticks、直接成员关系、cgroup、affinity、内存和 swap 硬门仍 fail-closed。

## B12 数值身份与正式结果

B12 RUN 位于：

`results/task44_boundary_plane_attempt12/task44_sixlayer_0p7nm/sample_B_boundary_plane_20261101_attempt12__full3d_direct__mpi1__Mna/20261101T110836.357672Z/`

| 身份或规模 | 值 |
|---|---|
| source SHA | `dab67e47cc1feb7da1bc1018cae66e1d18b93ff5` |
| input SHA-256 | `7c96752bd34cba4c33562e761b93854e92b989fd63952a3fa5c1c33d84e6a643` |
| physical-model SHA-256 | `d97fe809c536ba0c73439cef4da855c636dc41b8fc3805a95a9e81d21678b131` |
| resolved-config SHA-256 | `2a0e38709530ecb584f7b6510de1f3967a8c66e9702b6695e64a2272ac4b098c` |
| 方法 / 网格 | `full3d_direct`；P6、`[3,6,8]`、144 hex、MPI1、线程1 |
| 完整自由度 / 活动迹行 / DtN auxiliary 行 | `99,894 / 29,808 / 160`（上下各 80） |
| 凝聚矩阵 | `24,315,568` used NNZ；边界参考面 gauge `boundary_plane`，`z_bottom=-0.5 nm`、`z_top=5.0 nm` |
| service | `task44-sample-boundary-plane-b12-r3-20261101.service`，Invocation `7f7b6407725d44188e3068d53b64cedf`；完成、exit 0、后代清理通过 |

| 正式量 | B12 measured | 判定 |
|---|---:|---|
| full explicit true residual（relative） | `8.169724140477284e-10` | 限值 `1e-6`，pass |
| `R_total` / `T_total` | `0.09521909449777169` / `0.8831311299149318` | 完整传播 DtN 端口功率 |
| `R00_s` / `R00_p` / `R00_total` | `0.09521864873059795` / `1.0432294028174373e-23` / `0.09521864873059795` | 零级反射 S/P 分量与总和 |
| `A_balance` / `A_volume_total` | `0.021649775587296527` / `0.021649774816315158` | 端口吸收与材料体吸收相符 |
| `R+T+A_volume−1` | `−7.709813898415518e-10` | 限值 `1e-5`，pass |

相对已有 B `global_z` 结果，B12 的 `R_total/T_total/R00_total` 有符号差分别约 `+2.42119e-12/+7.654e-12/+2.42085e-12`。这是 B 点、这组网格与输入下的数值锚点，只能支持该点的两种端口相位坐标输出相符；不推广为跨网格、跨厚度或全源码等价。

## 场文件离线核验

`airbox_fields_3d_scientific.npz` 可完整读取：685,195 B，SHA-256 `cbb0f0acaf8d22bce73a698e146a166de45508a7670c048fa874fef328c2b494`。坐标数组为 `(3888,3) float64`；144 个六面体的 VTK connectivity、type 与标签长度相符；`E_total_code`、`E_total_V_per_m`、`H_curl_A_per_m`、入射 E 都是 `(3888,3) complex128`，Poynting 是 `(3888,3) float64`，标签、mask 等维度与 mesh 一致，所有数值数组均为有限值。元数据报告 `boundary_plane`、参考面 `[-0.5,5.0] nm`、MPI1、144 cells、3888 points。

NPZ 文件本身不含 source SHA 或 input SHA。身份绑定来自唯一 RUN 目录：其相邻 `run_manifest.json`、`run_summary.json`、`resolved_config.json`、`input_original.dat` 与独立 NPZ hash 对应同一 run；因此这里是外部 manifest + 文件 hash 绑定，不能称为 NPZ 自包含 provenance。

E/H `.bp` 已确认目录和成员存在并记录 hash，但当前未解码：

| 文件集 | tree SHA-256 | `data.0` SHA-256 | 可确认状态 |
|---|---|---|---|
| `E_3d_numerical.bp` | `efc9e6cae3b02684d64ea0cdcd8bb632d84513d7c272c4d99b3fa9eed3b2ca89` | `a260a90fdc12df68e5874137628f1ead43c3814bbb87969b64d14b85871ad01a` | 存在、hash 固定；数组读取 pending |
| `H_3d_A_per_m_from_curl.bp` | `20e823ff63e4b564c36b97fdc8315e062d52d5e13fb2ef69e74c7648cb32bde8` | `372060bfc65f8b0387ed0dbc463d2829e9cbce1c89cf49a3f3a835a503557e9f` | 存在、hash 固定；数组读取 pending |

本机没有 ADIOS2 Python reader 或 `bpls`；临时 C++ reader 缺少 `ADIOSConfig.h` 无法编译。故 BP 的 shape 与有限性仍是 `pending`，不把存在和 hash 写成 scientific readback pass。本轮不装包、不改环境、不扩建 reader。

## `global_z` 分支的范围限定静态核查

已有 y12 run 的 source SHA 为 `5a89ca1652fbe721f4d0ecf8cef9fc7ea276d92a`；air1 run 的 source SHA 为 `a2009b1268c314fcceb9df33d38dad9b217410a1`；当前 B12 source 是 `dab67e47cc1feb7da1bc1018cae66e1d18b93ff5`。这是三个不同的完整 source identity，不能概括为“源码相同”。只对决定参考面相位的窄路径作静态比较：

| 代码点 | 旧 y12 / air1 行为 | 当前 `dab67e…` 中的行为 | 证据边界 |
|---|---|---|---|
| `src/common/config_3d.py:115-118::SimulationConfig3D.dtn_phase_gauge`、`src/io/input_schema.py:837-848` 与 `src/io/input_validation.py:2992-3028` | 两个旧 source 都未暴露可选 gauge 配置；历史路径使用 global-z 坐标 | 新字段默认值为 `global_z`；validation 只对显式 `boundary_plane` 执行 3D/direct/MPI1/air1/fixed-p 限定 | 证明当前默认选择和 plane 分支范围，不是所有输入和所有 source 等价 |
| `src/solvers/dtn_port_3d.py::_mode_projection_from_solution` | 两个旧 source 在旧函数约 2124–2158 行都以全局 `x[2]` 构造相位，并用 `_mode_projection_denominator(mode,cfg)` | 当前 `2232-2285` 行的 `global_z` 分支仍取 `x[2]` 并走原分母；仅 `boundary_plane` 使用局部平面坐标和新分母 | 仅这个投影函数分支的源码比较 |
| `_incident_projection_onto_top_mode` 与 auxiliary assembly | 两个旧 source 的函数约 2061–2074 行都使用 `exp(1j*(cfg.kz-mode.k_vector[2])*cfg.physical_z_max)`；旧 assembly 约 4904–4905 行使用历史分母与入射投影函数 | 当前 incident 函数在 `2117-2129`；`global_z` assembly 在 `5082-5091` 仍调用 `_mode_projection_denominator` 和 `_incident_projection_onto_top_mode`。`boundary_reference_z` 在 `4870-4873` 对 global-z 返回 `None` | 检查 incident/auxiliary 参考坐标分支，不覆盖整个 weak form 或其他源文件 |

当前源码对应的最小分支证据（`src/solvers/dtn_port_3d.py:2254-2258, 2280-2284, 4870-4873, 5082-5091`）为：

```python
phase_z = (
    x[2] - PETSc.ScalarType(port_plane_z(mode, cfg))
    if dtn_phase_gauge == BOUNDARY_PLANE
    else x[2]
)
denominator = (
    assembly_projection_denominator(mode, cfg, dtn_phase_gauge)
    if dtn_phase_gauge == BOUNDARY_PLANE
    else _mode_projection_denominator(mode, cfg)
)
incident_projection = (
    incident_projection_in_solver_coordinates(mode, cfg, dtn_phase_gauge)
    if dtn_phase_gauge == BOUNDARY_PLANE
    else _incident_projection_onto_top_mode(mode, cfg)
)
```

旧 y12 源和旧 air1 源的对应最小读回分别是 `src/solvers/dtn_port_3d.py:2124-2158, 4904-4905`（y12 SHA `5a89ca1652fbe721f4d0ecf8cef9fc7ea276d92a`；air1 SHA `a2009b1268c314fcceb9df33d38dad9b217410a1`）：相位积分直接使用 `x[2]`，投影分母调用 `_mode_projection_denominator`，incident 通过 `_incident_projection_onto_top_mode`。这只说明所核查的 `global_z` 分支延续了这些公式；增加的 gauge 分支、诊断快照、输出语义、监控和缓存改动都仍在完整 source diff 中。

从 `5a89ca1652fbe721f4d0ecf8cef9fc7ea276d92a` 到 `dab67e47cc1feb7da1bc1018cae66e1d18b93ff5` 的整体源码 diff 还包括 gauge 支持、结果语义、snapshot 诊断和多处监控/缓存变化；本核查不宣称整体源码等价。B12 的 measured 对比只为上文 B 锚点提供数值证据，不能替代上述窄范围静态证明，也不能证明 y-refined 或 air1 旧结果等同于当前 source 重跑。

## 缓存字段、组装成本与两场额度提案

下表只读了已存在的 `run_summary.json` 和 service summary。worker elapsed 是计算 runner 时间；service wall 包括 service 生命周期；DtN 阶段字段彼此嵌套/部分重叠，不能把它们加到总时间或相互相加。三场记录的 `floquet_topology_cache_hit=false`、`stage4_dtn_component_vector_cache_hits=80`。前者说明拓扑对象未命中 warm cache，后者是单场内部向量缓存命中数；它们不是跨样本 FFCx JIT 加速证据。每个 service 使用独立 JIT cache root，因此估算不计共享 warm-cache 收益。

| 已运行校准点 | worker / service wall | cgroup peak | `stage4_dtn_assembly_time_total_build_seconds` | `stage4_dtn_port_assembly_and_solve` |
|---|---:|---:|---:|---:|
| y12 `[3,12,8]`，288 cells | `3347.793 / 3417.755 s` | `13,289,373,696 B` | `2851.534 s` | `3313.561 s` |
| air1 `[3,6,9]`，162 cells | `1877.662 / 1944.634 s` | `9,228,845,056 B` | `1453.377 s` | `1842.700 s` |
| B12 `[3,6,8]`，144 cells | `2727.063 / 2806.500 s` | `8,588,120,064 B` | `2122.621 s` | `2684.826 s` |

**拟申请的最小新增额度：两场；本次没有授权或启动它们。** 固定 B 的六层厚度 `0.75 nm × 6`、材料与入射参数、P6、160 个 DtN 模态（每侧 80）、`global_z`、装配期静态凝聚、MUMPS exact、MPI1/线程1、x 方向 3 段、底面 `z=-0.5 nm`。运行前每场仍需 fresh ABI、CPU claimant、宿主/祖先 cgroup 和零 swap admission，service cap 128 GiB。

| 候选 | 只改变的输入 | 网格 / cells | 比较对象与能回答的问题 |
|---|---|---:|---|
| y 加密 | y 段数 `12→24`；保持 z 段数 8、空气 0.5 nm、top `z=5.0 nm` | `[3,24,8]` / 576 | 与现有 y12、air0.5 `[3,12,8]` 比较 y 方向离散敏感性。只作这两档离散比较，不拟合收敛阶。 |
| 顶部空气扩展 | 空气 `0.5→1.0 nm`、top `5.0→5.5 nm`，增加一个顶部 z 单元；y 保持12 | `[3,12,9]` / 324 | 与现有 y12、air0.5 `[3,12,8]` 比较。它同时改变空气高度和 z 单元数，是配对的“空气延伸 + 顶部网格延伸”检查，不能解释成纯空气主效应。 |

每场先要求 full explicit true residual `≤1e-6`、能量闭合 `≤1e-5`。二者都通过后，再按完整 observable vector 检查 `R_total`、`T_total`、`R00_total` 对对应 air0.5/y12 基线的绝对变化均 `≤2e-4`。任一 solve/closure gate 失败就不读入 official R/T/A；稳定性失败则保留负记录并停止该方向扩展。即使两场都通过，也只形成 B 单点、y12 候选配置在所测方向上的工程稳定性证据，不自动使旧粗网格 A/C/D 达到 `gp_eligible`，也不证明连续收敛或 DtN 模态截断收敛。该两场方案固定 160 个 DtN 模态；若后续代理工作获批，适用范围须据实披露。用户已取消继续扩展 DtN 壳层，不把它暗示为后续必做步骤。

| 候选 | 服务时间预测 | 预测内存（cgroup 口径） |
|---|---:|---:|
| y24 | 中央约 `113.9 min`（y12 service ×2）；乘 `1.3` 计划余量约 `148 min` | 以已有峰值简单按 cells 缩放为 `26.6–34.4 GB`；乘 `1.3` 后约 `35–45 GB` |
| y12/air1 | 中央约 `64–65 min`（y12 基线 ×9/8 与 air1 ×2 交叉估算）；乘 `1.3` 后约 `83–84 min` | 基础缩放 `15.0–18.5 GB`；乘 `1.3` 后约 `19–24 GB` |
| 两场合计 | 中央约 `178–179 min`；计划余量后约 `231–233 min`（约 `3.9 h`） | 两场串行；数值是预测，不是总峰值或一次同时驻留内存 |

以上预测只用于评估是否值得申请新额度。直接 MUMPS 填充随拓扑变化可能非线性；内存缩放不是硬上界，也不是 solver pass。正式启动仍受 128 GiB service cap、动态宿主 reserve、祖先 cgroup 余量、任务 buffer、零 swap 和完整进程清场 Gate 控制。不得从两个异向局部对照外推全局误差阶。
