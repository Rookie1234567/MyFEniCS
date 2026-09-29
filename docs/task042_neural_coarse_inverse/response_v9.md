# Response V9：六个冻结状态的误差定位完成

V9_FROZEN_ERROR_PHYSICS_LOCALIZATION完成D0–D4，六个状态全部可用。最终独立诊断状态FIXED_ERROR_DIAGNOSTIC_COMPLETE，solver_pass=false；V7/V8四候选的数值负结果保留，没有新增求解、训练或资格。

| 身份／交付 | 精确记录 |
|---|---|
| branch／upstream／worktree | task42_neural_coarse_inverse／origin/task42_neural_coarse_inverse／/home/fenics/Projects/NN-Lab |
| common Git directory | /home/fenics/Projects/Maxwell3D-Lab/task-repository.git；linked worktree，不操作其他worktree |
| 开始HEAD／Review V6 | ba5ec813cc16a90adde1433ecb91e4b822b9d601 → 安全快进0071b97cc60996010c97671c5a1e620783af412e；远程实读，无reset或覆盖 |
| frozen base／初始任务锚点 | ccd357885f7f9be84efe3be07868cc94f13d93fc／f8c51c8e614edc806cf72120ac2cfd14ae8b62f7，均为当前历史祖先 |
| helper HEAD | 39c773962edd85388104cf6afbd747115ae8b294 |
| 实际正式运行source | a1dc3466294c30b6de292468d6dd1aa9b685b193；clean源码＋独立one-run dat，不以文档HEAD替代 |
| 修复／独立checker完整HEAD | e21af767d3522af531ad83c45eacc1df252566c9，clean提交后仅数组checker重放 |
| 最终交付HEAD和状态 | 最终commit无法在自身正文内嵌自己的SHA；以最终答复及Git精确HEAD为准，交付要求clean、upstream 0/0；[发布检查](outcomes/records/publication_checks_v9.json)绑定实际已推送文档HEAD |

本轮继续用户的Task042受控共享CPU授权，仅覆盖已有heavy禁用／独占要求。现场核查选正式CPU0，SMT siblings=[0]、采样busy0；MPI1／数学线程1，自身nice10／idle I/O、自有锁、整树16GiB hard／12GiB warn、swap0和隔离缓存。没有cgroup委派，使用原0.5s树监督，不宣称内核连续限额或绝对零干扰，不修改邻任务。两卡原训练忙碌，本批CPU-only，Torch/moment/D均未加载。

固定物理身份仍为0.7nm、384hex/p3、完整40端口、原canonical材料表。原action、master/MPC、背景、RHS、状态NPZ/z/source及run manifest哈希均闭合；NN7/FREE7接受状态UNKNOWN保留，LSQR8读取原物理z，未再乘D。REF7只做offline diagnostic，不回传任何训练／表示／初值，旧seed420620池封存。[完整身份与raw向量绑定](outcomes/records/frozen_state_inventory_v9.json)。

内部恢复会加入固定载荷特解，因此误差必须使用两完整场之差或显式零内部载荷。实际Se=r-r_ref最大差2.925e-12；齐次恢复3.082e-16；原增广/native身份1.601e-11／1.589e-11；背景抵消、slave-zero及实际MPC展开通过。默认recover(e)会错误多加范数0.001203391344625017的特解，本批明确捕获。参考实际Schur/native6.424e-12／3.018e-12保留，没有强置参考残差为零。[恒等式](outcomes/records/error_identity_checks_v9.json)。

| 冻结状态 | 原Schur／native相对残差 | 散射L2／scaled-curl相对误差 | 场范数比 | 复相关模 |
|---|---|---|---|---|
| Z0 | 1／0.387803782 | 0.999982／0.999973 | 0.00118192 | 0.382294 |
| NN7 | 0.913263145／0.661163226 | 0.661251／0.661245 | 0.457259 | 0.999809 |
| FREE7 | 0.797338565／2.179411163 | 1.008262／1.007831 | 0.0343829 | 0.345255 |
| LSQR7 | 0.071602580／0.028727752 | 0.999953／0.999937 | 0.00257406 | 0.424907 |
| LSQR8 | 0.068283274／0.026675036 | 0.998598／0.998575 | 0.00367088 | 0.421461 |

L2来自真实FE体积分，系数范数另报。NN7主导形状接近参考，但幅值不足且相位不同；两LSQR虽降低原残差，散射幅值仍只有参考约0.26%／0.37%。没有校相位、缩放场或构造更好的解。误差以y分量为主、遍布四区：NN7／LSQR8在air excluding notch约49.93%／49.98%，notch约2.08%／2.09%，substrate约12.54%／12.50%，Si block约35.45%／35.44%。实际单元数192/8/48/136，分区和交叉项最大闭合差3.024e-14。完整40通道复误差主要在上下(0,0,s)，全部原键、s/p和参考面保留；这不是功率差。[场](outcomes/records/field_error_components_v9.csv)、[区域](outcomes/records/region_error_integrals_v9.csv)、[通道](outcomes/records/port_error_components_v9.csv)。

原体作用和体—端口耦合、端口提取和原Hp作用均按同一误差拆开并保存复交叉项。LSQR8 body／port抵消比例0.0592730／0.000209768，方向增益比0.0683784，Schur残差平方99.95371%位于trace行。大场误差可以沿这一固定方向产生较弱方程响应；抵消并不独自证明病态，方向比也不是条件数。V内部机制、表示上限和优化原因仍INCONCLUSIVE，不宣布唯一根因。[完整原方程分量](outcomes/records/equation_components_v9.csv)。

首次正式stage因checker交叉项平方检查分母错误返回WORKER_FAILED，绝对舍入差约1e-17，却按强抵消后的约1e-8结果归一化。一次最小修复采用原运算项尺度，1e-10门限不变；7个受影响纯数组测试通过，仅重放只读checker。首次失败及原artifact/source/费用保留，最终最大独立差1.60056e-11；没有重跑FE或旧求解。[独立决策](outcomes/records/gate_decisions_v9.json)。

唯一正式stage launcher234.760038073s；packet/状态1.9241s、原审核3.9265s、误差/分块3.4860s、一次FE积分环境220.3246s（含JIT126.0700s）、保存/hash0.1506s。调用S11/Sᴴ0/recover16/uncondensed34，Hp审核12次solve加16次显式审核乘法，共28；FE436积分、43表单、22 MPC展开，均有界且缓存复用。树RSS采样峰1008717824B（0.93944GiB），own swap0、新增VRAM0。全部成本标shared-workstation，未观察持续PSI压力，缺可比阶段速率，邻影响INCONCLUSIVE。carry9804.434395463672s，新增包括失败／辅助／发布和120s明确保守占用，最终账保持新增≤3600s、累计≤36000s，不重复加父子时间。[全过程账](outcomes/records/resource_costs_v9.json)。

最终23相关pytest通过，Ruff/compileall/input/diff、历史字节保护和本地文档检查另记录。Review V6实际GitHub5表/6公式通过，review未改；新文档实际网页检查绑定发布HEAD。无full pytest／MPI2/4或CI声明。正式FE预检一次被沙箱本机MPI socket拦住后同ABI通过，没有重装；辅助测试文件名和小fixture断言错误费用也保留。

本批无global p4因子、global FE CSR、新目标factor或隐藏fallback；既有局部恢复packet和40维Hp审核被明确计入。无训练、新Krylov/参考LU、PC/loss/D扫描、p4 enrichment、F5/p6、短波、GPU、VTU或新R/T/A。旧p4路线保持关闭，最终0.7nm／48h仍NOT_QUALIFIED，目标成本和所需步数unknown。

唯一下一建议：待review批准后，针对冻结LSQR8误差与参考方向，在原未凝聚体行量化curl-curl、epsilon质量项及必要原边界项的平衡并核对原V作用；只需有界operator-only装配及少量作用，设置成本尚未测量。不做另行凝聚、求解、谱分析或loss/网络改动。本批没有实施，推送同一分支后等待review。
