# F0 测试与文档交付检查

| 检查 | 实际结果 / 数据身份 | 证据 |
|---|---|---|
| 新纯数组合同 | clean source9934c2e，33 passed in0.19s；workflow1.659649s，RSS67,231,744B、swap0 | [bounded runs](records/bounded_f0_runs.json) |
| pure / FE / CPU ML imports | 同clean source顺序独立进程通过；project路径、cache、thread、ABI和库映射实读 | [pure](records/environment_pure.json)、[FE](records/environment_fe.json)、[ML](records/environment_ml.json) |
| 失败API与一次修复 | C1 FE WORKER_FAILED/exit1、无JIT，后代清场；修复0.10实际cache API后通过 | 原raw与摘要保留，未覆盖 |
| 解析toy残差 | 11返回检查最大native1.2757622972373108e-16，port/recovery0 | [component audit](records/pure_component_audit.json)，无真实FE credit |
| Ruff / shell / compile / docs / ignore | 27既有静态测试通过，Ruff0.16.6通过，定向compile/bash语法/diff/11个Markdown文件与JSON/CSV/ignore通过 | [static_checks.json](records/static_checks.json)；不运行full pytest或FE fixtures |
| GitHub rendered view | 已推送2636fe5491e1381aa9cbda16abceb7ae4644b3e9的summary/架构/response及两份总账共5页，HTTP200；实际richText表格列数与math-renderer通过 | [publication_checks.json](records/publication_checks.json)；没有浏览器像素截图资格声明 |

纯数组测试覆盖正确复数方程、极小/极大幅值与相位、累计端口、内部恢复、全零与仅port非零、精确slave-zero、nonfinite/complex64/形状、operator身份与plan变更、固定RIGHT32/256/零初值、局部与总容量门、失败packet与sink失败。还给出凝聚不与p传递、curl/mass分别凝聚交换的反例。受控解析backend没有实际FGMRES迭代，不能以这33项或toy残差替代F1/F4。

复现最终数组测试（每次使用fresh独立目录）：

```bash
cd /home/fenics/Projects/NN-Lab
source scripts/activate_task042.sh pure
taskset -c 14 python scripts/task042_bounded_check.py \
  --directory tmp/task042/pure/recheck-<unique> -- \
  python -m pytest -q src/test/test_task042_coarse_inverse_protocol.py
```

CPU14是本次快照的空闲物理核心，后续必须重新现场核验，不能把它当永久安全CPU。FE/ML preflight命令同样通过薄监督入口顺序运行，仅导入。

静态交付检查使用仓库既有治理/文档/总账Markdown测试，另核对本轮新增/修改文件的fence、math、table列数、链接、JSON/CSV、null/not_run语义、保护条款、缓存忽略与非本轮源码diff。Ruff0.16.6仅只读运行已有独立可执行文件，缓存仍为NN-Lab；没有source Metrology环境或向其环境安装。

首次额外文档检查器在其自身记录尚未生成时报告自引用链接缺失，并把旧progress代码围栏内的等号误报为Setext；27项既有测试/Ruff/compile当次均通过。保留[首次负记录](records/static_checks_attempt1.json)和raw监督摘要；改为读取Markdown解析token判断围栏外标题，记录生成后一次针对性复查通过，未改历史正文。两次监督workflow分别2.616270/2.954395s，RSS57,163,776/57,368,576B、swap0，均清场；后续因交付文档更新所需的最后轻量校验在run index另列，不重复FE或数组研究。

本地使用markdown-it实际生成HTML并检查summary/架构/response的标题、表格和链接；local renderer把math fence作为code显示，因此不把它称为KaTeX视觉资格。GitHub真实富文本/公式renderer检查在推送后单列。Firefox系统入口会修改桌面配置，没有运行该入口。

首次发布检查器错误要求架构中文正文包含英文`not_run`，在该页HTTP200和公式组件检查通过后触发断言；这不是发布文档或数值失败。保留[首次检查器负记录](records/publication_attempt1.json)及原raw，修正状态关键词检查的适用页面后，5页一次复查全部通过。两次监督workflow分别6.626467/17.024449s，RSS63,635,456/55,427,072B、swap0，后代清场。发布证据绑定上述真实已推送SHA及每页源文件hash；后续仅补齐本轮检查记录，不用文档HEAD冒充F0运行源码SHA。

首次staged diff检查发现新CSV默认CRLF被判尾随空白；之前unstaged diff未覆盖新untracked CSV。提交/推送尚未发生，只将这两个新CSV规范为LF并复核列数与原值，保留[拦截记录](records/csv_line_endings_attempt1.json)，最终必须通过`git diff --cached --check`。没有更改旧CSV或任何数值字段。

full pytest、旧PETSc/FE ledger fixtures、MPI多rank、小FE/JIT、teacher/oracle、训练/GPU、F4严格粗逆和p6正式入口均not_run_by_shared_workstation_gate。没有CI声明。最后静态检查发生在文档准备工作树，保存其真实dirty/source，不冒充clean formal PDE。
