# Task032 最终答复 v1

## 1. local migration and branch identity

```text
new local repository = C:\Users\admin\Desktop\Code\fenics_v3_hybrid_FEM_modal
origin = Rookie1234567/MyFEniCS
branch = codex/20260714-task32-hybrid-fem-modal-direct-baseline
Task031 clean merge base = dae03170b0cdd87f2d72769aea7ce04e32acce2b
ordinary default changed = false
classification = hybrid_direct_engineering_success
```

旧目录保持历史基线，Task32 的代码、正式记录和文档只写入新仓库。实现主提交为
`735774473e54415ab5393f2d2cbc9c8d7d2a24e6`；修正内存 provenance 后的正式
内存源提交为 `793354af0ac72cbfe1c6eb1030b2438afe10c101`。

## 2. frozen physical model

冻结 13.5 nm、验证过的 Si、50 x 25 nm 双周期单元、17 x 25 x 120 nm Si block、
10° 掠入射、phi=0、S 主单点、p2 Nédélec、MPI4 和 MUMPS direct。域分解接口固定
在 z=10/110 nm，中间 100 nm 为截面不变模态区。未修改材料、外部 Fourier-DtN、
衍射级或端口定义。

## 3. theory-to-code mapping

```text
2D cross-section QEP -> right/left passive modes -> stable two-sided propagation
-> matched Nedelec trace projection -> augmented or modal-Schur direct
-> local plus modal E/H reconstruction -> R/T/A, orders and volume absorption
```

存储合同是 `O(N_interface*M)+O(M^2)`；禁止 dense `N_interface^2`，禁止 rank0
完整场或完整模态 gather。中间区不再生成 3D volume mesh。

## 4. eigenproblem implementation and validation

`N1curl(p2) x Lagrange(p2)` 混合截面空间构造
`K0 + beta*K1 + beta^2*K2`，通过双 Floquet `u=Cq` 和 `C^H K C` 稀疏约化，
使用 SLEPc PEP/TOAR。air、homogeneous lossy 和当前 patterned cross-section 的解析
beta、QEP residual、Bloch phase、orientation、正反 pairing、归一化和 MPI ownership
均已有 clean Phase 2 record；完整 eigenvector 未聚集到 rank0。

## 5. mode classification/normalization

传播模优先按 z 向 Poynting flux 分类，near-zero flux 或纯衰减模按被动衰减分支
选择。左模来自显式 adjoint QEP，使用 `Q'(beta)` left/right biorthogonality；
near-degenerate group 使用小 block inverse 与子空间 Gate。宽 M 漏斗前先求 `2M`
candidates，再过滤成精确 M 个正、反向被动模；不足时 fail closed。

## 6. stable propagation

中间 100 nm 使用正、反向 two-port 对角传播，不保存 growing inverse。37+63 nm
composition、reflection-free block、reciprocity/passivity 与强衰减下溢合同全部通过。

## 7. interface projection

匹配 3D/2D p2 Nédélec trace，bottom/top 局部外法向与 modal 外法向显式取反。
Petrov left projection、right reconstruction、round trip 和近简并子空间 Gate 通过；
通信只传接口插值点和两个复切向分量。

## 8. augmented direct result

正式 h5/h3 M120/M160 augmented 记录来自 clean SHA `7357744...`。M160 结果：

| mesh | R | T | A_balance | true residual |
|---|---:|---:|---:|---:|
| h5 | 0.0890210691064 | 0.4425867427429 | 0.4683921881508 | 2.55e-12 |
| h3 | 0.0046128199040 | 0.5836509402052 | 0.4117362398908 | 2.60e-12 |

两档的 interface projection、variational traction、物理界面 E/H、体吸收、能量闭合
和五个选面 Gate 全部通过。

## 9. modal-Schur result

h5/h3 M160 的 Modal-Schur modal coefficients、上下局部解、接口投影、R/T/A 与
augmented 的差异均远低于 `1e-9`。只形成 `320 x 320` modal Schur，使用一次
factor context 的 321 个 multi-RHS；没有 dense interface square 或完整 gather。

fast 生命周期同时保留 bottom/top 因子；memory-minimal 按 bottom factor、贡献、
释放，top factor、贡献、释放，modal solve，再逐侧 refactor/recovery 执行。

## 10. truncation convergence

早期 M20->M40 最大 total delta 约 `2.25e-5`，证明 M6 表面平台不足。正式
M120->M160 结果：

| mesh | max total delta | max significant complex-amplitude relative delta |
|---|---:|---:|
| h5 | 6.2395e-14 | 1.4793e-10 |
| h3 | 1.2212e-14 | 1.3335e-10 |

两档都通过 mandatory、strong、significant-order 和 interface residual Gate，选定
`M=160` per direction。

## 11. full-3D comparison

h3 M160 Hybrid-minus-full3D R/T/A 为
`-2.1150e-7/-2.4170e-6/+2.6285e-6`；体吸收差 `2.6285e-6`，界面 E/H 最大
相对 L2 为 `2.5037e-8/4.8169e-4`，五个选面 E/H 最大相对 L2 为
`9.9644e-5/7.7981e-4`。h5 同网格主阈值也通过。h5 与 h3 full-3D 本身差异大，
所以只证明各自同网格 Hybrid 对照，不宣称 h5--h3 网格收敛。

## 12. angle/polarization smoke

正式 `30/30 pass`：h5 为 1--10° S/P，h3 为 1/3/5/7/10° S/P。每点重新计算
QEP 与方向分类，并验证参数 round trip、complex128、无 full gather、Hybrid algebra、
有限 R/T/A 和逐衍射级输出。该批次使用 M=4，只是参数入口 smoke，不是整个角度
区间的 production qualification。

## 13. memory and timing

六条独立 MPI4、M160、0.25 s simultaneous RSS 记录均数值通过、零 swap、无
warning/termination，且保存 clean source 与实际镜像 ID。

| mesh/path | worker RSS GiB | cgroup current GiB | solver total s |
|---|---:|---:|---:|
| h5 augmented | 1.865 | 1.584 | 70.72 |
| h5 Schur fast | 1.755 | 1.160 | 63.01 |
| h5 Schur memory-minimal | 1.698 | 1.061 | 60.91 |
| h3 augmented | 3.853 | 3.215 | 102.58 |
| h3 Schur fast | 3.998 | 3.362 | 111.97 |
| h3 Schur memory-minimal | 3.224 | 2.586 | 99.69 |

h3 memory-minimal 相对 augmented 降低 `16.31%`；h3 fast 反而升高，证明收益
来自顺序 factor 生命周期，不是“Schur”标签本身。h2 最佳候选仍是
memory-minimal，但网格尺度预测为 `5.365/6.170 GiB`（中心/上界），MUMPS
factor-payload 预测为 `11.647/13.394 GiB`。两种方法都未过 4/5 GiB Gate，
因此 `h2_unlock=false`，h2 未运行，也没有可报告的 h2 实测峰值。

## 14. negative results

保留了 candidate 方向混入、M120 MPI context 耗尽、h3 缺接口平面、早期 M 不收敛、
h3 Schur-fast 不省内存、内存摘要镜像 ID 录入错误和 h2 预测失败。每项均有根因、
修复或停止边界；没有修改物理模型来制造通过结果。

## 15. changed files

主要新增物理场重构、Modal-Schur direct、正式 funnel/smoke/memory/prediction runner、
最终 Gate 模块、test_40、Case080 记录及 walkthrough。完整清单见
`outcomes/changed_files.md`；重型 artifacts 保持 Git ignored。

回归结果：Task32 serial/MPI1 `41 passed`，MPI2/MPI4 每 rank `29 passed,
2 skipped`，全量 serial `212 passed, 10 skipped, 299 subtests passed`，最终
Case080 checker `302/302 passed`。

## 16. merge recommendation

```text
recommendation = push branch for independent review
merge now = no
reason = implementation and evidence complete, but project workflow requires review acceptance first
```

建议审阅重点检查：物理 H/吸收符号、h3 精确接口插入、Schur 因子生命周期、
内存 source/image provenance、h2 fail-closed 决策和参数 smoke 的声明边界。

## 17. next Task033 decision

技术结论是 `ready_after_review_acceptance`：Task32 已证明 Hybrid 数值正确且 h3
存在 `16.31%` 结构性内存下降，满足任务书允许进入 Task033 的前提；但 h2 未解锁，
所以不是 strong-memory success。必须先接受本分支 review 并合入 master，再启动
Task033。

Task032 的十个后续问题回答如下：

1. 中间 100 nm 可以被截面模态可靠替代；h5/h3 同网格场和 R/T/A 均通过。
2. 当前主点需要每方向 M=160；M120->M160 已强收敛，不能用早期 M6 代替。
3. z=10/110 nm 接口合适；h3 应插入精确平面，不能移动到近似坐标。
4. augmented 是最直接的正确性 reference；memory-minimal Modal-Schur 是推荐内存路径。
5. h2 没有实测峰值；两种预测均失败，因此任务书禁止运行。
6. 主要峰值来自 local MUMPS factors 与其并存/填充；Schur 本体和 projection 较小。
7. 几何拓扑、接口路由和符号装配可复用；角度改变后 Bloch/QEP、模式分类、传播因子
   和数值因子必须重算；S/P 可复用同一模式基下的线性结构，但需重新组装右端与输出。
8. Task033 应固定 10/110 nm 匹配接口网格，优先只对 local 3D interior 做 h/p 自适应。
9. Task034 应面向最终 local-FEM + `2M` modal core 的 Hybrid/Modal-Schur 块系统，
   以 full residual 和场连续性为资格，而不是回到完整中间 3D 单体。
10. 现在不应直接缩短到 0.7 nm；先完成 Task033/034，并处理色散、网格尺度与 QEP
    模态增长后再评估，否则 h2 预测已经表明资源外推不安全。
