# trace4 interior6 严格端口消元的有限预算像空间诊断

日期：2026-10-14 UTC。已绑定科学终审、资源终审和 v73 成本账。

## 1 结论

本轮在 same6656 的同一 native 真残差上，用一个 80×80 小因子严格消去端口参数。选定候选通过原端口门：相对缺陷 **2.27544973555564e−17 ≤ 1e−10**。128 步 LSMR 用尽预算后，native field 残差比为 **0.8950707999659866**；scaled/unscaled normal 残差约 **59.005958 / 90.051760**，没有最优性或收敛证书。科学结论仍为 **INCONCLUSIVE**。

本次候选的端口约束已通过，但尚未找到残差比 ≤ 0.02 的合格像空间见证。有限步结果不能证明不可达、给出最优残差下界、确认 trace 缺失是旧 Maxwell 平台原因，或声称 BAL_H 得到改善。没有新外迭代或被接受的物理解。

## 2 固定输入与端口消元

保持同一 108 单元 fine p6、trace p4 与全部 48,600 个 fine interior bubbles。未裁剪 Pt 为 23,976×10,224，其 SHA-256 为 `131167d5770521d4b869c054040047a7f08cbeb58b96a780b60f8976ca726695`。目标含 23,976 个 field 与 80 个 port 分量；原始 PETSc 残差范数 0.013898680225977397，归一化后 field 分母 1.000000000000002，port 范数 5.778000052683001e−13。

- raw 目标 SHA-256：`7a0f317f14c13dfa3235d34cb2586ceeecbdd3a43addd6555ebfb66af84daca2`。
- unit 目标 SHA-256：`3cd6bb01aba4adbcdb87a9b678796cc7a6ba45cd0296d6d3a05b9961147abfce`。
- checkpoint 未修改，未用 saved 右端替代 native 目标，也未延续上一次 LSMR。

native block 为 `[[S_V,Bhat],[-Dhat,Hhat]]`，其中 `Hhat = Hp + Σ Di XiB`，不同于原始 Hp。同一个小 LU 用于正常与共轭转置解。给定 trace 系数 c，令 `t = Pt c`、`alpha = Hhat⁻¹(Dhat t + q_port)`，保留非零 q_port 的端口约束为 `q_port + Dhat t − Hhat alpha = 0`。

设 `v0=[0;Hhat⁻¹ q_port]`、`E0 c=[Pt c;Hhat⁻¹ Dhat Pt c]`、`F=field_selector J A_saved R`，其中 `R=diag(Qb,I80)`、`J=diag(Qbᴴ,Hp)`。求解

`min_z ||F E0 diag(scale) z − (q_field − F v0)||₂`，并取 `c=diag(scale)z`。

saved 算子已含上方耦合，未重复施加 DtN 或 B H⁻¹ D；没有假设 D=Bᴴ 或 Hermitian。选定 retained 向量另经独立 FE native S6 动作、原 homogeneous interior recovery 和原 D 动作核验。

## 3 右尺度和 actual 资格

正实数右尺度取 Pt 每列 2 范数的倒数，范围 0.4472135954999579 至 1.0000000000000029；列范数约为 1 至 √5。没有裁剪、截断或正则化。该可逆参数变化保留 Pt 的 range 和 native field 目标，但改变有限步 Krylov 路径；它不是 A 或 F E0 的列归一化，也不保留未缩放系数的最小范数选择。

源码终审的 89 个有界纯测试通过，46 个 source pins 已绑定并在终审重核。源码审发现的 action-cap 回执缺少 `port80_numeric_factor` 字段问题，已在最终固定哈希中修复并补测试。源码测试和 actual 数值资格分别记录。

| actual 检查 | 次数 | 最大相对误差 | 原门 |
|---|---:|---:|---:|
| Dhat 复伴随 | 3 | 7.295803224673932e−16 | 1e−10 |
| Hhat⁻¹ 复伴随 | 3 | 1.626867962211695e−16 | 1e−10 |
| 右尺度 M 复伴随 | 3 | 4.99547500025556e−15 | 1e−10 |
| 正常小解 RHS 相对残差最大值 | 136 | 1.2977299322469054e−16 | 1e−10 |
| 共轭转置小解 RHS 相对残差最大值 | 136 | 1.671284912025608e−16 | 1e−10 |

这些检查仅支持当前受限动作；没有重新授予任意非零 port 压力 RHS 的通用粗逆资格。

## 4 128 步终态

| 指标 | 值 |
|---|---:|
| LSMR 步数 / istop | 128 / 7，达到上限 |
| native field / total 残差比 | 0.8950707999659866 / 0.8950707999659866 |
| saved 映回同一 native field 范数的残差比 | 0.8950707999660044 |
| 选定 native 与 saved field 像差 | 8.342847804293221e−13 |
| native field / port 残差绝对范数 | 0.8950707999659884 / 6.806550954530763e−21 |
| 重算 scaled / unscaled normal 范数 | 59.005958395391 / 90.0517603061968 |
| 除原 field 分母后的 normal | 59.00595839539088 / 90.05176030619661 |
| LSMR normar | 59.005958395391524，右尺度参数指标 |
| LSMR condA | 7.797841251084291，仅内部迭代估计 |
| c / z / alpha 范数 | 0.000736988160313862 / 0.0008445636384994916 / 4.461868546417249e−5 |
| affine field / b 范数 | 3.9890790823751864e−12 / 1.0000000000000044 |

选定向量的 native/saved 差很小，不是算子范数界。normal 的两种尺度都单列；LSMR normar 不能替代未缩放 stationarity，condA 不能认证全局谱。`image_threshold=0.02` 的见证标志仍为 false；有限步残差不是全局最小值或不可达下界。

## 5 原端口门及两轮比较边界

原始端口动作给出 `||Du||=9.728152432021144e−5`、`||Hp alpha||=9.728152435563323e−5`。原端口缺陷绝对值 4.4271843897310474e−21，原运算尺度 0.00019456304925364467，相对值 2.27544973555564e−17，通过 1e−10。原 D 重构与 native condensed port 残差分开计算，其浮点范数不要求完全相同。

| 有限预算候选 | 残差比 | 原端口门 | 科学状态 |
|---|---:|---:|---|
| 上轮自由 80 port，未作本轮右尺度 | retained 0.8537943314895308 | 0.9394413894559671，FAIL | INCONCLUSIVE |
| 本轮严格端口消元，Pt 列范数右尺度 | field 0.8950707999659866 | 2.27544973555564e−17，PASS | INCONCLUSIVE |

这里只能并列有限预算候选。两轮同时改变约束和右尺度，目标分量也分别为 retained 与 field；不能隔离端口约束的因果影响，也不能将残差差异解释为最优残差变化、空间变差或 PC 提升。上轮 port FAIL 保留，本轮通过不倒改历史。

## 6 实际工作与资源成本

本轮耗时 **74.776561388018 秒**，采样进程树峰值 **2,408,468,480 B**，294 个资源样本、63 次 admission 全部通过；child exit 0，清场后 remaining 为空。进程成功退出不等于最小二乘收敛。

| 动作 | 次数 |
|---|---:|
| LSMR M / Mᴴ | 128 / 129 |
| M / Mᴴ 总计 | 131 / 133 |
| F / Fᴴ 总计 | 133 / 133 |
| Dhat / Dhatᴴ | 135 / 136 |
| Hhat 正常解 / 共轭转置解 | 136 / 136 |
| 80×80 小因子 | 1 |
| native 输入 / 选定 native S6 | 4 / 1 |
| 选定 homogeneous recovery / 原 D | 1 / 1 |
| global K、JOB1、global numeric、global factor solve | 均 0 |
| H3、BAL_H、CG、outer | 均 0 |

原 fine local LU bank 仍存在，不能把“无 global numeric”写成“完全没有因子分解”。各 image/小解回调硬上限 136 未提高，128 步后没有追加 LSMR。

原限制保持：6 GiB AS、8 GiB tree、host 可用至少 1 GiB、zero swap、600 秒、磁盘剩余至少 4 GiB、输出 128 MiB、MPI 1、线程 1、单科学子进程。联合 CSC/LS/allocator/diagnostic 预约 1,091,418,852 B，比上一阶段增加 16 MiB 的小端口与尺度 scratch。AS 检查实际 VmSize 加 named extras；tree 另外保留 ELF 和安全余量，二者不混用。

资源审重算最大 projected tree 为 4,361,104,164 B，最小 host available 为 6,980,517,888 B，最小 disk free 为 13,037,912,064 B；最大记录 VmSize 快照 3,117,477,888 B。快照不是连续峰值，不借清理推断已释放的 allocator 页面。11 个已知 owner 清理回调正常返回，加上 supervisor 清场；没有宣称所有隐藏的部分构造 native handle 都被显式销毁。实际普通输出 3,368,616 B。

本轮只新增 74.776561388 秒，嵌套动作时间不重复相加。此前六次 trace4 尝试合计约 947.759838753 秒，含本轮七次约 1022.536400141 秒。全项目 v73 已知终态科学时长 **21231.991389564137 秒**，含中断下界 **29145.98367240712 秒**。二者都不是精确总墙钟；准备、审核和等待未完整计量，不能记为零，内存峰值也不相加。

## 7 独审范围与保留失败

四个 complex128 小 NPY 只存本地，合计 **1,318,784 B**，最大单件 385,024 B。`coarse_y` 是 10,224 个物理 trace 系数 `c=scale*z`，不是 z，也不包含自由的 80 个 port 参数；另外三个是长度 24,056 的 native image、native residual、q_native。没有持久化矩阵或因子，没有上传 NPY；配套 JSON 仅列元数据和哈希。

独审以标准库核查四件的头部、文件与 typed 哈希、有限性和范数，逐分量验证 `native_image−q=native_residual`，最大差为 0；重算 field 残差比 0.8950707999659855 与 actual 回执一致。独审没有重新施加 native S6，没有读取大型 CSR/Pt，也没有重算 normal 动作；小解与伴随数值依据固定源码和 actual 标量回执复核，不伪称独立算子重跑。

原 g=1 压力资格 FAIL、same checkpoint raw MISMATCH、saved/native PC raw FAIL、prediction raw FAIL 全保留。`all_diagnostics_passed_claimed=false`，`field_accepted=false`，`solution_accepted=false`。单次端口门通过不覆盖这些检查，也不证明 108 单元或 hp 收敛。

本轮止点是发布端口合法但 128 步未决的结果；没有继续最小二乘或进入外迭代。任何后续数值需要新的明确方案、源码与资源审和准入。

## 8 固定证据索引

路径相对本地证据根 `hp_resume_20261013`。本次只上传此中文报告和配套小 JSON。

- `phase4_trace4_interior6_port_eliminated_image_source_review.json`：23104 B，SHA-256 `649f4abed20df47193e9bb1cc8dfcc42333ac9d033f97c4adb789b9abac9ea11`。
- `phase4_trace4_interior6_port_eliminated_image_attempt01/summary.json`：1224 B，SHA-256 `c4d1a114c9d4bc25d31c2bf306c3edc8486b8d3a53d59ce33d941c4e53cd9bf6`。
- `phase4_trace4_interior6_port_eliminated_image_attempt01/result.json`：229231 B，SHA-256 `4795a480e5fa5ab77d596e1a64a5f23ec05c1bebfc005e11f3d60a8eb10728e5`。
- `phase4_trace4_interior6_port_eliminated_image_attempt01_terminal_review.json`：31145 B，SHA-256 `8904a925ff43c83b92e2f7ba01e185771be8542377f31710744995d2890e543a`。
- `phase4_trace4_interior6_port_eliminated_image_runtime_review.json`：5794 B，SHA-256 `a1e6c0c51101cdd0a759538f80e08a809854a7c69dd7045c60f2c3d5eef2545f`。
- `phase4_execution_ledger_v73.json`：51578 B，SHA-256 `f957545b9e59dcc8c83305028abe01650eab6ade09647266a3a27b6dbca752c6`。
