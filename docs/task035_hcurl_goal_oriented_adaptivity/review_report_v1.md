# Task035 Review V1：Phase A 文档合同阻断与快速恢复方案

## 1. 审查结论

```text
review_status = PHASE_A_LOCAL_CONTRACT_FIX_AUTHORIZED
branch_exists_remote = true
wsl_environment_failure = false
numerical_failure = false
phase_a_environment_base_subgates = pass
phase_a_full_regression_initial_run = one_known_contract_failure
heavy_pde_rerun_required = false
additional_review_before_phase_b = not_required_if_all_listed_gates_pass
```

本轮审查对象为远程分支：

```text
codex/20260721-task35-hcurl-goal-oriented-adaptivity
```

该分支从：

```text
master@5002636852ffb67b4711443da70eb536c303e34e
```

创建，目前远程存在且相对 master 领先一个提交。

Phase A 的 WSL、complex ABI、MPI1/2/4/8、MUMPS、SLEPc PEP、Task034 compact baseline、六份必要 artifact 哈希和 hermetic checker 均已通过。当前停止不是 Ubuntu/WSL、PETSc、MPI、MUMPS、SLEPc、FEniCS 或物理模型故障。

唯一失败为：

```text
src/test/test_26_documentation_contract.py::
DocumentationContractTests::
test_numbered_benchmark_cases_use_case_contained_contracts
```

根因是 Phase A 按任务书创建了：

```text
benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/base_manifest.json
```

但旧文档合同把所有 `benchmarks/cases/<numbered_case>/` 目录都视为已经完成完整 benchmark freeze 的正式 case，并使用硬编码 `CASES` 集合。Case094 在 Phase K 才完成最终 benchmark freeze，而 Phase A 已经需要该目录保存 base manifest，因此当前是**case lifecycle 与旧测试合同不匹配**，不是 Task035 科学或环境负结果。

---

## 2. 推荐修正：为 numbered case 增加 staging/in-progress 生命周期

不建议删除 Case094 目录，也不建议为了通过测试而在 Phase A 伪造“已完成”的 canonical Case094。推荐修改 `test_26_documentation_contract.py`，明确区分：

```text
QUALIFIED_OR_FROZEN_CASES
STAGING_OR_IN_PROGRESS_CASES
```

### 2.1 正式 case

现有 Case001–Case093 继续保持原有严格合同：

- 完整 README；
- 22 项参数表；
- 规定章节；
- expected status；
- 既有 record/run/test 文件要求。

不得因 Task035 放宽已有正式 case 的合同。

### 2.2 staging case

将：

```text
094_hcurl_goal_oriented_adaptivity
```

显式列为 staging case。staging case 至少要求：

```text
README.md
config.json
expected.json
test_command.txt
records/base_manifest.json
```

其中必须明确：

```text
status = phase_a_in_progress
canonical = false
production_qualified = false
pde_run = false
phase_b_or_later_results = not_available
```

README 只需解释当前 Phase A 身份、运行 checker 的命令、已有/未有证据和升级到正式 Case094 的条件；不必在 Phase A 提前填写 Phase K 才能产生的结果。

测试应保证：

1. 实际目录集合严格等于 `formal cases ∪ staging cases`；
2. staging case 不能使用 canonical/qualified status；
3. staging case 必须有明确升级条件；
4. Case094 的 `test_command.txt` 只运行 hermetic Phase A checker，不启动 PDE；
5. Phase K 完成后再把 Case094 从 staging 集迁入正式 case 集，并启用完整 contract。

这不是降低测试标准，而是为 benchmark 增加符合任务阶段的生命周期。

---

## 3. 允许的最小修改范围

Codex 可在当前 Task035 分支直接完成：

1. 新增 Case094 staging scaffold：
   - `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/README.md`；
   - `config.json`；
   - `expected.json`；
   - `test_command.txt`。
2. 修改 `src/test/test_26_documentation_contract.py`：
   - 保留现有正式 case 合同；
   - 增加 staging case 合同；
   - 将 Case094 纳入 staging 集。
3. 扩充 `src/test/test_87_task035_phase_a.py`，锁定：
   - Phase A checker hermetic；
   - staging status 不得冒充 canonical；
   - Case094 base manifest 存在且可检查；
   - 不读取 ignored artifacts 的普通路径。
4. 保留 `phase_a_regression_failure.json` 作为首次失败历史，不删除、不改写为通过。
5. 新增 Phase A completion 记录或在现有 outcomes 中明确写：

```text
initial_full_regression = fail_one_document_contract
contract_fix = pass
final_phase_a_gate = pass
```

6. 新增 `response_v2.md`，说明修正和最终 Gate。

不得为解决该问题修改 Maxwell、Floquet、DtN、QEP、Hybrid、材料、几何或求解器数值核心。

---

## 4. 测试策略：避免在前置阶段重复浪费时间

本次不需要重新运行：

- WSL 环境安装；
- MPI1/2/4/8 资格化；
- MUMPS/PEP microfixture；
- 六份 Task034 artifact 的完整哈希验证；
- Task034 重型 PDE；
- p3/h3、p4/h5、M funnel 或 MPI matrix。

这些 Phase A 子 Gate 已有绑定证据，除非环境、baseline SHA、artifact descriptor 或数值核心发生改变，否则不得重复。

修正顺序应为：

```text
1. 仅运行原失败测试
2. 运行 test26 + test87
3. 运行 focused governance/Task034 baseline tests
4. 最后只运行一次 full pytest
```

建议命令：

```bash
pytest -q \
  src/test/test_26_documentation_contract.py::DocumentationContractTests::test_numbered_benchmark_cases_use_case_contained_contracts

pytest -q \
  src/test/test_26_documentation_contract.py \
  src/test/test_87_task035_phase_a.py

pytest -q \
  src/test/test_24_repository_work_principles.py \
  src/test/test_26_documentation_contract.py \
  src/test/test_81_task034_case093.py \
  src/test/test_86_task034_review_v2_aggregation.py \
  src/test/test_87_task035_phase_a.py

pytest -q
```

同时运行 scoped Ruff、compileall 和 `git diff --check`。

Phase B 开发期间采用测试金字塔：

```text
每个小改动：pure-Python/单 fixture targeted tests
每个 estimator 子阶段：serial + MPI2/4 component tests
Phase B 收口：Task035 focused suite
Phase B 完成并解锁 Phase C 前：full pytest 一次
```

不得在每个小提交后重复全仓 pytest、环境重装或 artifact 全量验证。

---

## 5. Gate 失败后的新处理规则

后续需要区分两类失败。

### 必须立即停止并等待审查

- environment/ABI 不一致；
- source 或 baseline hash 不一致；
- MPI identity 失败；
- true residual、official R/T/A 或物理 Gate 失败；
- estimator fixture 暴露数学/数值错误且修复方向不明确；
- 内存、swap 或资源终止；
- 需要扩大任务范围或改动 ordinary default。

### 可在当前阶段直接修复并 targeted rerun

- 当前分支新建文件引起的文档合同缺项；
- README/index/schema/scaffold 不完整；
- 明确、局部、无歧义的测试夹具或元数据错误；
- lint、格式、链接和 compact record schema 问题。

后一类失败不应把整个任务停成长期等待状态。修复后只重跑受影响测试，再在阶段末运行一次全仓回归。

---

## 6. Phase B 解锁授权

完成上述 staging contract 修正后，只要：

```text
case094 staging contract = pass
test26 + test87 = pass
focused baseline regression = pass
full pytest = pass
Ruff/compileall/diff-check = pass
worktree = clean
```

即可将：

```text
phase_a_full_regression_gate = pass
phase_b_unlocked = true
```

无需等待额外 ChatGPT review，可直接进入 Task035 Phase B。

进入 Phase B 后仍只做 estimator 定义和解析/manufactured fixture；不得跳过 fixture 直接运行真实 p4 adaptive 或重型 PDE。
