# PSTDDM pilot Response V1

状态：**PASS_WITH_QUALIFICATIONS**，已完成四个p2案例及独立保存数组复核，停止本轮扩展。

1. 新实现使用双向累计源、正确带原源截断的Maxwell弱交换项、局部PML及连续重构；没有旧Schwarz的global residual逐块更新。完整约定见method_v1.md。
2. 真实0.7nm、120单元p2、非可分有限x/y块、双Floquet和836 DtN模式的完整3956阶原系统已解出。N2首扫残差1.66e−13；N4首扫0.11157，18步后5.74e−9，最终总/散射E/H均通过同离散门。
3. 没有内存收益。N2/N4峰RSS613.37/874.19MiB，总56.716/82.300s。N4的PML使最大局部free4080超过全局FE3120，三个局部因子与全局质量因子同时驻留。主要时间在装配，不是外迭代。
4. 保留方法研究价值，但下一步应先改PML网格和因子生命周期的成本结构。本轮不启动p4（保守准入预测超预算），不凑N8、不扩大、不改变默认或merge。

总场分母会掩盖弱散射误差：N4首扫散射E/H仍有4.45%/4.83%，不能通过；FGMRES后降到3.63e−9/3.56e−9。功率一致不等于物理收敛：reference能量缺口0.00470279，p2未收敛，R/T/吸收全部diagnostic。制造源的功率诊断门false保留。

四案总监督249.892s，资源门均未触发，swap0，完整进程组清场。测试和证据遗漏均在[统一结果](outcomes/summary.md)列明，不宣称CI/full suite通过。[独立审阅](review_report_v2.md)重算原始矩阵和资源通过，原run未修改。

数值source bd0d4daed6da301eaca26b2fdac76a59a834be8a，基线2c7aa97f4746c5de0545cf511908321b356a74df。实现已以等树70afaab9aaa6cde32de23c1e45f509e86bfffb53发布；本地结果提交e17101f7e42ac58ca9ab2c51314279731539fe4d。发布/备份最终验证另列publication记录；远端未核验的提交绝不标已发布。

发布补充：用户明确允许本轮内容上传到指定仓库分支。结果提交60be6bbdd79d0dfffba11590a6ba224bc656b2dc已回读，完整备份已恢复验证；同源码、同原数组，无重跑。详见[outcomes/publication_v2.json](outcomes/publication_v2.json)。
