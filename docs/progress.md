# Development ledger — docs/implementation-plan.md

- Approved scope: all five phases in chat, offline first. 2026-10-22.
- Ruling: target is an empty non-Git project; no existing branch to isolate. Use sandbox staging, then verified publication to exact user path. Avoid changing parent repository.
- Ruling: standard-library unittest replaces unavailable pytest; no external installation required.
- Preflight interfaces: Task1 produces JSON-safe tasks/docs -> Task2 engine consumes them; Task2 run returns JSON-safe results -> Task3 CLI/report consumes them. No shared ownership conflict.
- Task 1: complete. Compressed SQLite index built on D:; 396/414 JSON readable, 18 explicit read failures. 15 data tests pass; real index audited, no source writes.
- Task 2: complete. Three modes, core math, evidence extraction and state machine; core and final reviews passed. Strict explicit boolean review gate included.
- Task 3: complete. CLI, comparison, annotation template, offline HTML; 5 real markets x 3 modes and one annotated synthetic run saved. UTF-8 console verified under legacy GBK.
- Task 4: complete. 120 source/config/doc/report files published with SHA-256 verification; independently built D: index and audit preserved. Final target-directory run: 50/50 tests passed, 16 saved runs passed provenance/budget/cutoff checks, and run.py demo regenerated successfully from the target path.
- Scope ruling: real pilot is pipeline acceptance only, includes past-deadline tasks and repeated event corpora; no accuracy or cost-at-equal-quality claim. Source labels remain proxies. See validation.md and patent-map.md for deferred production capabilities.

## Continuation — automatic pipeline

- User steering: “不用人工审核了--先把全流程跑通”. Human review is optional and does not block execution.
- Task 5: implemented and real-data checked. 5 different events selected by frozen hash order from cutoff-visible metadata; 1,563 texts exported, source hashes verified, raw output path prohibited.
- Task 6: automatic full pipeline completed in staging: 15 new runs, deterministic English rule version recorded, all real directional matches zero and explicitly disclosed. No human-reviewed annotations or external model/API calls.
- Regression: 71 tests passed; 31 stored runs plus 5 prepared inputs passed manifest/time/budget/input-equality checks. Original 16 runs and index remain unchanged.
- Task 7: pending stronger automatic semantic extraction, official outcome verification and independent quality evaluation. A successful pipeline does not complete this task.
- Final target publication complete: 263 files verified; independent review has no open findings. From the final D: directory, 71 tests and all 31 stored-run/5-prepared-input checks passed. run_pipeline.py executed successfully from D: for 5 tasks/15 runs into a separate temporary smoke output; no original outputs overwritten.

## DeepSeek integration and storage correction

- Task 7 semantic adapter and bounded real pilot complete: v1 50 calls/15 runs, v2 50 calls/15 runs, strict v2 rejects odds-derived direction. v2 all support zero; no quality claim.
- Total recorded API usage 158,969 tokens including probe and both versions. Disk-full report failure recovered from cache, no extra API request.
- User storage requirement enforced: all project data migrated to D:, 677 remaining C: files hash-verified; temporary verification data also preserved on D:. Current C: chat folder contains only Git metadata.

- Final D: validation passed: 94 tests (47.073s), 61 stored runs, 50 cached calls/15 identical replay results/0 uncached tokens, exact credential absent in 1,990 project text files. Target test log: docs/target-test-output.txt. All temporary test and replay outputs were on D:.

## Task 7 quality preparation

- Added coverage diagnostics, fixed event partitions, official resolution collection and post-prediction scoring. 13 new behavior tests; full 107 tests passed (33.071s).
- Real official API audit: 1/5 scoreable, 3 not final, 1 lacks terminal payout details. All three modes and 0.5 baseline have Brier 0.25 on the single scored market; no improvement or independent holdout claim.
- Frozen semantic pilot retained unchanged. 61 saved forecasts and both new quality reports pass provenance/metric checks. No new model calls; all files and test temp paths on D:.

## 阶段十三（2026-10-23）

- 已完成损失逐条观测、来源/预算/净收益判据、收缩阻塞与证据进出轨迹；运行时紧迫度/预算表接入共享标注和按需抽取路径。
- 54 次历史完整输出保持一致，16 次参数敏感性、2 次合成档位联调完成；304 Python /20 前端测试通过。
- 默认未换参，真实标定、专利整带回收对照、独立新样本与真实调用成本尚未完成。详见 phase13-delivery.md。

## 阶段十四（2026-10-23）

整带回收显式对照、180次开发比较及486次真实本地查询观测完成；340项Python和20项前端测试通过。严格历史暴露登记覆盖107标识，当前索引106真实事件全部已暴露，独立新样本为0。真实发布者成本/配额及酝酿期标定仍缺字段；未启动独立评价或替换默认策略。详见 phase14-delivery.md、phase14-summary.html。


## 专利预算口径修正（2026-10-23）

[0103、0104、0108—0113、0248—0252]新增显式patent_budget_v1：派生常规预算、守候独立记账、三类预留及共享配额、回收统一包含式成本、来源集合变化后只重分配未花费额度。历史默认输出保留。351项Python测试通过；三个已用事件/60文档的6个新运行完成预算核验，6份旧输出完整一致。焦点成本12.6>单轮8.333，实际未整带回收，不能宣称预测收益。

更正：此前106事件“全部暴露”是把元数据筛选排除也纳入的保守登记，不证明全部参与语义调试；独立样本需按暴露类型重新界定。[0205]网格公式、[0249]成本尺度及随时间到达回放仍需分别对齐。当前新规则未切换可视化工作台默认。详见[本次修正与验证](patent-budget-correction.md)。


## 来源成本与逐格预算接入（2026-10-23）

[0205]显式patent_grid_v1使用名义带宽及逐格公式，无归一化总额、无跨轮信用；修复浮点微格重复领取预算。[0249]成本观测profile接入引擎、CLI、按需抽取与冻结回放前端，要求全可见来源及出处，保留合成/接口观测区别，不宣称经验标定。380项Python、28项前端测试通过；3事件60篇冻结对照，6份旧预算输出一致、3个新网格运行未提升最终方向证据。浏览器合成场景完成12轮，0模型请求。下一步先解决示例预算下远端网格不可执行、采集可比接口成本观测，再做证据到达回放和独立评价；新事件页面尚未迁移新规则。详见[交付与下一步门槛](source-cost-grid-delivery.md)。

## 候选读取与执行预算优化（2026-10-23）

[0201]增加显式预算可执行检查和查询前可读性检查，保留[0205]逐格公式；借鉴论文代码的分块BM25只用于已授权来源/时间范围内排序，保留完整原文、五要素准入及整带回收判据。前端冻结重跑已接通。393项Python、29项前端测试通过；3个已用事件60篇、15组新运行，9份历史输出完整一致。读取42→51、模拟消耗94→69.4包含网格参数变化；同新网格下读取保持51、预算检查将82.4降至69.4。BM25未增加本批有效证据，最终方向证据仍为0。焦点第7轮观测到边界外证据，但整带成本12.6>单轮8.33而被阻止。下一步成本标定与准入失败例诊断，不盲目扩大评价。详见[优化交付](retrieval-optimization-delivery.md)。


## 2026-10-23 — 证据规则与新事件入口统一

完成显式 patent_elements_v1、全入口传递、共享/按需冻结执行、完整候选正文与调用账本。432 Python /34前端测试、15旧输出一致、1401保存运行验证通过。3事件60篇9次新开发运行全部0.5，准入0/60，通用解析/支持覆盖未完成。下一步先补停火、计数、议会解散任务契约与可溯源要素规范化，之后成本标定、到达回放和未使用事件独立评价。详见 evidence-entry-delivery.md。


## 2026-10-23 — 三类任务语义闭环

三类任务的结构化条件、原文规范化、断言冲突和时间规则已接入前后端。60篇既有开发文档的全量诊断准入为0/60篇（v1为0/60），但方向性证据仍为0，9次策略运行均为0.5；本轮不宣称预测质量提高。 511 Python/41前端测试通过；24旧输出一致；1419运行完整性通过。保留首轮误绑定诊断，最终批次采用semantics-v2-final-20261023。下一步先补可判定真实事实覆盖，再做真实标定、到达回放与独立评价。详见semantics-v2-delivery.md。


## 2026-10-23 — 截止前事实覆盖与抽取窗口

已扩展检查到三个既有事件的527篇截止前可见正文，找到可追溯的事件进展报道和抽取入口缺口。决定性事实及任务条件尚未全部闭合，未进入标定或独立评价。 28原始文件/527正文核验，585候选片段；发现存档链接正文和超长聚合页。fact_window_v1已接共享/按需但保持显式可选；525窗口未发送，覆盖568→570净增2。530 Python通过，9旧输出一致，0新模型调用。详见fact-coverage-delivery.md。


## 2026-10-23 — 跨句事实关联与准入/支持分离

显式patent_elements_v3与工作台入口已加入。7篇开发案例14次真实抽取、28130 tokens；同标注v2→v3准入0/7→3/7，方向性0，概率仍0.5。审查修复后复用标注离线复验，9旧输出一致，未标定/未独立评价。详见[cross-sentence-delivery.md](cross-sentence-delivery.md)。


## 2026-10-23 · v4事件时间与进展支持

已交付可选v4；597项Python、44项JS通过，15份旧结果一致，1455运行核验。7篇冻结案例3篇准入但0方向，60篇原标注0准入；0新增模型请求。标定与独立评价暂不启动，下一步按事实日期、动作条件和计数口径补齐开发证据。见[交付](temporal-progress-delivery.md)与[缺口清单](temporal-progress-data-gaps.json)。

## 历史正文与逐条来源缺口核查（2026-10-23）

新增只读历史正文候选恢复与查询层回归；三既有事件527个最新正文扩展核查至595个去重URL＋正文版本，新增68历史版本、94候选片段，恢复1个原被空壳遮蔽的议会报道窗口。片段/版本不计为独立事实。另查39个计数相关跨事件正文版本，未检出指定计数器词项。保留三任务14段完整说明及7篇冻结标注实际读取覆盖（事实窗口12/12既有证据段）。可靠事件日期与合规计数来源仍未补齐；无新模型调用、无标签读取，默认预测输入和规则未变。606项Python测试通过，独立只读复核问题已修复。最终产物source-gaps-final-20261023；详见[source-gaps-delivery.md](source-gaps-delivery.md)。
