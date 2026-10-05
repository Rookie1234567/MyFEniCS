# Review V10：B0 p6 逆算子、物理解与边界证据综合

## 读法与结论

B0 是 0.7 nm 工程方案的小型真实三维周期模型：网格有 80 个单元和两单元宽的真实三维 void，p6 表示六阶有限元近似，沿 y 周期包含四个 q 分支。它用来检查新 p6 路径的边界耦合、线性求解和物理能量门是否闭合；它不是原始 50×25×140 nm 目标设备。

V10 结果要分三层读：逆算子分量测试通过；p6 线性系统残差通过；由该解恢复出的物理能量闭合没有通过。因此目前没有 official R/T/A，C 依 Review V10 §5 保持 `HELD_NOT_RUN`。这里的“通过”仅属于各自所列的门。

## p6 逆算子分量检查

逆算子分量负责把周期模态边界数据映射回有限元行；检查它有助于判断 p6 solver 的局部代数接口是否能处理全端口与内部未知量。它覆盖通用 RHS、36,000 个内部行、全模态端口 RHS、物理规则 RHS，B/D完整32,060行见证、generic complex input和nonzero port RHS属于A代表边界链，不能记为B0全局逆算子的逐行资格。这里只在 preconditioner 背景中填回缺口，用四个 y 相位分支的完整 p6 准确 LU 为真实三维缺口 target 计算修正方向；target 与 RHS 不变。四个 factor 同时保留并恢复全部 36,000 个内部未知量，增加内存和 setup 成本；三步残差通过不代表物理能量通过。A 的 q60 指积分分辨率，B0 的四个 q 指 y 周期相位分支，二者不是同一指标。

| 量 | 实测 | 门限 / 解释 |
|---|---:|---|
| 全端口通道 | 532：top 266、bottom 266 | 通道数，不是顺序方程数 |
| 内部 / trace 行 | 36,000 / 16,992 | 存储/独立行 55,950 / 52,992 |
| 每个 q 的增广 trace+port 行 | 4324、4400、4400、4400 | 四支全部保留 |
| 最大 q 真残差 | `7.493923678060789e-12` | `<1e-10`，通过 |
| regular reference 问题抽样原方程残差 | `1.465060265308628e-11` | `<1e-10`，通过 |

分量检查通过说明相应右端项与矩阵行的代数接口在测试覆盖内闭合，不说明该物理候选能量守恒，也不构成生产路径资格化。

## p6 物理求解与官方结果门

p6 候选运行三次迭代。显式真残差为 `1.6089774391665316e-8`，释放后原生 A6 witness 为 `1.6089791915820923e-8`，均低于 `1e-6` 求解门。纯 `ksp_solve_phase` 实测 `4.899454752 s`；父级 solve phase `6.441171838 s` 还含外围动作，不能称为纯 KSP 时间。

恢复保存场后，能量闭合误差为 `6.581916436299018e-5`，高于 `1e-5`；吸收一致性误差为 `6.581916436306369e-5`。能量闭合检查确认散射功率与体积吸收之间是否守恒，它独立于线性方程残差。因此虽然线性系统求解通过，物理场仍没有 official result。

| 保存场诊断值 | 数值 | 状态 |
|---|---:|---|
| R | `0.984273608092677` | 仅诊断 |
| T | `0.014174698896746551` | 仅诊断 |
| A_balance | `0.0015516930105763937` | 仅诊断 |
| A_volume | `0.00148587384621333` | 仅诊断 |

p6 worker 在输出阶段因缺少 `pyvista` 以 exit 4 结束，原分类 `WORKER_FAILED` 保留。后续恢复流程从已保存数据重建输出并运行物理检查；恢复成功不抹除 worker 失败，而能量门失败也必须单独保留。

## p4 控制的比较边界

p4 控制仍求同一个 p6 target，变化只有 preconditioner。它 2048 次迭代后 KSP reason `-3`，A6 true residual `0.966131083707469`，高于 `1e-6`；KSP-only 时间 `1519.454145885 s`。由于它没有通过同一残差门，这不是匹配的成功性能对照，不能据此得出 p6 速度优势。

## A 边界的连接证据

原 worker/report 的 p4 top 为 PASS；旧 checker 因 32,060/16,030 通道数混淆将其误标为 FAIL，旧记录保留不改。V1 frozen-scale recheck 再次确认 p4 top 为 PASS，并确认 p6 top 仍未通过。A代表边界链覆盖完整32,060个B/D行、generic complex input和nonzero port RHS；该覆盖不能解释成B0全局逆算子的B/D逐行资格。V2 补齐 bottom：p4 top/bottom 已知内部场恢复前向相对误差分别 `4.071005827429115e-13` / `3.318404914520256e-13`，小于 `1e-11`；p6 top/bottom 分别 `2.202932653970648e-11` / `2.42442721473547e-11`，高于该恢复门。它们是已知内部场恢复前向误差，不是原方程残差；原方程残差门已通过。

q60 五类有限见证均通过；冻结saved_q60_apply分母`5118.679535729753`、relative action error `9.063390130105725e-15`、n0最大逐模相对值`3.3410810842083564e-15`保留。冻结q60的原boundary compact入口为[`review_v10_boundary.json`](records/review_v10_boundary.json)：Git blob `7420124f261d8bc638254d7fedc2db4501987e9b`（a4ac46a），文件SHA-256 `1c619be21ec6ef0c757916fdeac0fa7a5863718beb0c3fd8f4068d3173895cec`；较早V9入口也保留于[`review_v9_w1_closeout_v1.json`](records/review_v9_w1_closeout_v1.json)。旧 q30 误差 `5.705909332721303` 超过 `1e-10` 也不自动否决 q60。完整 A 当前未资格化的数值原因是 p6 恢复门失败；B/D 行、通用复输入和非零端口 RHS 已覆盖。完整浮点定理属于适用边界限制，不是 V10 前置门。

原始A worker用时`57.269548677955754 s`；其watchdog supervisor wall为`71.49506455799565 s`，tree RSS `762998784 B`、swap 0。V1 首次底部续算因 watchdog 文件夹与 runner 输出目录冲突，在数值底部工作开始前以工程错误退出；V2 使用新空目录后完成。V2 watchdog 用时 `83.070806061 s`，tree RSS `744566784 B`，cgroup peak `928624640 B`，swap 0。

## 资源与未运行范围

B0 p6 worker 全流程 `1051.699122267 s`；同时进程树 RSS 峰值 `3713953792 B`，cgroup 峰值 `4101464064 B`，swap 0。factor allocated/used、setup 与 factor 分阶段耗时是 unknown/null，不是 0；释放后 inventory `used/peak=0` 只说明采样时对象已释放，不能代表求解期间四个 q 的同时驻留内存。输出恢复全流程 `33.431334133 s`，tree RSS `1193611264 B`，cgroup 未记录。

C/Gx560、完整 15,232 单元模型、自动全尺寸路径、原尺寸 A 链的 global MPC/target-scale mapping 和完整 cold-flow 端到端资格化均未运行；B0 小模型已有 native/MPC 身份。50×25×140 nm 目标保持 `NO_GO`/未资格化，这表示目前没有足够证据满足目标，而不是数学上不可能。

主要机器记录：[`review_v10_manifest.json`](records/review_v10_manifest.json)、[`review_v10_boundary.json`](records/review_v10_boundary.json)、[`review_v10_p6_inverse.json`](records/review_v10_p6_inverse.json)、[`review_v10_physical_comparison.json`](records/review_v10_physical_comparison.json)、[`review_v10_cost_and_repairs.json`](records/review_v10_cost_and_repairs.json)。
