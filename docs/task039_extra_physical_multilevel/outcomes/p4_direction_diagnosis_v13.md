# P4 物理方向诊断 V13：受控停止与可审计的部分证据

## 结论先行

本轮没有完成三输入 P0–P4 诊断，状态是 `DECISION_DELIVERY_INCOMPLETE`。P0 的输入身份、质量度量等价性和 A2R160/01 的四个真实右预条件方向可以复核；随后在第一份输入的 P2/P3 中途，因新增诊断对象的 256 MiB 生命周期账本尚未闭合而受控停止。这里的资源结论是源码生命周期的推导，不是把 process-tree RSS 冒充数组预算，也不是整机内存或求解器 OOM 结论。

因此本轮没有发布 `DUAL_MASS_SCALED_P4_KRYLOV`、`SELECTIVE_MULTIPRECONDITIONED_P4` 或 `PHYSICAL_INTERFACE_MULTILEVEL_REDESIGN`。唯一下一步主项是 `IMPLEMENTATION_OR_METRIC_REPAIR`，具体修复和再次验证条件见 [决策卡](records/next_method_decision_v13.json) 与 [蓝图](next_method_blueprint_v13.md)。

## 身份、运行和停止

| 项目 | 事实 |
|---|---|
| 物理/模式 | `physical_model_sha256=9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f`；`ordered_mode_sha256=dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2` |
| 网格/身份 | p6 independent/storage=`164592/173802`；p4=`48960/53084`；MPI1、complex128、固定三份输入 `01/02/09` |
| 正式源码 | `e46fec48dc073a745e9b7e6c9186a147aefbc0a0`；运行前 source clean；工作树中的 split git 为 `.git-codex` |
| 首次失败 | source `80d2fb35145ac4770040ec9bb4627dfbe8cc7e67` 在 direct mass 完成后、P64 owner-row 检查处失败：`2.4834738612237617e-09 > 1e-11`；没有 I4/B4；原始负证据保留 |
| 修复重放 | `USER_CONTROLLED_STOP`，leader `-15`，全部后代清场；单调时钟 `542.6013903369967 s`，保守 realtime `592.4604761721841 s`；首次失败加重放为 `948.1497426901994 s` |
| 资源口径 | process-tree sampled RSS peak=`3125956608 B`、swap=`0 B`、launch cap=`9189265408 B`；RSS 不是 2.5 GiB 局部库存 cap，不能写成 cap violation |
| 局部库存 | 42块 allocated（含 padding）=1,671,000,000 B；used（含 padding）=888,000,000 B；allocated CSR=450,499,800 B；C_U 后保守库存=2,180,383,916 B < 2,684,354,560 B，沿用已资格化 V11 口径 |
| 停止原因 | P3 源码生命周期下界 `273571328 B` 已超过诊断新增数组 cap `268435456 B`，且尚未计入多类对象；这是 `DERIVED_UNCERTIFIED`，不是采样数组峰值 |

## P0–P3 证据状态

P0 先验证三份输入的 `g/c_ref/A4c_ref`、canonical map、旧四步身份和有限非零 `r_ref`。归一化后的 reference-free probe 由 `max(max_abs,l2_norm)` 缩放，归一化 2-norm 为 `0.9999999999999982`。degree-4 直接质量/旋度作用与 p6 pullback 的输出相对差分别为 `1.8218700611567345e-15` 和 `2.9122511040234625e-15`；固定正质量对角已保存且有限为正。这一 Gate 通过，但不等于后续候选通过。

P1 捕获的是 counted right-FGMRES PC 对实际 Krylov 输入返回的四个输出，不是 Arnoldi 基。A2R160/01 的保存包经过独立 checker 复核：四列、有效秩 4、实际解属于 `range(Z)` 的重建相对误差 `2.873275164100603e-16`，保存的 `rho`、`eta`、scaled-curl 量与原记录一致。P2 的局部响应已经被用于生成该输入的 P3 response packet，但完整 P2 packet 在停止前没有原子落盘。

P3 的 42 个局部 `A p_i` 和 `A_a/A_t` 独立坐标数组已保存。独立 checker 重算了固定选择 `[41,27,6,20,34,13,19,5]`；包含 `Z` 的 48 列 `L/AL` 残差空间有效秩 47，原方程残差 `rho=0.9358770172082744`；保存选择的 10 列 response-only 原方程残差为 `rho=0.9678905201139729`、有效秩 10。两者都是已保存 A 像上的 derived 原方程 `rho`，不是场误差；由于 `a/t` 和完整 P2 包缺失，不能推导它们的 `eta` 或 curl。

## 三输入候选表

下表采用 `rho / eta / eta_curl / rank`。`best-Z` 是只用于诊断的参考场最优 `y_M`，不是无参考生产结果；`scaled-Z` 是固定质量对角 `D` 的无参考候选。`best-L` 与 `selected-L10` 的场/curl列只有在完整 P2 数据存在时才有意义。

| 输入 | actual | best-Z（参考，仅诊断） | scaled-Z（无参考） | best-L | selected-L10 |
|---|---|---|---|---|---|
| A2R160/01 | `0.9502310252350668 / 0.9647147926182198 / 0.9646390272009856 / m=4` | `126.80492969347596 / 0.23602989478833247 / 0.33805312121755393 / r=4` | `1.0241864181252134 / 0.9602831778385792 / 0.9602354345340673 / r=4` | `0.9358770172082744 / not_run / not_run / r=47` | `0.9678905201139729 / not_run / not_run / r=10` |
| A2R160/02 | `not_run` | `not_run` | `not_run` | `not_run` | `not_run` |
| LIGHT448/09 | `not_run` | `not_run` | `not_run` | `not_run` | `not_run` |

`best-Z` 的巨大 `rho` 说明“把当前有限方向调到最接近参考场”不能自动保持原方程残差；但它的 `eta=0.236` 也说明不能笼统地说四个方向完全没有场逼近能力，在此四维空间两种最优目标得到的是差异很大的修正，不能从两个端点推断不存在折中解。`scaled-Z` 在 A2R160/01 的 `rho=1.0241864181252134` 仍满足原方程的 `1.10×actual` 线（约 `1.0453`），但 `eta` 比为 `0.9602831778385792/0.9647147926182198≈0.9954`，违反 strong-action 所需的至少减半条件，因此对这个固定 Z 的离线候选可判 `STRONG_ACTION_SIGNAL=false`；这不推出将来真正改变搜索方向的 scaled Krylov 必然无效。其余两份输入没有数据，选择性 response 的场/curl 仍是 `unknown`，不能外推。

## P2 局部—全局表

P2 需要保存 `a,h,d,A_d,t`、每块 `D_i d_i` 与 `D_iR_i e_h`，并独立复核有限 `r_ref` 恒等式：

```text
Ae_h = h - r_ref
D_i(d_i - R_i e_h) = chi_i + R_i r_ref + ell_i
sum_i R_i^H W_i(d_i - R_i e_h) = d - e_h
```

| 输入 | c_ref-a | c_ref-a-d | c_ref-a-d+t | PoU/重组 | a/d/t 全局 M0、curl与抵消 |
|---|---|---|---|---|---|
| A2R160/01 | `not_run_as_complete_p2_record` | `not_run` | `not_run` | `not_run` | `not_run` |
| A2R160/02 | `not_run` | `not_run` | `not_run` | `not_run` | `not_run` |
| LIGHT448/09 | `not_run` | `not_run` | `not_run` | `not_run` | `not_run` |

不能用 42 个局部 response 列替代这些 P2 恒等式，也不能把局部向量范数相加解释为全局场能量。保存的 P2 image 缺口是本轮不能选择下一生产方法的直接原因之一。

## 诊断内存账本

已有 `check_ls_workspace` 只递归计算 ndarray payload；它没有覆盖 `ReferenceCellBasis`、PETSc source/target Vec、metric 内部 buffer、local observation 以及部分 allocator/workspace。源码生命周期审计在构造 `L/AL` 后、删除 `p_columns/p_images` 前得到以下保守下界：

| 同时存活对象 | 字节 |
|---|---:|
| `L+AL` 48列 | 75,202,560 |
| `p_columns+p_images` | 65,802,240 |
| selected 10列及 A 像 | 15,667,200 |
| `Z+Q` | 6,266,880 |
| metric4/metric6 values/curls | 58,097,664 |
| 四个 SerialAction 的 PETSc Vec | 14,520,704 |
| 其余已明确的 RHS、参考、P1/P2/P3 和工作数组 | 38,014,080 |
| **已明确下界** | **273,571,328** |

该下界比 256 MiB cap 高 `5,135,872 B`，还未包含 native maps、local records、原始 md observation、metric action 临时量、Python object 和 allocator overhead。因此内存状态只能是 `DERIVED_UNCERTIFIED`，不能写成低内存 PASS。未来需要给 `LosslessFEMetric` 增加 opt-in construction flag，使本诊断不创建不用的 `metric6` basis；若兼容路径已经创建，则要真正释放。旧调用保持原 construction behavior。详细 compact evidence 是 [memory liveness record](records/p4_direction_diagnosis_v13_memory_liveness.json)。

## 独立复核与边界

独立 checker 只读 ignored raw 的 JSON/NPZ，用稳定 QR/SVD 重算 16 项：16/16 通过。root 已有第一次 `/usr/bin/time` wall `1.70 s`；本轮再次复核 wall `4.70 s`，主控首次复核 wall1.70 s；执行窗口复核核心脚本时间 `1.6693295069999294 s`，MaxRSS `198344704 B`，swap 0。两次 wall 都保留并计入证据成本，core/elapsed 不重复相加。两次复核 wall 均计费，两次正式运行加两次复核的已知总时间为954.5497426901994 s。它验证的是保存的 A2R160/01 部分包，不是三输入任务完成。记录见 [offline audit](records/p4_direction_diagnosis_v13_offline_audit.json)。

以下均保持 `not_run`：A2R160/02、LIGHT448/09 的 P1–P3；完整 P2 nonzero-`r_ref` 恒等式；三输入 strong-action signal；完整 `best-L/selected-L10` 场/旋度；任何新 Krylov；新完整 p6 original/notch 求解；E/H、近场、R/T/A、`A_volume`、衍射级和守恒。后续顺序必须是三输入取证闭合、new review 资格化 PC、冻结 13.5 nm p6/h10 original 全外层；original 通过后才做同配置 notch，并执行 A6 `1e-6`、场/curl `1e-4`、R/T/A/体吸收/守恒 `1e-5`、80复幅 `1e-4`、功率 `1e-6` 和完整资源 Gate。大型 NPZ、factor、cache 和时间线留在 ignored artifact root；Git 只保存 hash-bound compact records。

机器记录总入口：[p4 compact](records/p4_direction_diagnosis_v13.json)。
