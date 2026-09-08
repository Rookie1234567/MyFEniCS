# Review V2：F0/F1 实现待测量

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
