# 目标尺寸 5 nm 的下一步容量设计

本页是 E5 的尺寸与成本推算。目标 PDE 未运行，几何尚待 review 冻结；0.7 nm、48 h 和生产资格仍为 `not_run/not_qualified`。这里的“5 nm”是波长，区别于已经实测的小型 M5；它不是把盒长缩成 5 nm。

| 对象 | 候选配置 / 单位 | 证据类型与边界 |
|---|---|---|
| 光学 | 波长5 nm、Si/air、1° grazing、phi0、s入射 | 沿用本轮材料表hash，不能重猜材料 |
| 周期与盒子 / nm | x[-25,25]、y[-12.5,12.5]、z[-1.25,121.25] | proposed；上下开放面位置未冻结 |
| Si结构 / nm | substrate z<0；block x[-12.5,12.5]、全y、z[0,120] | proposed；真正三维缺口见下一行 |
| 空气缺口 / nm | x[0,12.5]、y[-3.75,3.75]、z[40,80] | proposed；y/z同时变化，不改成可分截面 |
| 网格 / nm | h1.25；40×20×98 hex=78400 cells；p3，FE求积15 | derived exactly for this proposed box；未造网格/矩阵 |
| 开放边界 | 原双Floquet及原auto-propagating Fourier-DtN | analytic mode count另见容量JSON；未构造目标FE耦合 |
| 网络 | 当前3×64 tanh仍8966实参数 | 不等于已证明足以表示目标场；本轮不改网络 |

按原端口模式枚举 API 对这项候选几何做解析计算，得到上下端口共 600 个有序传播模式（上 304、下 296）；身份及顺序见[容量记录](records/target_capacity_v1.json)。这是由建议盒子和材料推导的通道数，没有创建目标网格、耦合块或 PDE，也不说明 600 模式已经收敛。

对一个 Nx×Ny×Nz 六面体网格，p3的双周期独立边、面、内部矩数量可直接由拓扑计数。每边有p个矩，每面有2p(p−1)个矩，每cell内部有3p(p−1)²个矩；下面没有用小模型运行次数伪装目标实测。

| FE对象 / 复数行 | 小型M5 measured | 此候选 derived |
|---|---:|---:|
| 原生未约束FE | 34050 | 6471114 |
| 周期slave | 2082 | 106314 |
| 全部独立FE | 31968 | 6364800 |
| 独立边矩 | 3744 | 710400 |
| 独立面矩 | 14400 | 2832000 |
| 独立trace | 18144 | 3542400 |
| 内部矩 | 13824 | 2822400 |

目标未知量约为M5的199.10倍、cell数为204.17倍。完整FE向量单个约101.84 MB，FREE的参数/梯度各约101.84 MB；L-BFGS的20对历史方向约4.07 GB，再加Adam、图、端口、矩与算子临时对象。不能拿8966网络参数代替整条路线内存。

| 生命周期 / 字节或时间 | M5校准 / 本轮观测 | 目标预测 / 必须先解除的阻塞 |
|---|---|---|
| A/Aᴴ体作用的全cell临时张量 | 当前实现按cell类索引展开，384×144²×16=127401984 B | 78400×144²×16=26011238400 B，约24.22 GiB；单个临时对象已超过当前16 GiB合同，须先改成有界cell批量作用 |
| 坐标及矩packet | 当前最多8cell图；固定坐标、矩、owner表仍常驻 | 992点/cell的坐标数组约1.87 GB；约束展开COO约0.36 GB；其他index/变换/端口另计；目标packet未导出 |
| 稀疏Gram CSR | 31968行、7336179 NNZ；payload146851456 B；实际装配648.77 s | 按cell比粗推约1.50×10^9 NNZ、约30 GB payload；连CSR也超当前16 GiB；边界修正/真实稀疏图未知，不能称exact NNZ |
| RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR | LLᴴ/AMD symbolic fill18839705，CHOLMOD峰633592648 B，numeric约108.84 s | 三维N^(4/3)填充模型约2.2×10^10项；复值/行号存储约0.5 TB，含工作区约0.75 TB；只是不确定性很大的预测，非准入 |
| Gram factor时间 | symbolic flop≈2.76×10^10，单核numeric约109 s | N²模型约1.09×10^15 flop，按当前单核校准约50 d；几何、顺序和局部结构可显著改变比例，但不能据此宣称48 h通过 |
| 每次Gsolve/训练 | 实测必须从三路线成本账读取 | 不能线性外推训练步数；固定tanh的频率表示与优化仍未在目标验证 |
| 参考Maxwell factor | 仅本轮候选冻结后的小型authority | 目标全局Maxwell因子无预算/未运行；不得改成训练fallback |

约2 TB是全机物理内存。它不能替代当前的本任务预算，也不能视为邻项目驻留和增长预留已释放。当前共享窗口下有效可用减去系统与邻增长预留，仍不足以为上述不确定的目标全局Gram因子准入。任何目标阶段都需要新的合同、资源窗口和先symbolic容量Gate，不能借剩余16 h启动。

下面给出替代Riesz路线的成本模型；它们只是设计候选，未实现、未运行，不替代本轮准确稀疏factor的实账。

| 候选Riesz生命周期 | derived 或成本关系 | 未验证量 |
|---|---|---|
| matrix-free G action | 全cell致密144×144局部作用上界为78400×144²=1625702400次complex multiply-add；batch8张量临时2654208 B | 实际核融合、索引、MPC及CPU吞吐；不是秒数预测 |
| Krylov常驻向量 | 8个完整复向量814694400 B，约0.759 GiB；owner/端口/网络/缓存另计 | 内层算法、迭代数及实际峰RSS |
| H(curl) multilevel/auxiliary space | 一次hierarchy setup，加每次V-cycle成本；几何层数和稀疏fill须单独symbolic核验 | Bloch周期与高阶空间兼容、正性、fill和收敛没有证明 |
| Gram RHS solve | T_rhs=T_hierarchy_setup(首次)+k_G×(T_G_action+T_PC+T_reduction) | k_G unknown；不能宣称常数迭代或线性可扩展 |
| 全部训练 | 同一固定G内积，每次完整closure都计Gsolve；原残差/场/功率Gate不变 | 每次真实Gsolve≤1e-11及有界FD梯度需先在M5资格化 |

这里的multilevel是辅助正定G的候选求解方式；不是给Maxwell A提供隐藏global inverse。约2 TB物理RAM、向量payload和O(N)符号不能证明16 GiB/48 h：所有hierarchy、临时对象和迭代必须实际测量，目标部署需要新的资源合同。

Gram是计算残差的辅助正定系统。可扩展方案应先在固定M5上检验有界cell A/Aᴴ和matrix-free或multilevel H(curl) Riesz作用，保留真实Gsolve误差与全部原方程/场/功率Gate；不能把粗略内层误差当已通过的1e-11准确解，也不能引入global Maxwell逆。该方案尚未实现或运行，不把小型准确稀疏因子称为可扩展预条件器。

本轮唯一下一最小建议由三路线的独立验收结果决定，详见response。目标几何、更多seed/宽度/carrier、p/h扫描和0.7 nm均需后续review，本轮交付后停止。
