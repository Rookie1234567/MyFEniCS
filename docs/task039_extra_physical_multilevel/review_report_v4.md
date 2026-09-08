# Task39extra Review V4：p4 有限精化与诊断依赖隔离

## 0. 审阅身份与执行裁决

```text
repository                 = Rookie1234567/MyFEniCS
branch                     = task39extra
review_date                = 2026-09-08
reviewed_HEAD              = 7d234ae597aa21f901659ebfe844481c1857b5da
reviewed_formal_source     = bf8e0c1d16c9c86677e866cdf29fd5491f076e32
original_task_base         = 2dc2e7305f10dc391a13970c6f0f0340cb87b6ee
previous_review_response   = review_report_v3.md / response_v4.md
new_scope                  = BOUNDED_DIAGNOSTIC_COMPLETION
execution                  = C0 -> C1 -> C2 -> C3 -> conditional C4 -> C5
response_required          = response_v5.md
new_PC_or_outer_full_solve = NOT_AUTHORIZED
master_merge               = NOT_APPROVED
```

**本轮消除的 blocker：诊断用 p4 参考在一个输入上略超精度门槛、未保存失败向量，且调度把不依赖该逆的分析一起终止，导致表示能力和细层互补至今没有数据。** 本轮不是继续提高 p4 精度以挽救外层，也不是再换一种 PC。

最终目标仍为约 2 TB 整机内存内求解 0.7 nm、complex128、Nedelec H(curl)、双 Floquet、Fourier-DtN、周期单胞内任意非可分三维 Maxwell 散射。本次在约 16 GB 本机补齐原始 13.5 nm 的有限诊断，不改变 full-space matrix-free 主线。

本轮用户明确要求新 review 并继续补测，因此授权一次新增诊断批次；它明确覆盖 V3 及 Response V4 本次收口中的“不精化、不重试”限制，仅限下述范围。旧门槛、旧失败、旧时间账本不改写。C0–C5 连续推进，中间不在保存一个向量、完成一次修正或一项小测试后停审；共同正确性/安全阻碍不可消除时才提前收口。未授权新分支、merge、新的 PC 长跑或恢复旧 F3。

## 1. 审阅结果与已可复用的证据

依据 [Response V4](response_v4.md)、[诊断报告](outcomes/nonconvergence_diagnosis_v3.md)、[紧凑记录](outcomes/records/nonconvergence_diagnosis_v3.json) 及当前 p4/worker 源码。以下为历史 measured/derived，不是本 review 新测结果。

| 内容 | 已发生结果 | 裁决 |
|---|---|---|
| 三份 checkpoint 的原 A6 残差 | 最大绝对复现差 2.77556e-16，native 独立系数匹配、分项作用闭合 | 保留，不重做三条长程求解 |
| 完整 PC 诊断 | 8 started / 7 completed；第 8 次为 JOINT448 输入 LIGHT | 七份 q/z/Az 复用，第八次不追溯计为完成 |
| 后期残差上的弱修正 | LIGHT448 对三种完整 PC 的 rho 约 0.993947 / 0.999263 / 0.999012 | 是有限样本证据，不是所有 FGMRES 无效的定理 |
| p4 拒绝 | 原 A4 相对残差 1.0086968840613509e-10，门槛 1e-10 | 旧拒绝有效；超限约 0.8697% 不等于已查明外层平台原因 |
| 失败输入证据 | 未保存失败的 p4 RHS、解及残差向量 | 不能声称已独立重算；此次重建并保存 |
| 资源 | RSS 采样峰 3777171456 B，cap 8367992832 B，swap0 | 不是本次内存触顶，也不代表 0.7 nm 容量资格 |
| 数学缺口 | 已知误差、M0 最佳投影、粗响应和互补未运行 | 必须优先取得这些数据，不再扩大方法搜索 |
| 时间 | 诊断 opt-in 已记录 UTC 偏移并作逐段保守收费 | 复用现实现，不再调查或修改系统时钟 |

这里的完整 S6 组合是 `S6 -> p4 -> S6`，不是单独 S6 平滑器。p4 小残差只是满足该次方程检验，不是已证前向解误差界。大项相消比约 298–379 不是条件数、共振或色散根因的测量。

ChatGPT 本次只作远程文件/源码审阅及文档编写，没有运行 PDE，也没有读到全部 ignored raw。Codex 需从保存向量复算本批次新增结论，不能只读取 status 字段。

## 2. 冻结身份、改动范围与历史边界

| 项目 | 本轮合同 |
|---|---|
| 原始物理 | 13.5 nm、grazing1°、s、原单胞/材料、p6/h10 六面体、MPI1、线程1、80 modes，按 task.md §3 |
| A6 与 A4 | 原真实算子、积分规则、约束、carrier、P/P^H 不改；不加损耗、不减通道 |
| 物理 SHA | `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` |
| mode SHA | `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2` |
| 空间 | p6 存储/独立行 173802/164592；p4 存储/独立行 53084/48960；增广 53164 行 |
| p4 数值门槛 | 原 A4 相对残差 <=1e-10，保持不变 |
| 允许改动 | 失败 packet、显式诊断精化策略、按依赖隔离、增量保存和最小接线 |
| 禁止改动 | 旧 PC 默认、平滑窗口/次数、MR、restart、p/h、shift、LU 排序/主元参数扫描 |
| 禁止新增运行 | 原始外层长跑、fine direct、非可分 full solve、h5、MPI 扫描、5 nm/0.7 nm、PML/DD 新候选 |

沿用根和 docs 的 AGENTS、repository_work_principles、Markdown 标准。task.md 与 V3 的数学定义继续有效，只有本文件明确写出的执行顺序、有限精化、分项继续及新预算覆盖旧规则。

旧 `solve_intermediate()` 默认仍为一次回代及 strict Gate。新增行为用显式 `diagnostic_refinement_v4` 策略启用，默认关闭，旧 profile 和历史 hash 不追溯改变。接受了精化后结果的诊断，必须注明策略及实际额外工作，不能称与旧一次回代逐位相同。

## 3. 连续批次：先拿到独立数学数据，不再被一个子步骤全部挡住

| 阶段 | 必须执行 | 条件分支 |
|---|---|---|
| C0 | 复用旧七份 packet 和三份 identity；实现失败保存、精化与依赖隔离；一批 focused tests | 不重跑旧七项，不重新写全历史综述 |
| C1 | 同 ABI/mesh 重建必要 A6、P、M0、H6/S6；最小身份连接与资源检查 | A6/约束不可信则停止；p4 factor 尚未通过不阻止独立 C2 |
| C2 | 先保存已知误差及 q=A6e；做一次 M0 最佳投影，再做 H6/S6 补空间检查 | 投影不合格就保留近似及不确定性，不能宣布空间失败 |
| C3 | 按原输入生成方式重建第八次 p4 输入；保存原解，核对两种残差；必要时最多两次精化；补缺少的粗响应与 PC 对照 | 单个精度拒绝只跳过受依赖项，不跳过已经合法的独立诊断 |
| C4，条件 | 仅按 V3 §8 的既有触发条件做受限传播控制 | 无证据或实现不支持就不做，不新开 QEP/本征项目 |
| C5 | 更新原因矩阵、依赖状态、可复用 packet 与唯一下一建议；提交 response_v5.md | 不是以“修好了 p4 门槛”作为任务完成 |

C1 优先构建不需要 p4 LU 的部分；p4 matrix/factor 可以推迟到 C3。复用既有 builder 的组成函数，最多拆开必要接线，不能重写求解平台。p4 数值对象不得成为已知误差、质量投影和 H6/S6 检查的虚假依赖。已有 cache 仅在 form/ABI/hash 匹配时复用，cache 与现场内存都记录。

一套共享空间和有限工作区即可完成本轮；p4 factor 建成后复用，不按样本重分解。若 C3 安全预审不能构建 factor，记录缺口，但 C2 已取得的结果仍应保留。实际资源越线仍停止整个运行，不允许以“独立项”名义继续冒险。

## 4. 失败向量必须在检查拒绝之前保存

旧第八次失败的 p4 向量没有存盘。因此，本次是 `RECONSTRUCTED_FAILURE_CASE`，不是已证明逐位相同的旧失败重放。

从已保存的 JOINT448 原 fine 残差开始，沿旧归一化、H6 预修正、MR 和 P^H 路径生成 g4。完整 PC 输入 q 与中间 g4 是 dual RHS；解 y 是 primal FE 系数，使用合法独立/zero-slave 存储，不因旧错误文字标签把角色混淆。

**求解前**保存 q、预修正后 residual、g4 及 hash；**任何 Gate 判断前**保存以下最小 packet：增广 RHS/解、提取的 y 与端口 a、原 A4y、原残差、增广残差、范数、源/矩阵/carrier/约束身份，以及本次 solve/精化序号。仅保存少量向量和稀疏元数据，不复制全局矩阵或 factor 文件。

packet 写到 ignored artifact，Git 保留相对路径、hash、向量角色和标量。写入成功后再返回 pass/rejected。若无法保存必要证据，标记证据错误并安全退出，不以一次空异常替代失败输入。异常处理与 cleanup 分别记录；析构异常不能阻止最小 summary 的原子写入。

此次若原回代恰好低于1e-10，就如实记 `ORIGINAL_REJECTION_NOT_REPRODUCED`，仍核对残差关系并继续 C3；不扰动输入寻找一次新的失败，也不追溯将旧值改为通过。

## 5. 核对增广系统与原 A4：残差定义必须一致

当前实际分解的系统为：

```math
\mathcal A_4
=\begin{bmatrix}V&C\\-D&H\end{bmatrix},\qquad
\mathcal A_4\begin{bmatrix}y\\a\end{bmatrix}
=\begin{bmatrix}g\0\end{bmatrix},\qquad
A_4=V+CH^{-1}D.
```

此处 H 是端口归一化块，不是 H6 平滑器；端口逆作用使用已验证 carrier，不形成新的稠密 Schur 矩阵。定义：

```math
r_F=g-Vy-Ca,\qquad r_P=Dy-Ha,\qquad r_4=g-A_4y.
```

在相同算子与精确算术下，直接消元可得：

```math
r_4=r_F-CH^{-1}r_P.
```

用已装配的增广矩阵计算其残差，用原 matrix-free A4 独立计算 r4。保存两块绝对范数、以原 norm(g) 归一化的范数、CH^-1rP 的作用及差向量。端口 RHS 为零，不用 norm(0) 作相对残差分母。记录原代码的 `A4y-g` 与本文 `g-A4y` 符号差别，精化必须用后者。

比较该恒等式时同时报告相对 norm(g) 和相对运算尺度的差异。一个可用尺度为 norm(g)+norm(Vy)+norm(Ca)+norm(CH^-1Dy)，分母零按既有 tiny/零向量规则处理。**不要要求两个约1e-10的小残差之间再具有1e-10相对一致性，造成新的舍入级硬门槛。**算子定义一致性沿用已批准的作用核验标准；原 A4 解验收仍是 norm(r4)/norm(g)<=1e-10，两者不可互相替代。

只对重建的 y 和一份既有合法 p4 控制向量作必要 native/assembled 作用核查，沿用1e-10作用相对容差。若有显著定义/映射失配，不进入精化去掩盖；隔离该 A4 路径，保留 C2，指出具体 blocker。细层 A6/P 也受影响时停止所有依赖它的项。

增广残差小而原残差较大，可能涉及端口残差放大、有限精度或两条作用路径差异，不自动证明任何一种根因；不能只用小 backward residual 宣称 forward error 很小或参考一定可靠。

## 6. 仅诊断启用的有限 iterative refinement

精化的含义是：先计算当前解还剩多少方程不平衡，再用已有 LU 对这个不平衡求一次修正。它增加有限回代和 A4 action，不重新分解、不改变原问题。它是标准线性求解工具，而不是新的外层 PC 候选；参见 [LAPACK GERFS](https://www.netlib.org/lapack/explore-html/d5/da4/group__gerfs.html)。这里的具体限制由本 review 规定，并非声称复现了 LAPACK 全部误差估计功能。

对每个本轮允许的逻辑 p4 RHS，先作原始一次回代并检查。通过即返回；只在 finite、约束与定义一致且未通过原1e-10门槛时，允许最多两轮：

```math
r^{(j)}=g-A_4y^{(j)},\qquad
\mathcal A_4
\begin{bmatrix}\delta y^{(j)}\\\delta a^{(j)}\end{bmatrix}
=\begin{bmatrix}r^{(j)}\\0\end{bmatrix},\qquad
\begin{bmatrix}y^{(j+1)}\\a^{(j+1)}\end{bmatrix}
=\begin{bmatrix}y^{(j)}\\a^{(j)}\end{bmatrix}
+\begin{bmatrix}\delta y^{(j)}\\\delta a^{(j)}\end{bmatrix}.
```

每一轮都以**最初 g 的范数**计算原 A4 真残差，并保存修正前后向量/范数、delta y 的相对大小与 residual change；达到1e-10立即停止精化。累计更新 a 是为了保留一致的增广状态；另作端口重构时必须标记为独立诊断，不能覆盖原回代的 a 并掩盖端口残差。

执行约束：

| 项目 | 合同 |
|---|---|
| 次数 | 每个逻辑 RHS 一次原回代，最多两次额外回代；不是不断迭代到通过 |
| 低层调用 | 复用已存在 factor.solve_repeated；不递归调用会再次触发精化的高层 solve_intermediate |
| 误差检查 | 修正 RHS 很小时仍检查 finite/约束，最终验收用原 g；不让修正子问题的严格相对门槛触发无限递归 |
| factor | 相同矩阵、排序、精度和因子；记录 MUMPS 已有内部精化设置，不扫描 ICNTL 或混合精度 |
| 未通过 | 记录 `REFERENCE_ACCURACY_UNRESOLVED`，保留所有向量，拒绝该依赖结果，不改历史 PASS/FAIL |
| 大解变化 | 小残差但解修正很大时，标 reference sensitivity 限制，不能据此推导严格前向误差界 |

旧 profile 的默认精化次数仍为0。只有本轮诊断 opt-in 可为2；旧 PC 参数、生成方向及 MR 公式不改。使用精化后的方向时记录 `REFINED_DIAGNOSTIC_ACTION`，它不是旧一次回代数值输出的逐位复现，也不能据此宣称新生产求解器通过。

不接受“仅超0.87%，直接放宽到1.1e-10”的处理，也不允许“还差一点，再来第三次”。补救失败时仍继续独立的 C2 或其他无依赖项，见下一节。

## 7. 补齐表示与互补：明确依赖，不用广泛异常捕获掩盖错误

继续使用 V3 已冻结的一个三维已知误差 recipe，不按新结果挑容易样本。保存原 e 与 q=A6e；若归一化，e 和 q 同比缩放，并记录缩放尺度。

```math
c_* = \arg\min_c\|e-Pc\|_{M_0},\qquad
(P^HM_0P)c_*=P^HM_0e,\qquad
e_\parallel=Pc_*,\quad e_\perp=e-e_\parallel.
```

```math
\eta_{\rm space}=\frac{\|e_\perp\|_{M_0}}{\|e\|_{M_0}},\qquad
\eta_C=\frac{\|e_\perp-C(A_6e_\perp)\|_{M_0}}{\|e_\perp\|_{M_0}},\quad C=H_6\text{ or }S_6.
```

M0 为无损、未加材料权重的 FE 质量度量，只是诊断尺子，不是新物理 PC。保留 L2 与缩放 curl 两种记录，不能把 dual residual 当 primal 电场。投影采用原 fixed-diagonal CG、target1e-10、max256和1800s累计上限，检查正交条件、Pythagorean 缺陷与 native mass 等价。未收敛投影给出的误差只是一个可达近似，不以大上界证明空间不足。

| 子项 | 必需依赖 | 某 p4 物理回代拒绝后 |
|---|---|---|
| 旧七份响应的离线复算 | 已存 q/z/Az 和身份 | 继续，不重跑 |
| 已知 e、q 与 M0 投影 | A6、P/P^H、M0 | 继续，不需要物理 p4 LU |
| H6/S6 补空间作用 | 合格投影、A6、相应平滑器 | 继续；S6的自身p1辅助因子是另一依赖 |
| 实际 p4 coarse response | 本次输入的合格 A4 解 | 拒绝该项并存证据，不能使用未合格解填通过表 |
| 完整 PC 比较 | 本次调用的所有子项合格 | 此项拒绝；不自动否定其他不同输入 |
| 共同 A6/映射/输入错误、非有限值、资源越线 | 影响共同基础或安全 | 停止受影响范围；全局影响时整个进程退出 |

用具名 `ReferenceAccuracyRejected` 或结构化返回隔离这一类局部精度未通过，不用 `except Exception: continue` 忽略所有错误。内存/监控故障、未知错误和 cleanup 失败不能伪装成可跳过的参考拒绝。

p4合格时再计算实际修正 dG=P A4^-1 P^H A6e，比较未缩放和原MR后修正与 e_parallel；在一个非零 range(P) 向量上核对 coarse identity。没有合格投影时不标最优能力；可以保存实际修正，但只报告其独立含义。

本轮只补两个遗漏的真实残差比较：JOINT448 对 LIGHT 的重建调用，以及 JOINT448 对 JOINT；七个旧完整对照不重跑。再在已知误差上比较三种旧组合与各一次非实数同比缩放检查。精化若应用于其中某项，单列变化，不把不同策略混算为严格旧 profile 性能。

**缺少真实 x_ref 的事实仍保留。**人工 e 只是在原三维 A 上有已知答案的控制，不是实际入射散射误差，也不是非可分材料器件通过。若这些控制良好却无法解释真实残差，结论应是需要匹配的 fine 参考/真实误差，不再追加随机样本或强行认定 p4 色散。本批次不启动新的 fine direct；后续参考取得路线需明确成本与迁移条件。

## 8. 数量、资源、时间与停止边界

这是用户授权的新增补测预算，不借用 V3 未用余额，不重置旧账本。只将实际启动的测试、setup、诊断、失败尝试和收尾计算计入本批计算账；等待审阅和文字编辑另列，不冒充数值耗时。复用现有账本实现，不新建预算平台。

| 范围 | 上限 |
|---|---:|
| 本批全部实际计算（含测试/失败/cleanup） | 7200s，按已修复的保守收费口径 |
| 原始规模补测 workflow | 5400s，含共享 setup 和 factor 构建 |
| 已知误差 M0 最佳投影 | 1次，最多256 CG步，累计1800s，包含于workflow |
| 完整 PC 诊断 | 最多8次尝试，包含2个遗漏输入、3个已知误差与3个同比缩放检查 |
| 独立 H6/S6 互补 | 最多4次作用，包含同比缩放检查 |
| 直接 coarse/identity 控制 | 最多2个逻辑 p4 RHS |
| 原 p4 回代及显式精化 | 总计最多10个逻辑 RHS；最多30次外部 MatSolve 调用，内部 MUMPS工作另报 |
| 条件 D4 | 仍按V3至多4个小问题、900s和256MiB局部工作限制；包含于本批总预算 |

上限不是填表目标。零向量直接处理，不浪费求解；同一 p4 输入在前项未合格时，明确依赖相同的后项可以标跳过，不反复碰同一门槛。没有新原始外层 full solve，也不增大 max-it/restart。只为可明确修复的实现错误允许在本批总量内修复受影响项，已成功 packet hash 匹配则复用；数学或精化无收益不算 bug。

本机资源仍按有效RAM/cgroup与available，预留 max(4GiB,15%有效整机)，cap不超过12,000,000,000 B且每次动态计算；RSS含parent、MPI、FFCx/编译器全部后代。zero-swap、一次一个heavy、资源与clean-source预检不变。新精化和失败保存不得保存稠密全矩阵；实际额外工作区计入总cap，向量存盘后可释放。

沿用 bf8e0c1 的诊断 opt-in `conservative_realtime`：逐段保存 monotonic/BOOTTIME/UTC，按已批准规则保守扣账，UTC向前计费、回拨不退款；不把UTC变化再次变为共同数值故障，不更改系统时钟/BLAS/库。原始时间与保守费用分开，不能声称strict时间一致性或通用speedup。

安全故障立即停止；预算或用户请求按已有安全点收口。单项精度拒绝先保存、标拒绝再继续独立项。每个数学项目完成即原子保存；最终主summary使用finally保障，但不能让清理异常覆盖原始异常。阶段名必须区分 started/completed/rejected/skipped，不把八次开始写成八次完成。

## 9. 验证、提交与最终交付

代码只作窄修改：`fullspace_p4_reference.py` 的显式策略和packet钩子、既有低层factor回代、`physical_diagnosis.py/worker` 的依赖顺序及分项状态；M0/数学指标仅作必要接线。数值逻辑进src，runner不另实现第二套Maxwell、Schur或CG，不复制大型task脚本。

一批 focused tests 覆盖：复数增广残差符号；失败前保存；默认拒绝行为不变；一/两次修正及次数封顶；修正用原g归一化且无递归；参考拒绝后质量投影/独立项继续；共同映射/非有限/资源错误仍停止；异常摘要和清理保存。修正前后已有算子保持同一身份，正式补测前须clean commit。测试通过不当作原尺寸分析已完成。

建议两个普通代码/证据提交阶段：最小保存/精化/隔离实现并测量 -> 补测结果及原因矩阵集中收口。不amend、强推、不改master，不修改旧task/review/response或覆盖旧raw。首次读取失败后的旧缓存不直接信任，需身份检查。

只新增中心说明 `outcomes/diagnostic_completion_v4.md` 和小索引 `outcomes/records/diagnostic_completion_v4.json`，同步summary、run_index、test_summary、两本项目总账及新 `response_v5.md`。旧七份packet按路径/hash引用，不复制一套新结论。数值向量与timeline留ignored，manifest包含input/physical/operator/space/metric/source、ABI、MPI/线程、重建状态和精化策略。

C5必须给出下表；允许混合原因和明确缺证据，不强行宣布唯一root cause：

| 必答项 | 必须交付的量/解释 |
|---|---|
| 第八次拒绝 | 重建输入身份、是否复现、原/增广残差关系、每次精化前后解与残差、通过或仍拒绝 |
| p4最佳表示 | eta_space、投影精度/正交性、L2与curl记录；未合格时明确界限 |
| 细层互补 | H6/S6 对合格 e_perp 的实际作用与成本，不把positive资格代替它 |
| 实际物理粗响应 | eta_G与最佳表示差距、原MR接受、coarse identity；受拒绝影响则标不可判 |
| 跨方法复用 | 已有真实q与新已知误差packet、精化策略区分；新DD可复用但未测试 |
| 后续决策 | 一个有证据的修改对象；若控制不足解释真实失败，明确匹配fine参考这一关键缺口 |

状态至少区分 `REFERENCE_PASS_INITIAL`、`REFERENCE_PASS_AFTER_REFINEMENT`、`REFERENCE_ACCURACY_UNRESOLVED`、`PROJECTION_UNRESOLVED`、`DIAGNOSTICS_COMPLETED_WITH_LIMITATIONS` 和共同 `IMPLEMENTATION/RESOURCE/EVIDENCE_BLOCKED`。任何参考通过都不是外层通过；仍无官方 E/H、R/T/A、体吸收或0.7nm资格。

**本轮完成标准是取得表示、响应、互补的可解释数据，或指出明确且带数值证据的剩余依赖；不是只修复一次 p4 阈值拒绝后再次停审。** 合同内连续推进到C5，再统一回应。若数据支持后续改法，只作一个具体建议；新PC实现与真实三维长跑由下一review冻结，不能自动重开旧路线。
