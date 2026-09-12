# P4 物理方向诊断 V13：历史受控停止与续算收口

> 本文前半部分保留初始 V13 的负结果快照；下方“当前续算”是最终 source `3457b5e2f54dec690fcb70deb1f387fe7f6d57cd` 的三输入诊断结论。旧 256 MiB stop 未被追溯改判为通过。

## 初始 V13 受控停止（历史快照）

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

```math
\begin{aligned}
Ae_h&=h-r_{\mathrm{ref}},\\
D_i(d_i-R_ie_h)&=\chi_i+R_ir_{\mathrm{ref}}+\ell_i,\\
\sum_iR_i^HW_i(d_i-R_ie_h)&=d-e_h.
\end{aligned}
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

## 当前续算：三输入诊断已完成，但没有生产 PC

表内数值按9位有效数字显示，完整精度见续算compact。rho是近似解的原A4相对残差；eta和eta_curl分别是相对匹配参考的无材料质量积分误差和scaled-curl误差。固定scaled-Z重新计权原四个方向的残差；selected-L10从42个局部响应选至多8个，连同a和-t作原残差最小组合，仍须支付全部42个A像的构造费用。

续算在一次 fresh 42-block 构建上完成：`A2R160_BAL_H_p4_01` 复用身份合格的 P1/I4/bare packet，`A2R160_BAL_H_p4_02` 和 `LIGHT448_BAL_H_p4_09` 新做 I4/bare。当前 raw/compact 状态为 `P4_DIRECTION_DIAGNOSIS_COMPLETED`、`gate_pass=true`；这只是诊断工作流完成，不是 official Maxwell 求解或 production PC qualification。

### 当前身份、费用和资源

| 项目 | 当前事实 |
|---|---|
| source / model / ordered mode / input | `3457b5e2f54dec690fcb70deb1f387fe7f6d57cd` / `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` / `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2` / `86829433e2dd4412b5e6b1e7903255ed33a462dcf5afadffe56efa841e5e7692` |
| ABI 与规模 | MPI1、`complex128`、`int32`；42 blocks、80 DtN modes；p4 independent/storage `48960/53084`，p6 `164592/173802` |
| 正式计时 | 一次必要 fresh 42-block 构建 `300.807805 s`；01/02/09 分析阶段 `216.48585 / 272.964772 / 272.377783 s`；历史已计费 `954.549743 s`；本次外层 supervisor `1204.47179 s`；修正正式累计 `2159.02153 s` |
| 审计追加 | continuation `1.09 s` + block-outside `0.17 s` + resource review `0.12 s`；截至 resource review `2160.40153 s` |
| 监督与采样 | leader exit `0`、后代清场；RSS `3287973888 B`、PSS `3254656000 B`、swap `0 B`；resource review `4252` samples、`34016/34016` checks passed |
| 工作区 | 本次 cap `536870912 B`，最大估计 `369795024 B`；旧 cap `268435456 B` 的 liveness lower bound `273571328 B` 仍是历史负结果 |

正式计费使用外层 supervisor；worker 原始 clock `1201.563813993922 s` 仅保留为 raw diagnostic。旧负结果中的首次 owner-row discrepancy `2.4834738612237617e-09 > 1e-11`、旧 controlled replay 和旧 256 MiB liveness 均未改写。allocated padded `1671000000 B`、used padded `888000000 B`、allocated CSR `450499800 B` 和 C_U 后 `2180383916 B` 是局部库存指标，不能与 RSS 或 liveness lower bound 混用。

| 成本比较（秒） | `A2R160_BAL_H_p4_02` | `LIGHT448_BAL_H_p4_09` |
|---|---:|---:|
| 原 I4 基础内核（实测；新尺度化 Krylov 未运行） | `7.43339113` | `7.05866804` |
| selective lower：bare B4 + 42 个 `A p_i` + `A(-t)` + selector | `22.533772` | `22.7700278` |
| selective covered upper：加全部 dense QR/SVD（覆盖 final10 LS） | `22.9368437` | `23.1821034` |

上述 selective lower/upper 是已测的嵌套诊断成本，不是完整未来外层 KSP 成本；01 的复用 I4/bare packet 细分时长为 unknown，不能填零。

### 当前三输入统一指标

每个三元组按 `rho / eta / eta_curl` 排列。`actual` 是实际四步 I4 返回的解；`best-Z`/`best-L` 使用参考场，只是标尺或 oracle；`scaled-Z` 和 `selected-L10` 才是无参考诊断候选，但本表仍不等于物理结果。

| 输入 | actual | best-Z（reference-only） | scaled-Z | best-L（oracle） | selected-L10 |
|---|---:|---:|---:|---:|---:|
| `A2R160_BAL_H_p4_01` | `0.950231025 / 0.964714793 / 0.964639027` | `126.80493 / 0.236029895 / 0.338053121` | `1.02418642 / 0.960283178 / 0.960235435` | `86.688459 / 0.213419927 / 0.292679164` | `0.96789052 / 0.992583743 / 0.992554855` |
| `A2R160_BAL_H_p4_02` | `0.101264949 / 0.877757076 / 0.877371768` | `6.39136754 / 0.170914106 / 0.25953131` | `0.165361737 / 0.742969278 / 0.742565056` | `3.16286411 / 0.14613246 / 0.186722965` | `0.173007783 / 0.96992168 / 0.969507771` |
| `LIGHT448_BAL_H_p4_09` | `0.977895241 / 0.992817604 / 0.992802276` | `152.556741 / 0.221237812 / 0.310294927` | `0.997120938 / 0.995016514 / 0.995013927` | `110.065271 / 0.194652922 / 0.266357032` | `0.992461078 / 0.997122877 / 0.997112985` |

对应的 residual-oriented 三元组也必须单列，避免把“场最优”与“残差最优”混称：

| 输入 | `Z_residual` | `L_residual` |
|---|---:|---:|
| `A2R160_BAL_H_p4_01` | `0.950231025 / 0.964714793 / 0.964639027` | `0.935877017 / 0.962653537 / 0.962567851` |
| `A2R160_BAL_H_p4_02` | `0.101264949 / 0.877757076 / 0.877371768` | `0.0951039085 / 0.883431704 / 0.883038825` |
| `LIGHT448_BAL_H_p4_09` | `0.977895241 / 0.992817604 / 0.992802276` | `0.964794655 / 0.991134125 / 0.991113434` |

`scaled-Z` 在 01 的 eta 比为 `0.995405190426173`，没有达到困难输入 eta 至少减半的 hard 条件；fixed-Z strong-action signal 为 `false`。`selected-L10` 的 strong-action signal 也为 `false`。`best-Z` 虽能给出较小 eta，但伴随很大的 rho，因此只能作为 reference-only field oracle，不能进入 PC、selector 或 initial guess。

### P2 局部—全局分解

`P2_c_ref_zero_initial` 的零初始基线指近似解为 `0`、误差为 `c_ref`，故 `rho/eta/eta_curl=1/1/1` 并不表示参考场残差。后续 P2 表的 `eta/eta_curl` 是误差 `c_ref-a`、`c_ref-a-d`、`c_ref-a-d+t` 的场/旋度误差；对应 `rho` 分别来自近似解 `a`、`a+d`、`a+d-t` 的原方程残差。

| 输入 | `c_ref-a` | `c_ref-a-d` | `c_ref-a-d+t` |
|---|---:|---:|---:|
| `A2R160_BAL_H_p4_01` | `3.79457109 / 0.930671134 / 0.93065853` | `14.0889637 / 0.920132086 / 0.920020217` | `4.5683427 / 0.848992333 / 0.848835797` |
| `A2R160_BAL_H_p4_02` | `0.204475774 / 0.980973007 / 0.980587899` | `0.452118314 / 0.973784692 / 0.973376101` | `0.193949173 / 0.914617715 / 0.914280712` |
| `LIGHT448_BAL_H_p4_09` | `4.3922676 / 0.931661661 / 0.931677408` | `15.0118944 / 0.922746851 / 0.922690902` | `5.10196078 / 0.858182034 / 0.858122287` |

| 输入 | `a` mass/curl | `d` mass/curl | `t` mass/curl | `a+d-t` mass/curl | cancellation mass/curl |
|---|---:|---:|---:|---:|---:|
| `A2R160_BAL_H_p4_01` | `12.348341 / 12.746971` | `3.09978418 / 4.85595853` | `11.6599294 / 12.0250054` | `25.2866486 / 25.5794836` | `0.932809418 / 0.86335695` |
| `A2R160_BAL_H_p4_02` | `0.485286352 / 0.751646126` | `0.335790096 / 0.568774661` | `1.48652132 / 1.52530266` | `2.10582078 / 2.20330231` | `0.912559723 / 0.774250326` |
| `LIGHT448_BAL_H_p4_09` | `24.7927491 / 25.5096754` | `5.54755991 / 8.57623536` | `21.9153509 / 22.5606821` | `48.887641 / 49.3810361` | `0.93554729 / 0.871738856` |

保存的 P2 packet 还绑定了每输入的 initial closure、feedback、`e_h-A` identity、global recomposition、PoU、local solve 和 remainder；continuation audit 从原始字段独立检查 `219/219` 项。curl 检查使用保存的 squared norms，weighted-R field 检查使用保存的 measured metric factorization；没有把这两项限制隐藏成 fresh FE action。


全局重组误差的范数和已有粗修正的 closure 如下。closure 使用原物理粗限制的操作尺度，限值仍为1e-8；C_U不是M0正交投影。

| 输入 | d-e_h 的 M0 / curl 范数 | C_U initial / feedback closure | 局部回代最大相对误差 |
|---|---:|---:|---:|
| A2R160_BAL_H_p4_01 | 104.158699 / 104.295797 | 1.05622e-12 / 8.27729e-14 | 3.94086e-14 |
| A2R160_BAL_H_p4_02 | 18.4150544 / 18.4310214 | 9.46942e-15 / 9.14771e-14 | 1.70875e-14 |
| LIGHT448_BAL_H_p4_09 | 218.057181 / 218.306418 | 1.44038e-12 / 8.38784e-14 | 2.45856e-14 |

表中 cancellation 定义为同一M0或curl范数下 `norm(a+d-t)/(norm(a)+norm(d)+norm(t))`。它衡量向量合成时的抵消，不能解释为原因占比；重叠块范数也不能相加当作全局能量。

### 结构、动作和下一方法

结构清点得到 Gamma rows `13092`、I rows `35868`、合法 rows `48960`、coverage defect `0`；shared macro-DOF rows `12108` 与 nonzero DtN support rows `1152` 存在重叠，不能相加。cross-volume cells/rows `0/0`，DtN entries `80`，coupling/projection NNZ `31968/31968`，最大 local block `1944` rows。假设 dense Gamma Schur 需 `2742407424 B`。本批只清点 Gamma/I 结构，没有构造或施加新 Schur 算子；matrix-free Schur 是下一轮蓝图，当前已有资格的 A4 作用不等于新 S 已实现。

block-outside audit 是同一 block 内操作项的系数范数诊断，不是全球场能量或百分比。42-block 的 `||chi||/(||R_i A e_h||+||D_i R_i e_h||)` 中位数为 01/02/09：`0.99796865100185 / 0.9840960661566445 / 0.9961730504361788`；对应 `chi_norm` 中位数为 `18.084174988730773 / 4.392058047722505 / 42.93508393478842`，`ell_norm` 中位数为 `5.450596891409682e-16 / 9.69595278950643e-16 / 3.262991626739957e-15`。

动作账为 A4 total `149`（prior `49` + new `100`）、M0 direct/pullback `2/211`、curl direct/pullback `1/217`、P64 primal/adjoint `428/428`、I4 `3/3`、bare B4 `3/3`，B4 total `15`；02/09 的新增 I4 和 bare B4 均为 `2/2`。01 的旧 I4/bare 细分时长是 unknown，不能填零。

当前决策不是“已选 production PC”，而是：

| 字段 | 值 |
|---|---|
| `primary_method` | `PHYSICAL_INTERFACE_MULTILEVEL_REDESIGN` |
| `decision_status` | `ARCHITECTURE_PRIORITY_SPECIFIED_UNQUALIFIED` |
| `confidence` | `medium`，只用于 architecture priority |
| `performance_confidence` | `low` |
| fixed dual-mass / selective strong-action | `false` / `false` |
| official physics / production PC | `not_run` / 未选择 |

下一方法蓝图提出 actual complex physical local Schur singular directions 与 nonzero DtN bilateral channels：每 patch 最多 `8` 个 verified directions、最多 `64` 个含 verification 的 equivalent augmented actions、最多 `32` 个 work vectors、每 patch `2048` rows；用 `P^H S P`、一个 fixed Vcycle，bottom 最多 `512` rows/`64 MiB` allocated，若超过则最多聚合 `8` 个邻居，不能 strict reduction 就停止。这是待 review 的 proposal。

完整接口动作应写为

```math
B_{4,\mathrm{new}}g=C_Ug+(I-C_UA_4)F_{\mathrm{interface}}(I-A_4C_U)g.
```

`F_interface` 包括局部消元、固定 Vcycle 和恢复，但不包含外包的 `C_U/A4`。每次还须计入 `2 C_U` 与 `2 A4` 的逻辑作用；首层最多 `168` 个内部回代只是 `F_interface` 的一部分，不能写成完整 B4 action 总数。已有 P2 的 `8192` rows/`512 MiB` 限额不能增长。该接口方法尚未实现或性能资格化。

### 当前证据入口

- [续算 compact](records/p4_direction_diagnosis_v13_continuation.json)
- [219 项 continuation audit](records/p4_direction_diagnosis_v13_continuation_audit.json)
- [block-outside audit](records/p4_direction_diagnosis_v13_block_outside_audit.json)
- [resource review](records/p4_direction_diagnosis_v13_resource_review.json)
- [统一 provenance](records/p4_direction_diagnosis_v13_continuation_provenance.json)
- [当前 decision](records/next_method_decision_v13.json)
- [下一方法蓝图](next_method_blueprint_v13.md)

当前运行没有产生 official E/H、近场、R/T/A、`A_volume`、衍射级或守恒结果；全仓 pytest、CI、production-PC qualification 和 `F_interface` 性能 qualification 均为 `not_run`。旧 compact、旧 liveness、旧失败和旧受控停止仍是历史证据，不被当前完成状态覆盖。
