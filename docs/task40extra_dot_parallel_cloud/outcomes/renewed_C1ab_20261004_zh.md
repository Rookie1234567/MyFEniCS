# 恢复后的两项实际资格已闭合

2026-10-04 的独立云分支现在完成 C1a 与 C1b，各自具有真实 worker、独立检查器和完整 Library 原始包取回核验。C1a 是 p6 紧凑端口的作用/RHS/恢复组件；C1b 是 p4 稠密端口、完整 Ny 参考的四个 q 及 regular/notch 三维求解链。两者使用 7/135 缩放的 80 单元、phi5、manual532 和原两单元 notch，尚未验证原始大模型尺寸、精度、2 TB 或48小时目标。

## 实际结果

| 项目 | C1a p6组件 | C1b p4求解链 |
|---|---:|---:|
| 独立检查通过项数 | 955 | 148 |
| 完整内部自由度 | 36,000 | 8,640 |
| 物理端口 | 532 | 532 |
| worker 时间 | 1,349.135 s | 97.766 s |
| worker 树 RSS 峰值 | 2,191,613,952 B | 863,150,080 B |
| 成功 checker 时间 | 18.142 s | 3.779 s |
| checker 树 RSS 峰值 | 519,229,440 B | 455,397,376 B |
| swap | 0 | 0 |

C1a 保存并独立核验全部80单元、16 raw/29 oriented 类、1,616 个数组。制造解原始 native 残差2.4904492e-15、恢复状态差1.4967087e-12。原始 H 只需8,512 B且不常驻 Hhat；物理 DiXiB 范数7.6890873e-27，只说明数值非零。独立合成负控具有0.5的实质修正，故不能把物理小修正称为遗漏耦合敏感性证据。

C1b 实际分解四个1884/1960/1960/1960维块，因子 setup6.001 s。generic、interior_only、physical、notch_supported 的原始 A1 notch FGMRES 为4/4/3/4步。regular 最大原方程残差5.416e-12，notch 最大7.967e-12，均保持原1e-10门槛；8组输出全部含532模式并通过必要 global-output consistency。它使用完整三维原始作用和恢复，未创建全局 p4 稠密 FE 矩阵，也没有声称全局 direct 或官方 RTA 资格。

C1b 的 sampled PC defect：physical0.0001869652、generic0.0020506757、interior_only0.0015409116、notch_supported0.0017875125。这些是特定载荷采样，不是算子范数界；本微小两单元扰动不能代表原尺寸非可分几何的收敛难度。

## 源码与失败保留

C1a producer为`a580c72a`，独立 checker为`16415427`。C1b producer/checker为`dd26a1a9`，树`daaae32186bd420a801915a061b1c8fb378e370c`。这些是恢复后的真实本地源码身份；发布提交可以有相同文件树但不同提交身份，旧丢失的本地提交图未被伪造恢复。

原始单元张量修复保持 exact native authority 单独归档，不用不同浮点运算顺序得到的结果替代内容 hash。首次实际 checker 因 stale native basis SHA失败；新公开工厂准确匹配本次 producer 的c0be730…64da。旧系数数据缺失，因此未声明旧/新基函数等价。三个 checker 文件的 exact old/new hash 桥与全部其他1,318依赖一致性受审阅。C1b 新增的 producer/checker/consumer 角色修复只触及两个 metadata 函数和测试；数值/配置及相邻 AST 保持不变。

早期 pyvista导入和 tensor-bitwise失败的科学原始数据在重置时丢失，保留历史说明，不称作已恢复。attempt3 的512MiB raw受控失败已完整保存在Library；768MiB C1a预算是新的明确决策，不追认旧失败。错误 CLI、解释器路径字面不一致、native metadata失败、修复成本和失败收据均保留。相对解释器 argv 的外部监督保持源码/真实 ABI、3GiB/4500s、zero swap、MPI1/单线程及清理门槛，没有豁免。

## 实际持久化

- C1a完整 worker恢复索引：`libfile_ac66834781108191a106e5517ae07c09`，12部分重组392,240,642 B，全部1,627文件和1,616 NPY核验
- C1a最终 checker包：`libfile_8479ec542a008191b8b42264d072fd28`，776,001 B，19成员全部核验
- C1b完整 worker恢复索引：`libfile_6c5d9eaccaa081919951a2abf2611064`，4部分重组101,510,980 B，352文件/327 NPY全部核验；包括新恢复图的真实 Git bundle，以便后续消费 exact source-role gate
- C1b最终 checker包：`libfile_d9ebe52606348191b6a6e1d1121419a5`，767,426 B，13成员全部核验

两项先保存全部 worker原始包并真正取回，再运行 checker，最后保存 checker包并取回。原始科学数组放Library，GitHub保存源码、报告和小型索引。[完整小型记录](records/renewed_C1ab_20261004/renewed_C1ab_compact.json)包含SHA、资源、阶段和限制。

## 已耗成本和下一道门

恢复12:05开始；到14:32的总墙钟为2小时27分钟，含约19分钟并行运行环境恢复、工程修复和审阅。已有可加收据子计25分12.827秒不能冒充总时间。另保留CLI失败0.391秒、环境启动失败0.750秒、归档导入失败0.184秒；C1b另加worker97.766秒、checker3.779秒、打包5.115秒和完整worker Library读回96.89秒。小包传输和部分下载没有完整elapsed，未虚构总数。

下一项 C1c 是紧凑 p4 quotient 全链。现有 compact provider 和字节受限投影已在源码，但旧 numerical入口依赖丢失的历史 audit/Step0包，不能假装已有 fresh CLI。应直接使用本次 C1b 已持久化 reference，先明确需要恢复的 local carrier/volume/映射和同一算子比较，再做最小接线；不重做已合格的 p6 组件。C2公共PETSc/AUTO成本和原尺寸完整求解仍未运行。
