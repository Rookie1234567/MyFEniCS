# V32：两冷态真实回流与独立审核

本批检验“联合区域的修正能否经外域反馈，产生旧九方向之外的有效响应”。先在J=[5,7]解已有局部问题，交由另外六块处理外部不平衡，再回到J抵消内部反作用。收益是可能增加一个有用方向；代价是读取七套历史因子、三角解、原方程作用和资格审核。候选只是一项离线方向诊断，不能独立覆盖全空间。

```math
q_J=B_Jr,\qquad w=L_OAq_J,\qquad
 d=-w+B_JAw,\qquad q_{\rm ret}=q_J+d.
```

A是原完整40端口闭合trace作用，内部特解不加入方向。固定0.7nm／384hex/p3/q15／18144trace／40port／原材料、背景、MPC和b。J缓存及外域0/1/2/3/4/6各一次只读因子载入；不读旧5/7 LU，无新装配／因子、FE恢复、REF7或训练。

| measured两态 | eta9 | eta10 | g10 | h/Ad | h与e9复相关 | 预登记决定 |
|---|---:|---:|---:|---:|---:|---|
| LZ4 | 0.9662055056183673 | 0.9648437480030249 | 0.9985906128588339 | 0.9116084437 | 0.0530734200 | g≥0.95，固定提案关闭 |
| LCZ4 | 0.9819684299899415 | 0.9807007112496798 | 0.9987090025488145 | 0.8696863007 | 0.0507969313 | 同上 |

eta衡量最佳固定方向组合之后的剩余范数；g衡量新增方向相对e9的额外作用。它没有修改原物理b的分母，也不表示E/H场误差。两者rank10且创新远高于64eps操作尺度，数学／hash／计数／checker均合格，但增益只有0.14094%／0.12910%，未达到两态g≤0.75的有效方向信号。

| 原响应的区域变化；measured范数 | LZ4 | LCZ4 | 解释 |
|---|---:|---:|---|
| J内原qJ | 0.003415196899 | 0.015085481964 | 区域局部残差响应 |
| J内Ad | 1.578071565e-16 | 9.856390657e-16 | 反馈抵消成立，不是新内部方向 |
| 外域原qJ | 0.005032386762 | 0.027267368584 | 回流前响应 |
| 外域qret | 0.008149887477 | 0.050688089495 | 分别增至1.61949／1.85893倍，单次未收缩 |
| J内e9→e10 | 0.002856574893→0.002862917538 | 0.012998445954→0.012826379241 | 再优化组合也可能有区域间交换 |
| 外域e9→e10 | 0.005839453512→0.005826139828 | 0.022986546075→0.023043991079 | 不以某个局部下降冒充整体改善 |

创新确实包含旧空间没有的分量，但与尚未平衡量的夹角很大；独立保存向量和系数支持这一解释。g与sqrt(1−复相关²)一致。没有发现本次输入错位或原作用抵消／重组错误；这些证据不能确定所有全空间困难的唯一根因，也不能否定未运行的B_full。

| 资格链 | 实际值／限值 | 证据 |
|---|---|---|
| 七reader／局部见证 | 固定seed、hash／readonly／原主块及J伴随配对均通过，solve≤1e-8／operation≤1e-12 | [原actor归档](records/raw_result_v32.json.gz) |
| 抵消／重组 | 抵消operation1.7632e-20／1.8753e-20≤1e-10；重组/b6.1912e-17／1.7623e-16≤1e-11 | [分析](records/direction_analysis_v32.json) |
| QR／驻点 | QR及正交≤4.585e-16，驻点≤1.484e-16，保留原1e-10／1e-8限制 | [checker](records/return_direction_checker_v32.json) |
| 实际库存 | S34/SH2、reader7、J4/外域24、pass56、薄流程2、port factor1/solve35 | [消费账](records/actual_consumption_v32.json)；三方独立一致 |
| 新完整物理 | NOT_RUN，未生成新场或official R/T/A；V24 0/5、V23 0/6保持 | [回应](../response_v32.md) |

| 软件／运行包 | 成果／费用 | 边界 |
|---|---|---|
| 存储与路由 | 一个stat-only去重范围由事前／live／delivery共同调用；V32独立窗口／dat／账本，旧默认不改 | [初始记录及库存](records/storage_v32.json) |
| 合格证明 | 当前实现文件hash＋具体scope／source＋通过summary；辅助attempt独立收据并累计收费 | 不是任选旧PASS；未重开旧closed或删除失败summary |
| targeted测试 | 12 passed、pytest5.29s，13 Python compile与全局名称检查 | 无full-repo／CI声明；合成resource／reader桩不替代真实actor资格 |
| 真实actor | source1fe058e3d120c42d197531139fc62e02a1a2cd5f，唯一83.140184552s，actor前clean／中途HEAD不动 | [run index](records/run_index_v32.json) |
| 后checker | 第一个入口在准入前遇存储余量停止，保存stderr；只清理未引用bytecode10,722,813B后，独立ID实际checker4.521115911s通过 | 不改容量门限、不重做原作用或factor／QR |
| 受控共享资源 | 前测CPU11／actor0／checker0，MPI1/math1、BLAS1、ownswap0；actor采样峰1,247,059,968B | 0.5s请求实际0.582–1.021s，非kernel硬限；无可比邻阶段，性能INCONCLUSIVE |
| 全程累计 | carry52.680176060s＋本轮辅助15.668586196s＋actor83.140184552s＝151.488946808s≤600s | 总窗口10:42:27.034377Z起5400s不刷新，10:58:45.583814Z提前closed，随后仅交付 |

七套A/LU1,591,420,032B是净载荷，不是RSS；actor derived同时规划4,807,239,744B≤8GiB、实际同时树峰约1.161GiB。actor旧oracle作用约6.333904905s、局部lu_solve1.826185764s、reader含hash／mmap／norm／guard38.168578001s、薄代数0.023845749s，都已包含83.140185s监督wall；不重复相加，也未猜造独立资格见证／IO计时。历史factor构建、packet／神经训练／迭代和完整N=1成本unknown不消失。[完整费用](records/resource_costs_v32.json)／[邻任务观察](records/neighbor_observations_v32.json)。

NN20%保持NOT_DEMONSTRATED：本轮纯传统方向与线性代数，没有训练增量；没有最佳合格非神经完整N=1配对，不能将方向收益或较低RSS归神经。原尺寸正确性、离散／泛化、2TB／48h仍NOT_QUALIFIED。唯一建议是关闭固定局部方向序列，等待dot身份匹配参考与规模费用作只读对照，不自动实验。

| selective merge依赖组 | 变化与依赖／验证 | 当前建议 |
|---|---|---|
| production numerical/core | 原return公式／阈值／算子未变；无新PDE | 不提升production、不merge |
| reusable runner/window | opt-in V32注册／当前资格／attempt收费／统一存储，旧默认保留 | 12 focused＋唯一真实actor，等review |
| checker/benchmark | collector显式v32后缀，默认v28不改；缓存独立审核通过 | 保留完整消费和矢量证书 |
| compact evidence/docs | 新两态可信负结果、原始日志hash／资源／历史closed核验 | 可审阅，旧失败与unknown不改 |
| research-only/do-not-merge | fixed-return诊断dat／plan／synthetic fixture，Bret低秩不能全空间PC | 无神经、规模或merge资格 |

GitHub视觉NOT_VERIFIED，本地表格／math／链接结构另记。无subagents／重置卡、dot或其他分支修改、旧窗口重开。
