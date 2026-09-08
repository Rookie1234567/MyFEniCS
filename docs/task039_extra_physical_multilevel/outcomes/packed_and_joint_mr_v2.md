# Review V2：F1 结果与 F3 实现待测量

## 当前条件判定

| 阶段 | 实际结果 / 权限边界 |
|---|---|
| F1唯一正式 | source `4d30514d52e27d3c854c8d1f4432d3ce977c078e`；14/14完整PC，同一setup；数学等价通过、速度`INSUFFICIENT` |
| 固定速度Gate | median(逐对packed/original)=0.9384593270111676>0.75；两边中位数之比1.0493987661812125仅诊断 |
| F1完整wall / 资源 | 1096.5564253670163 s；4203样本RSS峰3592585216 B、PSS峰3558076416 B，全部可读；swap0，cap/余量违规0；60个相关PID清场、cache稳定 |
| 等价 / 重复 | same-input action最大1.4723857041130954e-14，S6最大3.385589945200919e-14，PC最大3.3634736365759556e-13；48项重复raw比较误差0 |
| F2 | **not_run**：未满足F1速度Gate |
| F3 | 已实现、最小测试63 passed，等待主任务审阅diff；未commit/push/formal，无旧checkpoint续跑 |
| F4 / official | not_run；尚无原始或非可分合格场 |

F1原/packed非warm完整PC中位为22.616387295012828 / 23.733608922862913 s。六个逐对比为1.3125269344515638、0.8743704405784026、0.9371184214537938、0.9398002325685414、1.140713267443425、0.8937186630153917，保留波动，不从中挑选最好样本。

| F1非warm每PC嵌套范围中位 / s | 原实现 | packed |
|---|---:|---:|
| B6 | 14.235077654360794 | 15.399217725906055 |
| PC内部原物理volume | 4.408280928560998 | 3.9336588784935884 |
| S6 inclusive | 16.775018576532602 | 17.88990024913801 |
| p4 solve/check | 0.562832570518367 | 0.5991889264550991 |
| p4 backsolve | 0.0971992164850235 | 0.10331542801577598 |

本次完整S6中的B6未胜过原FFCx，物理volume的小收益不足以形成25%的完整PC收益；p4回代不是主要成本。这些是不同嵌套范围的中位数，不能相加当成互斥分解，不继续packing优化。正式raw、comparison、全树资源和源码绑定见[小JSON](records/packed_and_joint_mr_v2.json)。

## F3 做什么

顺序MR每次只决定一个方向的步长，后续方向出现后不会重选前面系数。F3保留旧LIGHT的H6、准确p4和再次H6这三个方向及原顺序MR中间残差，只在末尾联合选三个复系数，检验方向互补是否有益。B6/H6窗口和原A6完全沿用R3；F1快速PC A6不进入F3。capture接口只保存旧MR已经计算的三个原A6作用，不增加p4 RHS或重生方向。

先以每个原A6作用的范数缩放对应D/W列，再做稳定薄QR，对最多3列的R做小SVD，截断固定为1e-12，不形成正规方程。复内积使用共轭转置。新候选最多用一次原A6显式核验；若残差大于已保存顺序残差加1e-10倍输入范数，则返回原顺序解，不重新执行H6/p4。小SVD或有限候选系数问题可以回退；物理action、p4或输入nonfinite直接失败。截秩时不宣称完整三列空间的理论最优性，成功也不保证外层更快。

非零通常调用计数为H6=2、B6=4、p4=1、原方向A6=3、joint核验A6≤1；旧零残差/零方向规则保持，实际跳过项按真实计数记录。每PC保存rank、最多三个归一化奇异值、复系数、方向范数、顺序/联合/选中残差和fallback原因，QR及extra A6成本进入完整PC wall。前三次仅增加同输入hash及紧凑seq/joint比较，属于将来正式fresh-zero的开头；每32步汇总scalar记录，完整周期清空，partial只保留当前≤32条，不积累旧方向或周期。

## 新增工作数组的生命周期

每个fine complex128向量为173802×16=2780832 B。表中只计相对旧LIGHT新增的工作；原q、顺序correction/residual、旧H6/p4内存另属于原基线。D/W复制仅存活于一次PC，结束释放。

| 阶段 | 同时存活的新fine列（最坏路径） | 其他存储 / 释放点 |
|---|---|---|
| 三方向按旧顺序产生 | D3+W3=6；零action临时零列至多1，即7 | MR已有临时Vec不重复归为新增；每次capture写自己的列 |
| 列归一化与QR | D3+W3；若SciPy未共享，再加QR3和Q3，最多12 | 当前tiny测试确认QR共享W、Q共享QR；最坏计数仍容许两个拷贝；LAPACK显式lwork=9，各144 B，tau≤3个复数 |
| 小SVD与candidate | 上述最坏12+candidate1=13 | R≤3×3、U/Vh/系数均常数大小；zgemv共轭转置避免N×3共轭拷贝；mask至多3N字节 |
| helper返回与转换 | QR/Q局部引用释放后，D/W6+candidate1+proposed1=8 | copy完成即del candidate；顺序解一直保留，不重算 |
| 显式核验 | D/W6+proposed1+额外A6值1+checked residual1=9 | 物理A6仍借原算子buffer，不增全局矩阵 |
| 返回与清理 | 上述9+返回copy1=10 | ExitStack随后释放proposed/value/checked与D/W；无跨PC累积 |

13列最坏QR/candidate峰加mask、可能的单列范数工作及常数工作仍小于16列；采用保守分配界 `16*N*16+65536=44558848 B`，低于64MiB。65,536 B覆盖固定LAPACK工作、tau、R/SVD/系数等小对象，N相关mask由16列余量覆盖。原有顺序correction/residual不因F3增加；RSS还受allocator/cache影响，不能把数组上界当作实测进程树峰值。tiny tracemalloc检查新增峰值低于该界，原尺寸F3 RSS为not_run；旧R3同期进程树峰3352014848 B作为历史基线保留。

## F3 最小验证与唯一待审核命令

合并test352/356/365/368：63 passed。覆盖复系数、rank1/2、近相关/零列/零RHS、极端列尺度、短矩阵、QR共享、内存上界、严格旧方向输入一致、最多一次extra A6、显式safeguard回退、SVD失败回退、物理nonfinite拒绝、真实PETSc/H6调用计数，以及32条完整周期清空后7条partial不累积。首次3 failed/60 passed仅是新NumPy fixture缺少caller-owned solution的destroy协议；只修fixture，没有扩展生产销毁接口，失败日志/扣账保留。

新profile为`light_p4ref_jointmr3_v2`，FGMRES32/max2048、原始零初值、solve7200 s、workflow10800 s；whole-workflow的最后60 s留给合作收口，parent最迟10740 s请求，solve Gate仍7200 s。沿用动态cap≤12,000,000,000 B、至少4GiB/15%有效RAM余量、进程树swap0，以及每8步/120 s安全点与32步账本。每次启动重算可用内存。新V2账本独立扣账，不借V1余额。

以下命令**未执行**，需主任务批准实现并形成clean source后，才用于唯一原始F3；没有profile/checkpoint flags。

```bash
cd /home/shenjh/Projects/MyFEniCSx_task37_extra
source scripts/activate_myfenics_wsl.sh
export GIT_DIR="$PWD/.git-codex" GIT_WORK_TREE="$PWD"
python scripts/run_case.py input/task39extra/original_13p5nm_p6h10_light_p4ref_jointmr3_v2.dat \
  --batch-budget-ledger benchmarks/artifacts/task39extra/review_v2_batch_budget.json
```

## 历史 F0/F1 实现快照（下文not_run指当时状态）

| 阶段 | 当前状态与证据边界 |
|---|---|
| F0身份 | `task39extra`，起点 `abe5fa2cb1240c397f514a815390a2d9fabd5d5f`，原Task base `2dc2e7305f10dc391a13970c6f0f0340cb87b6ee`；启动时HEAD=origin、clean，使用canonical目录的.git-codex |
| 旧证据 | 四份hash-bound审计及checkpoint576的manifest/solution哈希核对一致；旧R3源码cbf56e8、last_safe真残差0.0791360407785889，不改写为通过 |
| ABI | 资格化仓库venv链接；PETSc/petsc4py3.19.6 complex128/int32、SLEPc接口3.19.2、DOLFINx实际0.10.0.post2、Basix0.10.0、Linux OpenMPI4.1.6；线程均1 |
| 资源快照 | F0有效总RAM14654980096 B、available12872261632 B、reserve4294967296 B、cap8577294336 B；正式启动重新计算，不固定沿用该cap |
| F1实现 | 新显式 `a2r_packed_equivalent_v2`，仅B6和PC内部split A6 volume开启contiguous_work；batch8；外层与真残差A6仍原实现 |
| F1正式测量 | **not_run**；当前只有实现diff与最小测试，不提交、不推送，供主任务审核 |
| F2/F3/F4 | not_run；未提前实现F3联合选权 |

连续排布是把局部实部/虚部放到连续内存再做相同运算，以减少局部计算成本；收益是否覆盖复制成本要由完整PC测量决定。一次共享setup中复用原S6/p3/p1、p4分解、传递、对角和power10窗口。原/packed交替调用前先撤销计时装饰器，再只切换B6和PC内部A6引用；共享对象身份及窗口hash必须保持。旧FAST profile不启用连续排布，含义不变。

输入为归一化物理RHS、checkpoint576合法primal在当前原A6上重算的残差、seed3902合法复向量。checkpoint存在但hash/物理/ownership不符即拒绝；文件不可用时仅用其余两输入。每路径首个warm，其余每输入两次，共14次（缺checkpoint时10次）完整PC；无外层求解。原始/packed同输入action限1e-11，S6/PC限1e-8；原A6作用于不同PC输出另列诊断。重复性从已校验hash的S6、PC及A6 raw数组独立重算，不相信worker的passed布尔值。

**速度Gate在测量前固定为 median(t_packed_i/t_original_i)≤0.75。**两边所有非warm原始样本、各自中位数与两边中位数之比并列记录；后者仅诊断，不能事后替换Gate。计时保留必要日志，只剔除诊断数组保存范围。冷setup及安装前后资源单列，热调用两路径共存缓存的RSS前后采样单列；payload不是RSS，不能相加冒充进程树峰值。

F1共2400 s包含setup、测量及停止宽限；2340 s请求合作停止，预留最多60 s整树收口。沿用5975463机制，parent/worker都对新显式profile登记PID/start ticks；只向应用请求一次SIGTERM，资源越线仍立即整树硬停。新V2账本独立上限36000 s，不复用V1余量；当前仅实现测试扣账，正式F1未预约。小fixture不是新的正式退出资格。

| 最小验证 | 结果 |
|---|---|
| 合并361/363/365/367 | 82 passed / pytest3.07 s，外层monotonic4.689019392011687 s；含真实小FE原作用、窗口不变、交替引用/计时与旧profile回归 |
| 新parent/worker接线补充 | 11 passed / pytest0.29 s，外层1.419340105028823 s |
| 最终367 tiny | 12 passed / pytest0.34 s，外层1.322435159003362 s；含同步hash后伪造repeat=true仍拒绝，以及两种中位统计量分离测试 |
| 最后合并回归（最终代码） | **85 passed**；pytest报告6.11 s，外层monotonic4.123782100970857 s，分别保留原始口径；增加ownership拒绝和PACKED专属parent/worker配置断言 |
| 静态 | 改动Python compileall与git diff --check通过；未运行full repository；Ruff未安装，不声明CI/网页渲染通过 |
| 保留失败 | 首次MPI探针被沙箱socket权限阻止，未跑PDE；真实Linux权限下ABI通过。首次最小批次8 failed/74 passed：构造器多传batch_size、旧fixture无variant、新profile枚举遗漏，均局部修复；失败成本保留 |

输入SHA为`2a88399b0c3f5f5cd3d3b6b3b0619db8a051f5283c746c81642e1d98adb168bd`；physical SHA保持`9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f`。实际ABI、改动文件hash、日志和预算绑定见[小JSON](records/packed_and_joint_mr_v2.json)。代码尚未提交，因此不能把本次dirty测试身份用作formal来源。

正式F1唯一待审核命令如下；需主任务批准本diff并形成clean commit后执行，现在未启动。dat中的10800 s是既有完整流程字段，诊断入口以此处冻结的2400 s覆盖；不启动完整求解。

```bash
cd /home/shenjh/Projects/MyFEniCSx_task37_extra
source scripts/activate_myfenics_wsl.sh
export GIT_DIR="$PWD/.git-codex" GIT_WORK_TREE="$PWD"
python scripts/run_case.py input/task39extra/original_13p5nm_p6h10_a2r_packed_equivalent_v2.dat \
  --physical-pc-profile results/euv_grazing1_phi0/original_13p5nm_p6h10_p6smooth_p4ref_p6smooth__full3d_iterative__mpi1__Mna/20260907T223143.281687Z/checkpoints/iteration_000576 \
  --profile-variant a2r_packed_equivalent_v2 \
  --batch-budget-ledger benchmarks/artifacts/task39extra/review_v2_batch_budget.json
```

一次共享setup最多14次完整PC，原模型/modes和准确p4逆未改变。未获得任何packed性能、原始场或非可分资格；后续条件由Review V2及真实Gate控制，剩余预算不授权另加候选。
