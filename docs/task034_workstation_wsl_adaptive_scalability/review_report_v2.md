# Task034 Review V2

## 1. Review 结论

```text
review_status = CHANGES_REQUIRED_BEFORE_SELECTIVE_MERGE
master_merge = not_approved
heavy_pde_rerun_required = false unless numerical core changes
```

本轮审查基于：

- Task034 远程分支：`codex/20260717-task34-workstation-wsl-adaptive-scalability`；
- 审查时远端 HEAD：`b2862ef429252a05f79fec19c1d616911d11bc87`；
- Review V2 reviewed-content commit：`a161ce0fb61454f3fb5588f645cf6d8b95b0f5f7`；
- 已合并的 Review 权威 master：`6b80b209c07d3c1d8354365a4359bf532ad7aec2`。

Review V1 的主要方向性问题已经关闭：resource envelope 与 simultaneous peak 已分离，0.7 nm 已改为 p2/p3/p4 current-layout stress tests，S 偏振主线与资源停止语义已澄清，benchmark Python inventory 和 selective merge 分组也已补充。现有 p3/h3、p4/h5、Case093 与代表性 MPI 数值结论继续接受。

但新生成的统一结果表存在实际数据语义错误，`summary.md` 也尚未满足用户明确要求，因此需要 `response_v3.md` 关闭以下 blocking findings。

---

## 2. Blocking Finding 1：`all_model_results` 存在字段误绑定

### 2.1 Hybrid `total_seconds` 被误填为对应 Full3D 耗时

统一 CSV 中多组 Case093 Hybrid 主行的 `total_seconds` 与对应 Full3D 完全相同。例如：

- p3/h3 Full3D：`1726.3617402129894 s`；
- p3/h3 Hybrid M160：也被写成 `1726.3617402129894 s`。

但已接受的 p3/h3 current-source MPI8 证据明确给出：

```text
Hybrid M80  = 529.556 s
Hybrid M120 = 567.573 s
Hybrid M160 = 661.410 s
```

同类问题还出现在 p2/h5、p2/h3、p2/h2、p3/h7.5、p3/h5、p4/h5 等 Hybrid 主行。

根因是聚合器对任意嵌套对象使用递归 `_first(..., ("elapsed_seconds", "wall_time_seconds"))`。Hybrid descriptor 内嵌或引用 Full3D evidence 时，该搜索可能拾取 Full3D 的 elapsed，而不是当前 Hybrid shard 的 elapsed。随后 `_case093_rows` 只在目标字段为空时更新，错误值不会被更正。

### 2.2 `factor_nnz` 混入了不同语义的 `matrix_nnz_used`

聚合器当前使用：

```python
_first(payload, ("factor_nnz", "matrix_nnz_used"))
```

这会把并非 LU factor inventory 的 `matrix_nnz_used` 写入 `factor_nnz` 列。

例如统一表中 p3/h3 Full3D 的 `factor_nnz` 被写为约 `157,432,833`，而已接受的同一 MPI8 current-source full-solve 记录为：

```text
assembled NNZ = 157,785,425
factor NNZ    = 1,307,605,045
```

两者不是同一物理量。若精确 factor inventory 不存在，必须保持 `null`，不能用名称相近但定义不同的字段替代。

### 2.3 Hybrid `external_aux_dofs` 被不必要地留空

多条 Hybrid 行已经同时提供：

- `fe_dofs`；
- `modal_unknowns = 2M`；
- `total_rows`。

例如 p3/h3 M160：

```text
fe_dofs = 223770
modal_unknowns = 320
total_rows = 224170
```

因此可精确得到：

```text
external_aux_dofs = 224170 - 223770 - 320 = 80
```

该值应从明确结构字段读取，或作为 `derived` 字段计算并由 checker 验证。不得无原因留空。

### 2.4 部分 evidence path 是本机绝对路径

p3/h3 M funnel 行包含 `/home/Projects/MyFEniCS/...`。正式 CSV/JSON 应统一为仓库相对路径；仓库外路径才允许保留绝对形式并明确标识。

### 修正要求

1. 对 timing、factor inventory、DoF 和 rows 使用明确 schema path；禁止对含义敏感字段使用无边界递归 `_first`。
2. `factor_nnz` 只接受真正的 factor inventory；`matrix_nnz_used` 必须另列或不写。
3. exact metric 缺失时写 `null`，不得从另一个方法、阶段或定义不同的字段补值。
4. Hybrid external auxiliary DoF 应从原始结构字段读取，或由 `total_rows-fe_dofs-modal_unknowns` 精确推导并验证非负。
5. evidence path 统一正规化为 repo-relative path。
6. 重新生成 `all_model_results.json/csv` 和 `summary.md`。
7. `test_86` 增加至少以下事实断言：
   - p3/h3 Hybrid M160 MPI8 `total_seconds` 约为 `661.410 s`，不得等于 Full3D `1726.362 s`；
   - p3/h3 Full3D factor NNZ 为 `1,307,605,045`，不得回退为 matrix NNZ；
   - 已知 Hybrid 行的 `external_aux_dofs == 80`；
   - 所有 repo 内 evidence path 均非绝对路径。

---

## 3. Blocking Finding 2：`summary.md` 尚未直接提供用户要求的汇总信息

用户明确要求 summary 中能够直接查看：

- 所有计算模型；
- R/T/A 与零级 R(0,0)；
- DoF/rows；
- 内存；
- 耗时；
- M 对结果和资源的影响；
- MPI 对结果和资源的影响。

当前 `summary.md` 的“表 1”只列 R/T/A_volume、状态和 closure；没有 DoF、R00、内存和耗时。M 表没有 MPI、R00、rows 和相邻 M 差；MPI 表没有 R/T/A、rows 和物理漂移。把这些信息仅放在 CSV/JSON 中不能完全关闭用户要求。

### 必须修改的 summary 表

#### 表 1：全模型主表

至少直接显示：

```text
p/h, method, M, MPI, status,
fe_dofs, external_aux_dofs, modal_unknowns, total_rows,
R_total, T_total, A_balance, A_volume,
R00_total, peak_memory_gib, total_seconds
```

若表过宽，可以拆成“物理结果表”和“规模/资源表”，但所有模型必须可在 summary 直接查看，不得只链接 CSV。

#### 表 2：M funnel

至少显示：

```text
case, MPI, M, modal_unknowns, total_rows,
R/T/A, R00_total, residual, memory, time,
max delta vs previous M
```

必须明确 p3/h3 当前展示的是 MPI4 旧 formal funnel，还是 MPI8 current-source funnel；不能省略 MPI 导致两个证据链混淆。优先展示已接受的 current-source MPI8 p3/h3 funnel，并可另注 MPI4 历史 formal funnel。

#### 表 3：MPI identity

至少显示：

```text
method, MPI, total_rows,
R/T/A, residual, peak memory, total time,
max physical drift vs selected baseline
```

MPI32 必须继续标为 exploratory。

#### 表 4：资源停止/超时

当前表基本合格，继续保留 assembly measured、factor upper predicted、launch=false 和 Hybrid 实际状态。

---

## 4. Blocking Finding 3：自适应 mesh 文件不应无条件作为 production merge candidate

`src/geometry/task034_adaptive_mesh.py` 的 conforming graded-mesh mechanism 已通过结构、周期配对和 Floquet 机制 Gate，但：

```text
equal_accuracy_graded_compression = controlled_negative
field_driven_adaptivity = not qualified
```

因此 selective manifest 不能让文件名仍绑定 Task034、且物理自适应能力未资格化的实现无条件作为 production API 合入。

允许两种处理：

1. 本轮标记为 `research_only_do_not_merge_yet`，保留 evidence 和测试；或
2. 重命名/整理为通用 experimental opt-in conforming graded-mesh mechanism，明确不包含已资格化 field-driven adaptive policy，并以对应测试组选择性合入。

无论哪种方式，都不得在 capability matrix 或 ordinary default 中声明自适应求解能力已通过。

---

## 5. 已接受内容

以下结论继续接受，无需因本轮聚合修正而重跑重型 PDE：

1. S 偏振是正式主线，P 只保留 p2/h5 capability sample。
2. p3/h3 Full3D/Hybrid same-degree closure pass。
3. p4/h5 Full3D/Hybrid same-degree closure pass。
4. p3/h5 Full3D/Hybrid MPI1/8/16 identity pass；MPI32 exploratory。
5. p2/h1、p3/h2、p4/h3 Full3D 精确状态为 `not_run_by_conservative_resource_gate_after_assembly`。
6. p2/h1 Hybrid 为 `timeout_during_field_recovery_no_official_solution`，不是 memory failure 或 numerical nonconvergence。
7. resource model v2.1 已正确区分 largest component、cumulative envelope、measured peak 与 unknown predicted peak。
8. 0.7 nm 三场景只作为 current-layout stress tests；production target-accuracy DoF/M/peak 仍为 unknown。
9. benchmark Python inventory 的总体结论成立：Task034 没有为每个 p/h/M/MPI case 复制一套独立 Maxwell solver。
10. Review V2 本地测试结果可接受；修正聚合器后需重跑 targeted tests、Task034 suite、文档合同与 full pytest。

---

## 6. Response V3 要求

Codex 应在原 Task034 分支：

1. 直接读取本执行分支中的 `review_report_v2.md`；不得要求 ChatGPT 先写入或更新 `master`；
2. 修正聚合器和机器可读表的字段语义；
3. 完善 summary 四张表；
4. 修正 adaptive mesh selective-merge 边界；
5. 新增 `response_v3.md`，不得覆盖已有 response/review；
6. 不修改 Maxwell/Floquet/QEP/Hybrid 数值核心时，不重跑 p3/h3、p4/h5 和 MPI 重型 PDE；
7. 完成测试、提交、推送后停止等待 Review V3；
8. 未获得最终 review approval 与用户授权前，不得合并 `master`。