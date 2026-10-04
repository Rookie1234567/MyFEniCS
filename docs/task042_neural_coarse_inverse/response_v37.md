# Response V37：完成目标边界的有限真实见证与分块接口，保留q15及存储负结果

本轮在原三维目标尺寸的普通外表面上核查高阶有限元边界积分，并把单方向系数改为分面片生成。12个预登记通道的未裁剪分块作用通过；q15精度不合格。原生q60 JIT越过新存储门后停止自身负载，留下q15／q30原生数组，再独立完成Basix q30／q60、分块、checker及容量／消费分析。**没有取得TARGET_P6_BOUNDARY_WITNESS_QUALIFIED、完整有限元解、原尺寸2TB／48h或NN20%资格。**

| 身份 | 本轮实际值 |
|---|---|
| worktree／branch／upstream | `/home/fenics/Projects/NN-Lab`／`task42_neural_coarse_inverse`／`origin/task42_neural_coarse_inverse` |
| common Git／origin | `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`／`git@github-myfenics:Rookie1234567/MyFEniCS.git` |
| 冻结base／任务初始锚点 | `ccd357885f7f9be84efe3be07868cc94f13d93fc`／`f8c51c8e614edc806cf72120ac2cfd14ae8b62f7`，均为本分支祖先 |
| 取得的Review V34 | `02fe5f860562f6a7ef689f9d53b061cfaf30a43b`，同分支安全fetch，无回退／其他worktree操作 |
| 原生保存q15／q30实际source | `ce18a6056731780d1feb4f47c96dfcc4f52aa6d1` |
| CAPACITY／独立数组CHECK实际source | `bd7d7e2bc8167973ee1156deb0e8a23607a37db6` |
| 最终实现／DEPLOY实际source | `d7ec9180af1b45f55bd37b49a6f0ac450920589e`；最后文档HEAD另在推送回执及会话报告，不冒充数值source |
| 固定时钟／边界 | 2026-10-04T03:17:22.040407958Z，monotonic1008836.90，boot fd8f4b00-1e17-46af-a6fa-da3a32dbeba3；24h总窗口，末1h交付；总有载3600s／组件2400s |
| 交付状态 | closed，全部自有actor清除；推送后精确HEAD／clean／upstream0/0另核验，旧账本未重开 |

材料仍为canonical用户表，source波长0.699999988、nominal0.7，n=0.999885140474+4.32477054e-6i，epsilon=n²。目标周期50／25nm、外表面130／−10nm，实体x=16.5..33.5、y=0..25、z=0..120；本轮未偷换为微型模型或把面片宽度当周期。V36的32060完整ordered库存按hash复用，元数据预选12mode／4类面片共20hex；实际只完成一类4hex。各次失败重建合计16个native hex，未超过32；没有构造530856cell目标mesh或完整FE编号。

| 分别验收的问题 | 实测／停止项 | 结论 |
|---|---|---|
| q15积分是否足够 | q15／q30最大相对差 1.32594720615e-05 > 1e-10 | 不足；不靠裁剪小系数制造一致 |
| q30更高阶对照 | 未裁剪native q30／Basix q60差 4.69243170483e-13 | 普通面片支持q30；缺原生q60及周期情形，不能扩大结论 |
| 同q分块泛函 | 最大差 4.68916382572e-13；forward 2.79307870108e-13，adjoint 2.61645760695e-13 | 有限普通面片接口通过；完整高阶边／面矩、方向／Piola保留，C/D独立 |
| 端口振幅／H／单位功率 | 1.59542409236e-13／0／7.105427357601002e-15 | 仅局部边界见证，非物理解功率 |
| 旧两道裁剪 | q30删14928及112个分量；最大C/D差1.9269e-13，未删空本组选中通道 | 此有限组未超门；V36增加LEGACY_CLIPPED_SURFACE_EQUIVALENCE限定，不能证明全部目标通道裁剪安全 |
| 软件及隔离 | 最终31个定点测试、MPI2／4小fixture、真实编译／ABI通过 | MPI1真实FE；MPI2／4含空owner与共享rows，不称真实目标MPI资格 |
| 原native／Schur残差、E/H/curl、R00_s/p/total、R/T/A、A_volume、逐通道能量 | NOT_RUN | 本轮边界组件没有体积求解；无official结果 |

失败均保留。普通面片原MPC入口不适用于没有全局周期实体的截取片，最小修复为空的原全局约束限制；周期缝／角点仍走全局50／25nm周期映射。随后修复native双复分量T_apply需要平坦缓冲区的接线。q60生成的C/o/so造成新存储越512MiB：当时只有阶段边界存储检查，这是监督接线缺口；核实自身argv／PGID和临时JIT cwd后只SIGTERM自身组，未动邻任务。保存的失败raw分类仍WORKER_FAILED，资源原因另列；未称全程存储合规。修复0.5s新存储guard，经纯回归后只做已保存前缀的独立容量接口分析，没有重新启动该q60扩大步骤。34份JIT文件先无损压缩并解压核对hash／长度后回收原副本，原始科学数组和历史结果未删。证据打包CPU字段接线错误同轮修复，失败3.280613258s仍计费。

dot只读发布SHA为077ec9c8386c976da232093779279fb9d1a93033。逐字段验收区分相同入射／lambda／p6、真实几何与材料差、mode／Floquet／canonical行／恢复证据缺失；不是拿不同schema的hash直接判不同物理。其n差2.991716531811656e-8没有被默许成同一算子，source恢复未授其runtime／科学raw资格。没有执行dot solver、factor或修改其ref／工作树。

费用均标shared-workstation：监督wall 446.204937213s＋探针 25.657178592s＋bootstrap保守收费3s＝474.862115805s，含失败、JIT、归档、测试及checker；其中PATCH＋CAPACITY累计269.670777797s。分块作用集合wall1.810418537s包含creator1.628519290s与hash0.041459786s，不能再次相加。全批同时树采样峰3387654144B（约3.155GiB），own swap0、GPU不用；独立cgroup没有权限部署，记录为0.5s整树采样与停机保护，不伪称内核连续硬峰。数学／BLAS getter1、真实MPI1，自有锁／缓存／低优先级；每次准入重选核，实际CPU见原准入表。邻Task042extra持续运行未干预；没有足够可比阶段数据排除干扰，性能影响INCONCLUSIVE。

最终新库存477669342B、Task042 artifact 14963754484B，自由磁盘3370566049792B。端口tile实测42336B，保守全mode支撑111259016B原门会拒绝；9.08MB只是条件理想支撑。完整FE输入＋输出至少11.0647GB载荷，条件GMRES256向量组434.673GB，体积solver／因子／内部恢复／MPIIO共存峰unknown，未拼成伪峰。完整N=1历史仍有unknown；既有77349.71922726494s下界保留，不把边界费用当整个求解成本或NN摊销收益。

[完整结果与停止分析](outcomes/target_p6_boundary_tiles_v37.md)／[run与父hash](outcomes/records/run_index_v37.json)／[独立checker](outcomes/records/component_checker_v37.json)／[费用](outcomes/records/resource_costs_v37.json)／[原raw及大数组索引](outcomes/records/raw_evidence_index_v37.json)／[消费缺口](outcomes/records/consumer_v37.json)／[依赖分组](outcomes/records/selective_merge_manifest_v37.json)。GitHub精确Review V34页未取到视觉渲染，NOT_VERIFIED；本地结构检查单列，不称CI通过。

唯一下一建议：取得一次可预估JIT峰存储的未裁剪原生q60周期缝／角点边界见证，补齐精度与MPC覆盖；本轮不自动继续、不以NN补积分误差、不merge。推送、closed和清场后用原会话队列交回审阅窗口。
