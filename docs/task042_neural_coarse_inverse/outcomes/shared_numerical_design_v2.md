# 共享首轮数值设计与 F1 实测

本记录是用户授权下的实现和预先登记的实验设计，不修改原任务书、不代表 F0 已获正式 review。授权范围见 [共享运行授权](shared_authorization_v2.md)。所有资源与成本均标为 shared-workstation；邻负载和冷暖缓存不一致时，性能比较为 inconclusive。

## 已完成的真实接口

运行源码为 `cca180f875bd22146f2d30fa4d004e372135dfbb`，clean 启动，进程树已清理。252 cells、p6 storage173802、p4 storage53084、trace+port21824、80完整端口。独立原 A4 与 PᴴA6P 的相对差为 3.366065072840215e-15；p4 凝聚矩阵与独立单元作用相对差为 2.3566154699905024e-16。非零内部及端口 RHS 的原 A4/A6、端口、恢复与恒等式检查全部通过 1e-10。

固定传统方法 B0 只对互不重叠的512行小块分别求逆。它省去全局因子，但块之间的耦合仍需迭代消除。43个 patch、patch 因子177886464 bytes、单元/端口因子3469728 bytes；构建前后没有 global p4 LU，借用原 p4 矩阵及已有原方程审核作用，没有私有审核 CSR。7个非零 RHS 在固定256步后原 A4 相对残差为0.7623–1.9133，未达到1e-10；零 RHS 精确通过。这个停滞是 baseline 负结果，不调整 patch、shift、restart 或容差。

整树采样峰1641930752 bytes，swap0，1242.0434713200084秒；包括真实 p6 接口构造、p4 构造、7次迭代、全部监督及清场。它不能直接与后续只构造 p4 的成本比较。完整身份、每个 RHS、失败方向及 hash 见 [F1 实测记录](records/f1_real_components_v2.json)。

## Teacher 与表示的登记

后续粗层阶段不重复构建 p6 栈；仅在原 F1 接口通过、其 clean source/文件 hash 和退出清场都满足时，重建同一个原 p4。必须逐项核对网格、材料、MPC、80通道、积分规则，以及逐行原 p4 CSR 内容 hash `150f18e26f15783726f2ffeb362ef053450962a16fff13d5241cc93c8d018560`；任何差异即停止，不能换算子继续。

Teacher 在单独进程使用离线 MUMPS，先做 symbolic 预测 Gate，再做 numeric；OOC关闭、workspace cap8192 decimal MB，仍受整树16GiB限制。先独立审核 F1 的8个 RHS，随后 train256/validation64/heldout64，共384对，每对复算原 A4、port、internal 与 native/Schur恒等式，统一1e-10。每批最多32 RHS，规范化尺度和 full/port RHS一并保存。Teacher 从未构建 B0 或部署候选，退出后才允许 oracle/训练/部署。

划分按 seed 与整个 problem/轨迹：F1 的420110 synthetic family及所有相邻迭代残差只归 train；独立420200补 train，420300只 validation；真实 PHb6 及其整条 F1 内层轨迹、420400及其所有相位/幅值亲属只归 heldout。严格粗返回用 heldout 前16项，包含真实早期/后期、零、非零内部、非零端口、相位和幅值。Validation 决策不读取 heldout 的数值指标。

POD把训练中的困难修正压成最多128个方向；通过小规模非学习最小二乘先检查这些方向是否有用。比较 rank16/32/64/128。基、编码/解码及在线 buffer 上限512MiB，不保存全部 teacher field 到内存。线性路线在同一输出空间中最小化完整原 A4 残差；神经路线使用相同原残差编码和同一输出空间。完整原方程映射须再与独立 native A4 配对核验，训练 loss 保留不能被投影表示的残差分量。

在生成 teacher 或观察 oracle 数值前登记诊断正信号：rank128 的 validation 中，困难修正投影后误差范数中位比<=0.90，且最优原 A4 残差范数中位比<=0.99，两项同时满足才推进 F3。这是本次有限表示研究的操作判据，不替代任务书1e-10严格返回 Gate；最高 rank 无此信号记 REPRESENTATION_NEGATIVE，不增大网络或基。部署 rank预先固定128，网络仍为已登记的两层 hidden64、FP64、seed420500、最多300epochs和2小时有载预算。

## 轻测试

独立复数 SVD 配对验证流式 POD；原方程 Gram loss 与全维直接计算配对，覆盖投影空间之外的残差及实虚通道。加既有 coarse protocol/有界 B0 回归，共39 passed；整树88592384 bytes、swap0、2.4111145570059307秒。测试是 pure-array，不替代尚未执行的 teacher/oracle Gate。
