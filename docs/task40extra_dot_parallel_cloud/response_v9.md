# Response V9：centered p4 同网格升阶与新源码 p2 桥接通过

**结论：有界三维 p4 升阶架构资格通过。** 固定source `ad356715da86ab34fa6b10838cccc8629b3f6e8b` 先在新源码重做p2桥接，保留旧7c4410d的不可变dense authority，再运行同80单元的p4。两个独立checker分别164/164和148/148通过。p4没有全局direct对照；原volume authority来自保存的实际live FFCx作用向量，checker重算这些保存向量的残差、端口输出及稀疏块恒等式。

本次把同一三维离散实现从p2升到p4，保留全部内部未知量、全部y方向块和532个非空物理端口。单元内部先精确消元，求解四个y方向块后恢复每个原三维未知量；没有用二维截面替代三维场。这仍是小规模、弱扰动夹具上的实现验证，不是目标物理精度或工作站大运行资格。

## 桥接与p4原方程结果

| 对象 | measured | 授予范围 |
|---|---:|---|
| 新源码p2对旧centered dense | 2048原列差0 | 旧报告、provenance和manifest固定hash继续绑定 |
| p4独立 /内部 /trace自由度 | 15872 /8640 /7232 | 全部原三维自由度恢复 |
| p4四个增广q块阶数 | 1884 /1960 /1960 /1960 | 全部532非空端口；不合并不同物理alias |
| p4自身local basis /Gauss | 300 /degree23、144点 | 同一live carrier的532模式资格在factor前完成 |
| regular四载荷最大原残差 | 4.2235259e−12 | generic、interior_only、physical、notch_supported |
| 缺口四载荷迭代数 | 4 /4 /3 /4 | 真实三维缺口 |
| 缺口最大原残差 | 7.9668824e−12 | physical载荷；无full p4 direct差声明 |
| physical缺口非零q比例 | 3.0887006e−5 | 保留真实ky wrap和跨q耦合 |
| 完整增广off-q相对量 | 5.0522e−16 | 全部块对在factor前审计 |

两套checker各自40组逐模式输出比较均通过，每组覆盖532模式；p4最差局部运算误差6.5096e−17。required global outputs本夹具均可表示，此结果不推广到目标几何的global振幅。p4四块原残差最大5.0543e−13，重复解差0、线性差最大2.9903e−13；原始RHS和解向量的诊断hash保留。缺口右预条件器采样缺陷为1.8697e−4至2.0507e−3，是这些载荷的测量，不是算子范数上界。

## 时间、内存与尚未测到的成本

| 运行 | 监督wall | 采样同时整树RSS |
|---|---:|---:|
| 新源码p2桥接worker | 14.8806s | 462925824B |
| p2桥接checker | 3.5524s | 328343552B |
| p4 worker | 117.4464s | 913350656B |
| p4 checker | 4.7910s | 524525568B |

四个记录均swap0、正常退出、后代清场，低于本次1.5GiB/600s准入。采样RSS不是未采样硬峰，不将不同run相加。p4 worker事件时钟记录：live组件资格18.1946→53.1309s；factor前carrier检查93.8409s；全部对称门97.9421s；四块保留完成101.6171s；四类regular检查完成104.7213s；四类缺口检查完成114.5136s；退出carrier检查114.7221s。

精确凝聚build计时24.9723s，其中kernel23.7653s、local Schur0.2536s、插入0.2127s、预分配0.4912s。reference setup计时7.7761s，包含审计和factor流程，不能称纯LU时间。对称门通过至四块保留的事件间隔3.6750s也包含导出及诊断。四个缺口solver计时1.3910/1.4028/1.2287/1.6636s，包含迭代、原作用与预条件器调用；没有独立pure-PC apply计时，regular事件间隔也包含恢复、输出与检查。

资源相位记录存在边界：全部采样的worker_phase为空，supervisor与worker事件是不同相对时钟，未建立精确offset。整树峰值出现在supervisor elapsed66.1744s，不能据此硬归因某个数值阶段。已保存的分配边界瞬时RSS包括live开始433692672B、condensed matrix准入476639232B、初始factor准入648855552B；这些是点测值，不能替代分阶段峰值。

named payload另列：condensed CSR62914140B，保留局部数值缓存24760944B，装配临时raw tensors23040000B、oriented Schur17104896B。它们有不同生命周期，不能相加当RSS。512MiB factor/workspace allowance是准入声明；SuperLU实际factor内存仍未知，未为统计额外复制L/U。这些测量不推出TB级目标容量或48小时可行性。

## 身份、失败与移交

[compact证据](outcomes/records/centered_p4_v9/centered_p4_v9_compact.json)绑定两个report、provenance、checker、live receipt、事件和资源hash。[独立复核](outcomes/records/centered_p4_v9/independent_verification.json)核对1251个冻结源码文件、591项artifact hash（桥接288、p4 303）及48项raw-factor hash；这些计数不等于数组个数。复核为读取已保存证据，没有重跑数值求解；[说明](outcomes/records/centered_p4_v9/independent_findings_zh.md)保留精确范围。

V8两次严格上下文停止及V5/V6/V7全部历史失败继续保留。旧7c4410d dense authority保持原身份，不伪装成ad356715运行；p4使用自己的basis/Gauss/live资格，不能直接继承p2资格。仍未完成p6、强对比、原目标尺寸、目标模态截断/连续与几何精度、官方R/T/A、跨机器ABI、MPI及restart资格。继续与MyFEniCSx_task37_extra共同补足同一次工作站启动，自动读取主线远程结果；由用户执行大型运行。
