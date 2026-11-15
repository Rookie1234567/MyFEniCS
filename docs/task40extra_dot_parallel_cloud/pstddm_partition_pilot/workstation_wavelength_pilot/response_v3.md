# p6凝聚直接解：Response V3

**已用保存场和残差定位并修复入射载荷积分不一致；修复后的h10验证完成装配及MUMPS symbolic，在numeric前因当前动态内存额度不足停止，没有新解。** 原retry1完整残差仍判FAIL，h7.5及同网格PSTDDM比较未启动。本轮没有降低`1e-10`精度门、改变材料/模式/网格、增加精化或干预邻项目。

## 保存数据给出的原因

模型保持13.5nm、50×50×140nm单胞、居中有限宽Si块、phi90/S、p6/h10、504单元和612端口。静态凝聚先消去单元内部未知量，再求界面和端口，最后恢复完整场；最终检查必须使用同一原方程的载荷。

旧生产入射RHS使用自动生成的15阶积分，而独立完整残差使用配置的28阶积分。先复用旧场/RHS/残差定位高误差行，再只补两种入射载荷向量，未重新建立体积矩阵或factor。前125行占旧残差平方的99.0217%，均映射到顶端口表面，支持这一定位。

令旧保存残差`r=A*x-b28`，载荷差`delta=b_auto-b28`，则`r-delta=A*x-b_auto`。

| 保存数据指标 | 实测值及边界 |
|---|---:|
| 原完整残差 / 原RHS范数 | `3.2085634887236534e-7`，大于`1e-10` |
| 载荷差 / 原RHS范数 | `3.2085621535624343e-7` |
| 旧残差与载荷差的方向余弦 | `0.9999999179892587` |
| `r-delta` / 原RHS范数 | `1.299454705721522e-10`，仍超门 |
| 旧凝聚系统诊断残差 | `1.2779043655559762e-10` |
| 修复后新解的原完整残差 | **NOT_RUN**：numeric尚未开始 |

`r-delta`表示旧解相对实际15阶载荷的剩余，并非“改成28阶后的新解残差”。因此本次已解释主要载荷差，但没有证明全部数值问题消失，更没有推翻旧FAIL。

修复使本p6入口显式采用28阶入射积分，普通调用默认不变。真实入口原先还误要求外部solver port，已窄修为允许固定p、已装配的内部direct；variable-p、非装配和action-only路径仍拒绝。JIT只接受已审查的CSV-only及guard-only精确旧/新文件hash对，其他身份检查保留。

## 修复验证及真实运行

最终科学源码：`afd415d3f5eae03e30d223d1d794008812891cd5`。

| attempt | 完成到哪里 | supervisor完整父时间 |
|---|---|---:|
| retry2，source `2b7dcd78e54ffde890a15fb49badcfdb2595630b` | JIT源hash拒绝，worker未启动；后补精确CSV变更资格 | 0.6686448389664292s |
| retry3，source `619e6d243ea7cbc904b0ad69e54fadb308c1a81b` | mesh/MPC/forms后被错误入口guard拒绝，无矩阵/factor | 10.891114233061671s |
| retry4，source见上 | 全部612模式、凝聚增广装配、symbolic完成；numeric准入停止 | 763.1766434162855s（12.72分钟） |

retry4输入为`input/pstddm_p6_convergence_workstation/13p5_h10_direct_retry4.dat`，SHA256 `3da34ca66b6c96309b0d565b67d2ae355892bbccc83836d43c6b07d72d55fe3c`。服务`pstddm-p6-h10-retry4-20261115.service`，invocation `68e58469e6324d7abbe675dcac4e824e`。运行时间为2026-11-15 08:56:52至09:09:33（Asia/Singapore）；supervisor总父段还包含清场/hash，不能用两个墙钟时间差替代。

正式记录原样保留`FAILED / child_returncode_1`及worker异常`MUMPS_INCORE_WORKSPACE_CAP_BELOW_ANALYSIS_REQUIREMENT`。事后依据原始预算记录分类为**RESOURCE_CONTROLLED_STOP_BEFORE_NUMERIC**，不是数值不收敛。没有把旧回执改为PASS或伪补新场。

## 为什么64GiB任务cap仍不能分解

cap只是本任务上限，并不承诺共享主机能提供同样多的空间。此次装配期间宿主可用内存下降；numeric还须给宿主保留400GiB，并预留转换、后续对象及安全余量。

| numeric准入项 | 原始值 |
|---|---:|
| 任务cap / 宿主保留线 | 68,719,476,736 / 429,496,729,600 B |
| 观察时宿主MemAvailable | 450,226,487,296 B |
| 本任务live tree+supervisor | 3,018,309,632 B |
| task侧 / host侧可新增空间 | 65,701,167,104 / 20,729,757,696 B；取较小者 |
| 转换上界 / 后续共驻 / MUMPS外部余量 | 2,078,065,632 / 4,294,967,296 / 268,435,456 B |
| 独立安全margin / 观察slack | 536,870,912 / 16,777,216 B |
| 最终工作区预算 / ICNTL(23)候选额度 | 13,534,641,184 B / 13,534 MB |
| INFOG16/17预测需求 | 22,457 MB；预测，不是实测factor内存 |
| 未取整预算缺口 / 整MB额度缺口 | 8,922,358,816 / 8,923,000,000 B |

正确使用的是64GiB profile，未误落入10GB默认。限制来自host侧动态余量；watchdog没有触发`MemAvailable < host reserve`，但预留未来分解对象后额度不足。没有执行numeric、MatSolve、原残差或新物理输出，也没有改用OOC/BLR。按本次同阶段对象和余量算，MemAvailable至少需459,148,846,112 B才满足这个预测门；这是条件推导，**不是下一场放行保证**。

| retry4资源与清场 | 实测 |
|---|---:|
| 同时进程树RSS采样峰值 | 4,102,488,064 B，elapsed 757.8453578026965s |
| cgroup current采样最大值 | 4,404,195,328 B；不等于连续采样外的绝对峰 |
| systemd返回MemoryPeak | 3,130,531,840 B，与采样矛盾，原因UNKNOWN，不采用为真实峰 |
| task swap / 最终后代 / MainPID | 0 / 空 / 0 |
| 最终可用磁盘 | 388,133,281,792 B，高于380GB线 |

宿主已有swap另列，不能冒充本任务swap。共享主机余量变化不能未经证据归到某一邻项目。全过程没有操作邻项目。

## 成本、测试与证据

- 保存残差到网格行映射：imports后12.811645520851016s，RSS峰724733952 B；其中MPC 2.2063s，不与父时间重复相加。
- 两种入射载荷捕获：进程25.786462409s；装配子时间和峰值未记录，保持UNKNOWN。向量已先保存，随后JSON序列化失败只重做报告，未重装配。
- 保存向量报告重建：1.7102079540491104s，RSS峰334151680 B；未再运行FE求解或factor。
- 最终原ABI定向验证15项通过，测试父段0.7355273421853781s，RSS峰219766784 B；service父段2.777s。真实内部入口走过修复guard，限制路径及缓存身份反例仍拒绝。此前夹具前置门/临时路径两项失败与21项通过记录保留，修夹具后只复验相关范围。没有全仓测试或CI。
- 五次正式attempt的supervisor费用累计3162.9574122633785s，21600s账面剩18437.04258773662s。准备、诊断和测试另列，未记录成本仍UNKNOWN，不能宣称这是完整冷流程费用。

完整预算、逐attempt source/input、原始文件hash、测试收据与主控只读预算/清场核算见[紧凑证据](outcomes/records/p6_h10_diagnosis_retry4.json)。正式根为`/home/fenics/Projects/laptop_share/benchmarks/artifacts/pstddm_workstation/runs/p6_h10_direct_13p5_retry4`；其`mumps_symbolic/symbolic_preflight.json` SHA256为`abee139b25d2f9a65430bf310e26490f64748ae6481f2bfcbd8f4ff4773520d2`，`supervision.json`为`66f75ffa233de05123653ece2071e105e5435d684b57e8d3c8571a5907bbef08`。

旧残差与新增载荷向量、metadata和诊断报告保存在`reviews/p6_h10_direct_13p5_retry1_saved_residual_distribution_20261115`。载荷NPZ SHA256 `5a59e56d9ad97992ccb339b9107fcae850b4b8c3581e9c9bc14e5b05e5e4fffb`，只读报告SHA256 `26054d4d827ef5a4dd3199971b656f006bc5c080ecbdcb9dde9dfff2631c0411`。旧retry1场与失败完全保留。

## 下一断点

先等待共享资源条件改善，并重新核实际host/cgroup、完整未来对象及时间账；不原样重复当前资源条件，不降低保留线。源码、输入和合格JIT可复用，但未启用完整CSR checkpoint，旧factor已释放，不能声称可直接从numeric接续。没有启动retry5。

修复后的完整残差、体吸收/能量闭合仍未知；即使新残差通过，也须完整物理门通过后才能推进h7.5和收敛比较。旧解相对实际载荷的约1.30e-10余量也保留，不能预报修复后的PASS。本轮未证明网格收敛、PSTDDM省内存或完整工程成功，只推当前执行分支，不合并master。
