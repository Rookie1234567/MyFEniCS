# PSTDDM pilot：固定构造与运行前规格

此实验将昂贵的全局 Maxwell 逆换成相邻两个物理分层的局部逆，把更远源的作用逐层传递。局部人工吸收层 PML 只帮助局部求解，不改变最终验收的原始 Floquet–DtN 方程。它增加局部网格、装配、因子和迭代成本；增加分区不保证总内存降低。

## 当前权限和身份

新 task.md 是用户 2026-11-11 附件原文，明确授权本独立小试验，优先于父目录已结束任务的时间窗口及“无新heavy许可”等旧状态。仅 own branch `task40extra_dot_parallel_cloud`，实际 base 为 `2c7aa97f4746c5de0545cf511908321b356a74df`，远端在开始时重新核对未前进。当前云端 fresh clone 从此 own branch 建立并跟踪 origin；历史 connector 发布未验证 canonical 的事实不改写。其他分支、Task44数据及用户电脑不触碰。

## 固定模型

0.7 nm；Si n=0.9998851703688496+4.3236152269189515e-6 i；mu=1；空气n=1。材料继承 `docs/task40extra_0p7nm_engineering/outcomes/material_and_geometry_identity.md`，不增加损耗。周期x/y均2.5925925925925926 nm，物理z为[-0.5185185185185185,0,3.111111111111111,6.222222222222222,6.7407407407407405] nm。有限x/y Si块宽0.8814814814814814×1.037037037037037 nm，高6.222222222222222 nm，底为Si衬底；材料同时依赖x/y/z，并非y不变模型。具体X/Y/Z和边界对齐原样来自已备份的120-cell 0.7nm模型，在 `src/solvers/pstddm_model.py` 冻结。

入射theta=89°、phi=90°、s、单位电场；complex128 Nédélec p2；3×10×4=120 hexa cells；双Floquet相位由原cfg.kx/ky及周期产生；m=-5..5,n=-9..9、上下端口s/p共836模式，原生boundary-plane归一化、quadrature28，无数值裁剪。物理体积分/局部算子quadrature18；源和物理后处理quadrature28。4个z网格层只允许本轮N=2/4；N=8不合法，不重划网格。四层分区实际物理厚度并不相等，报告时保留这一限制。

原未知是对平面空气/Si背景的散射场，RHS为真实材料对背景的对比源；总场为散射场加解析背景。原全阶FE+aux矩阵为 [A,C;D,I]，先用独立全局direct取得同离散reference，精确保留所有原FE和aux方程。已有5nm相似控制参考不可冒用。p2仅承担同离散算法资格，不承诺物理精度或目标尺度能力。

## 源转移与重构

采用A=curl(mu^-1 curl)-k0²epsilon的正号弱形式，测试函数共轭。全FE+aux残差[rE,rq]先精确消去辅助方程为r=rE-C rq；输出端口q=rq-D e。用原全局FE L2质量矩阵M做Riesz lifting F=M^-1 r，再将f_i=M_i F按物理层体积分解，验证sum_i f_i=r。这里是未凝聚FE dual，不是未经lifting的trace residual。

β_i^+在第i层从1平滑降至0，β_i^-=1-β_i^+；区间外恒定，区间内用C1三次多项式。B_i为该层加权质量积分。弱截断交换项为：

```math
C_\beta(u,v)=\int\mu^{-1}(\nabla\beta\times u)\cdot\overline{\nabla\times v}
-\mu^{-1}(\nabla\times u)\cdot\overline{\nabla\beta\times v}.
```

它是a(βu,v)-a(u,βv)的连续弱形式离散；βv一般不在原FE空间，因此不宣称单次离散双扫严格恒等。所有β场都由UFL积分及curl乘积法则处理，绝不对edge DOF逐个乘β。

用从0开始编号的物理层，正向bar_0=f_0。对pair i=0..N-2求L_i u_i^+=bar_i+f_{i+1}；若仍有下一个pair，令bar_{i+1}=f_{i+1}-B_{i+1}F-C_{β+}u_i^+。反向独立从bar_{N-1}=f_{N-1}开始；pair i=N-2..0解L_i u_i^-=bar_{i+1}，仅i=0端点再加f_0。若i>0，令bar_i=f_i-C_{β-}u_i^-。原源截断项B_i F不可省略，反向内层不重复添加当前原源。

第i层的片状重构为u_{i-1}^++u_i^-，缺失端点为0。对该片状场组装质量负载，再用M^-1投影进原全局连续H(curl)/Floquet空间；它是明确的conforming近似重构，不是证明原PSTDDM定理已推广到本边界。全局mass因子同时用于lifting和投影，全部计入内存和时间，不称为“完全无全局因子”。核心入口 `PureSourceTransfer.apply`；局部装配和映射 `pstddm_native.build_partition`。

旧 `PMLDoubleSweep.apply` 每次用global action做r-=A delta，再顺序修正；新核心中没有这个算子，正反两串独立累计源，最后分层重构。旧代码只复用实际几何/材料/DOF映射帮助函数，不改名旧循环。

## 局部PML及映射

每个pair覆盖两个相邻分区的全部物理网格。人工切面外各加10nm PML，两层、厚度比1.25，材料按相邻真实横截面延拓；固定quadratic stretch s=1+i sigma(t/10)^2，sigma=3log100/(k0 sin1°·10)，约8.82。1%只是名义吸收设计值，不是误差保证；不扫描参数。原global cfg的pml_alpha字段未用于本局部式且global use_pml=false。外人工端点为零切向场；碰到真实z端点时不加PML，保留该端口完整原始DtN块。

PML eps=diag(s,s,1/s)epsilon，mu^-1=diag(1/s,1/s,s)，使用实际每cell材料系数和UFL积分，不使用旧无PML常材料张量缓存。JIT缓存只复用编译后的系数化kernel；PML参数、坐标、材料及source全部列入identity。

每个物理cell检查local/global orientation相同并逐raw DOF验证Tl S=T，含Floquet slaves/corners。S为独立primal坐标限制，其伴随S^H用于dual/重构；当前同相位/gauge映射为实permutation但必须验证，而不假设。N2局部物理域覆盖全域，无人工PML，其映射后L必须等于A-CD。本轮独立原生检查还包括弱curl乘积、质量分层恒等式、任意可表示场的重构再现及局部逆残差。

## 预算与流程

MPI1、四类线程变量均1；一次一正式PDE，先check_p2制造载荷，再direct_p2，再candidate_p2_n2/n4。候选明确为源转移x0后FGMRES(restart30,max100)，每实际迭代记录原FE+aux true residual。每case≤1800秒，全部数值/JIT/失败≤21600秒，最多10次；不自动延长。条件正结果且资源够时才另立一次p4成对对照，不启动p6。

保留更严格现场限制：系统采样用量<6GiB，任务树RSS+512MiB<2GiB，系统available至少2.5GiB且阶段前瞻另留至少1GiB+512MiB，swap=0，disk free≥12GiB+256MiB输出保留，总JIT/log/数组输出≤256MiB；阶段门含原生JIT及factor工作集估计。n×n复数因子预留4 n²×16 B是保守计划量，不冒充硬内核配额；监督器100ms采样整组树并受控终止完整组。N4中间pair预测4560独立local rows，两个PEC端面后4080free rows，因子预留1,065,369,600B，加512MiB后留约545MB现有RSS空间；是否准入由运行前实际RSS决定，不扩预算。因子策略对全部N相同：缓存全部local factors与一global mass factor，计入同时驻留；direct参考因子求解后释放，不藏在candidate峰值中。

正式证据保存input_original、resolved_config、source/input/physical SHA、manifest/summary、完整原残差、E/H和资源记录及hash；大数组在ignored artifacts。对p2未资格后处理标diagnostic，仍比较R/T/吸收/衍射及双方能量缺口，但不据此宣布完整物理通过。

## 依据及边界

[Du/Wu PSTDDM](https://arxiv.org/html/1505.06052v4)提供双向相邻层源转移结构；[2025 Maxwell论文](https://link.springer.com/article/10.1007/s10915-025-02872-7)当前仅公开摘要/附录可读，未声称已检查其订阅正文。这里是经过显式符号推导的Maxwell弱形式探索，不援引这些论文证明当前非均匀Floquet–DtN离散必然收敛。
