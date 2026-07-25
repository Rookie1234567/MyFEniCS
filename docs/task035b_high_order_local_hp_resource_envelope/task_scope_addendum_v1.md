# Task035b 范围补充书 V1：当前仅研究固定规则几何

## 1. 权威与优先级

```text
addendum = Task035b scope addendum v1
authority = user-authorized scope reduction
execution_branch = codex/20260723-task35b-high-order-local-hp-resource-envelope
supersedes = task.md clauses involving speculative irregular geometries
current_geometry_scope = Task034 fixed rectangular block grating only
irregular_geometry_research = out_of_scope_by_user
ordinary_default_changed = false
master_merge = not_authorized
```

本补充书是用户对 Task035b 的明确范围修订。它的优先级高于同目录原始 `task.md` 中涉及斜侧壁、圆角、缺口、尖角扰动或其他假设性不规则几何的条款。

原因是未来实际不规则结构尚未确定。现在随意构造若干“代表性不规则结构”，不能保证与未来服务对象有关，反而可能消耗大量计算与开发时间并产生误导性的 hp 结论。

---

## 2. 当前正式几何范围

Task035b 只研究：

```text
geometry = Task034 fixed rectangular block grating
wavelength = 13.5 nm
incidence = 10 degree grazing
polarization = S
```

允许改变的仅是数值离散与求解策略，包括：

- global p4/p5/p6；
- structured hexa 与 qualified tetra；
- local h refinement；
- local/regionwise p；
- high-order active-mode removal；
- element-interior static condensation；
- DWR、R5 与 smoothness/hp classifier；
- Full3D–Hybrid closure；
- DoF、NNZ、factor fill、peak memory 和时间优化。

不得在本任务中创建或运行：

```text
sloped sidewall
rounded corner
curved profile
local notch
defect
roughness
sharp perturbation
arbitrary irregular geometry
```

除非用户以后提供明确的真实几何、参数范围和工程目标，并另行建立新任务或正式补充任务书。

---

## 3. 对原任务书的具体修订

以下条款被本补充书替代：

### 3.1 原核心研究问题中的不规则几何问题

原 `task.md` 中关于“斜侧壁、圆角和局部缺陷等代表性不规则几何”的研究问题，当前状态改为：

```text
out_of_scope_by_user
not_run
not_a_completion_gate
```

### 3.2 原“代表性不规则几何”范围

原 `G1`、`G2` 几何层级全部取消。当前只有：

```text
G0 = current fixed rectangular block grating
```

### 3.3 原 Phase F 不规则几何转移

原 Phase F 的斜侧壁、圆角、notch、defect 和 singular perturbation 计算全部取消，不得启动。相关 outcome 最终应记录：

```text
status = out_of_scope_by_user
reason = actual future irregular geometry is not yet defined
```

### 3.4 完成判定

Task035b 的完成不再要求：

- 任意不规则几何算例；
- 不规则几何30%/50%/60%压缩比较；
- geometry-transfer结论；
- curved-geometry或defect benchmark。

---

## 4. 0.7 nm 资源模型中的保守系数

原任务书使用：

```text
f_H = 0.30 nominal
f_H = 0.35 conservative
f_H = 0.40 stress envelope
```

这些系数可以继续用于离线资源敏感性分析，但 `f_H=0.40` 现在只表示：

```text
conservative unknown-future-geometry planning envelope
```

它不授权创建任何假设性不规则几何PDE，也不构成Task035b的数值验证点。

13.5 nm等效DoF目标保持不变：

```text
minimum engineering target = <=90000
preferred robust target = 65000–75000
stretch target = <=60000 only with all independent accuracy gates
```

其中优选区间用于给未来未知几何、Hybrid接口、modal core和低存储预条件器保留资源余量，不代表本任务需要模拟未知几何。

---

## 5. 修订后的研究主线

Task035b 只围绕当前规则结构推进：

```text
1. qualification of same-mesh global p4/p5/p6
2. freeze a trustworthy FEniCS high-p baseline
3. decompose edge/face/interior DoF and matrix/factor memory
4. audit element-interior static condensation
5. build same-mesh p4/p5/p6 local correction data
6. classify p-down / p-keep / p-up / h-refine candidates
7. implement local-p or regionwise-p that physically removes matrix rows
8. start from accurate global-p6 and seek >=2x same-error compression
9. target <=90000 equivalent DoF, preferably 65000–75000
10. compare against global p5/p6, uniform controls and Task035 DWR candidates
11. connect only the best 1–2 candidates to Hybrid
12. update the 0.7 nm / 2 TiB resource envelope
```

不允许为了填满任务阶段而自行发明额外几何。

---

## 6. Codex执行规则

Codex开始Task035b前必须同时阅读：

```text
docs/task035_hcurl_goal_oriented_adaptivity/review_report_v6.md
docs/task035b_high_order_local_hp_resource_envelope/README.md
docs/task035b_high_order_local_hp_resource_envelope/task.md
docs/task035b_high_order_local_hp_resource_envelope/task_scope_addendum_v1.md
docs/COMSOL_direct_solver_report.md
```

发生冲突时，以本补充书为准。

Task035b继续采用连续自主研究模式。提交与push不是等待点。只有环境或证据身份异常、资源安全风险、所有合理路线耗尽、准备修改ordinary default或准备合并时才停止。
