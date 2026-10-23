# 数据、CLI、评估与 HTML 独立审查

审查日期：2026-10-22。范围：`docs/design.md`、实施计划 Task 1 / Task 3、`data/store.py`、`cli.py`、`evaluation.py`、`report.py`、`demo.py`、数据与 CLI 测试。只读检查源码；只新增本报告。未执行全量索引，全部复现使用自动清理的临时目录。

## 结论

时点查询、标签隔离和 HTML 转义的主要实现符合设计。本次独立审查复现的 4 项问题均已由其他工作线程修复，并在本审查中定向复验；当前未保留本范围内的阻断项。最新完整测试为 **43 tests，OK**。本结论仅覆盖离线代码与临时夹具，不替代真实数据完整性、真实 pilot 完成状态及最终目标目录复验。

源码由其他工作线程同时修正。本报告将已经看到修复并通过测试的项目单独标注，避免把历史复现误报为当前缺陷。行号是本次阅读时的位置。

## 已修复问题及独立复验

### [P1] pilot 直接用归档 market_id 拼接输出路径，可越过 --output

**状态：已关闭。** 当前 `cli.py:30-34` 使用 `market_directory`，只保留安全标识符，其余映射为稳定哈希；pilot 使用该映射。独立检查 `../escaped`、`../../x`、`D:\\escape`、`m/child` 和正常标识符，解析后的所有路径均在指定输出目录内。新增回归 `test_untrusted_market_id_cannot_escape_output_directory` 通过。以下为修复前证据。

- 位置：`src/dynamic_retrieval/cli.py:108`（`args.output/str(task['market_id'])/mode`）。
- 原因：market_id 来自归档 JSON，既未限制为路径安全的标识符，也未在写入前检查解析后路径仍处于指定输出目录。
- 临时夹具：完整 Yes/No 市场的 `market_id` 为 `../escaped`，包含一条时点合格正文；建立临时索引后执行 `pilot --db <tmp>/index.sqlite --cutoff 2026-01-03T00:00:00Z --count 1 --min-documents 1 --output <tmp>/requested`。
- 实际：命令退出 0，生成 `<tmp>/escaped/fixed/result.json`，而非 `<tmp>/requested` 内的文件。绝对路径或更多 `..` 也会改变写入位置，可能覆盖已有同名产物。
- 期望：拒绝不安全的归档标识符，或以稳定编码/哈希构造目录，并在写入前确认目录包含关系。保持产物里的原始 market_id。
- 对应设计：数据只读、输出路径显式、真实任务回放可复核；实现计划 Task 3 的 CLI 集成行为测试。回归应覆盖 `..`、绝对路径、Windows 分隔符及正常标识符。

### [P2] 数据库文件命名为 audit.json 时，成功索引被自身审计文件覆盖

**状态：已关闭。** 当前 `store.py:247-248` 在写入前按不区分大小写的文件名拒绝保留名称，新增回归 `test_reserved_audit_filename_cannot_be_the_database_output` 通过。以下为修复前证据。

- 位置：`src/dynamic_retrieval/data/store.py:245`、`:317`、`:318`。
- 复现：在新临时目录建立包含 `{}` 的归档；调用 `build_index(archive, tmp/'audit.json')`。
- 实际：函数正常返回 `dynamic-retrieval-index-v1`，目标前 16 字节为 JSON 文本；随后 `Store(tmp/'audit.json')` 抛出 `DatabaseError: file is not a database`。
- 原因：`audit_path` 与 `db` 相同，第二次 `os.replace` 将刚完成的 SQLite 覆盖为审计 JSON。
- 期望：任何写入前拒绝数据库与审计输出同路径，并考虑 Windows 文件名大小写等同关系。
- 对应设计：Task 1 的 SQLite 安全索引与显式错误；当前成功返回不能保证输出可用。

### [P2] 导入报告的 source new_count 会在前端变成未转义 HTML

**状态：已关闭。** 当前 `report.py:34` 使用 `esc(v.new_count)`。用同一恶意夹具再次运行页面脚本：`unsafe source row: false`，`escaped source row: true`。此次复验执行了 Node VM 中的实际页面 JavaScript 与最小 DOM 替身，验证 DOM 输出，没有在真实浏览器中触发恶意事件。以下为修复前证据。

- 位置：`src/dynamic_retrieval/report.py:34` 的 `'<td>'+v.new_count+'</td>'`。
- 复现：取得 `demo_result()`，把各轮 `source_states` 中一个来源的 `new_count` 设为 `<img src=x onerror=alert(1)>`，再调用 `render_report` 或 `report` 命令。用 Node VM 运行页面脚本，提供记录 innerHTML 的最小 DOM 替身，可观察到 `sources.innerHTML` 中保留完整 `<img ... onerror=...>`。
- 实际：JSON script 块正确把 `<` 转为 Unicode 转义，所以现有“HTML 文件不得出现原始 img”测试通过；浏览器 JSON.parse 后却将该字段原样插入 innerHTML。真实浏览器解析该 HTML 时可触发事件处理器。
- 边界：正常引擎输出该字段为整数；风险入口是 CLI 已提供的任意 result.json 报告导入，当前未校验其字段类型。
- 期望：对该字段同样使用 `esc` 或安全的 textContent，并增加前端 DOM 层面的恶意夹具测试；仅检查生成 HTML 的原始文本不足以覆盖此路径。
- 对应设计：Task 3 的自包含安全 HTML、恶意夹具与转义测试。

### [P2] 比较产物未冻结输入池、人工注释和实际评分标签的来源

**状态：已关闭。** 当前 result.provenance 保存全部可见候选的标识/来源/时点及正文摘要、可见注释快照与摘要；manifest 增加输入摘要、注释摘要和源码摘要；comparison 保存 `label_records`、`label_sha256` 及各模式 `input_sha256`。新增 `test_manifest_records_input_and_annotation_fingerprints` 通过。原始正文仍需由只读归档/索引提供，摘要可校验是否是同一输入；没有把代理标签并入预测输入。以下为修复前证据。

- 位置：`src/dynamic_retrieval/cli.py:29-39`、`:125-136`；`src/dynamic_retrieval/evaluation.py:19-21`。
- 当前证据：manifest 仅含 `format_version/files/python/mode/market_id/cutoff/visible_documents/config_sha256`。comparison 仅含标签状态、数量与类型等汇总，没有实际标签记录、observed_at/source_file 或标签摘要。
- 影响：CLI 在一次进程内确实把同一 task/docs/annotation 对象传给三种模式，未发现当前执行时对照不公平；但保存产物无法证明或重建全部可见候选正文与全部注释，未入选正文不会完整出现在 evidence.json，未使用注释也不会导出。以后重建索引或标签更新后，无法仅凭该次比较产物确定所用的代理标签版本。
- 期望：保存或引用不可变的 task、完整可见候选集/其摘要、输入注释/其摘要、索引审计标识；在预测完成后单独保存本次标签快照及其摘要/出处，保持预测输入与标签分离。comparison 关联三份运行 manifest 的摘要。
- 对应设计：数据来源可审计、标签隔离；Task 3 要求相同冻结注释、真实三模式比较和运行 manifest/hashes。此项为可复现性缺口，不代表已发现未来正文泄漏或标签进入预测。

## 已核实通过的设计点

- `utc_iso` 要求显式时区并统一为 UTC 六位微秒；数据库查询同时约束 `published_at <= cutoff` 与 `observed_at <= cutoff`，先过滤再按 URL 选最新合格成功正文。未来版本不会遮蔽截止前版本；后续失败抓取不会清空成功正文。
- 同 URL 保留历史版本，跨文件相同记录去重；来源由发布方或 URL 域名产生，provider 保留为检索渠道。`source` 字符串或 `{name/id}` 对象有适配路径，未知形状保守回退为域名。
- task 输出采用字段白名单；labels 是独立表、独立显式方法。run 不调用 labels；compare/pilot 先运行预测，再独立取 labels 评分。proxy-only、冲突代理标签不评分、verified_brier 为 null 的行为清楚。
- 写入已有 SQLite 前校验应用标记和源根目录；源树内禁止索引输出；临时 SQLite 事务、quick_check、只读 Store、SQL 参数化查询均存在。
- 标题、证据标题/摘录/要素和来源名字有转义；script 块中的 `< > & U+2028 U+2029` 有安全序列化；无外部 CDN。上述通过点不消除本报告列明的 new_count DOM 注入。

## 审查期间已修复并复验的项目

- 初始缺失索引会抛 `sqlite3.OperationalError` 并打印 traceback；目前 `cli.main` 已捕获 `sqlite3.Error`，`test_missing_database_gives_actionable_error_not_traceback` 通过。
- 初始评分用 probabilities[0] 假定 Yes，且引擎拒绝反序 No/Yes；目前反序选项支持及按 Yes 位置评分的新增测试通过。
- 初次完整测试曾见“已知非二元市场又被部分快照推断为二元”和“仅回收来源同轮 exposure 未更新”失败。它们由其他工作线程处理；本次最后完整测试已通过对应回归。

## 验证记录

运行：`C:\Users\18899\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe test.py`，工作目录为项目根。

最后一次输出：**43 tests，OK**，用时约 1.32 秒。除完整测试外，定向复验了修复后的安全路径映射和实际报告 JavaScript 的 DOM 转义；保留文件名拒绝、指纹保存、CLI 缺失索引和反序选项评分均有通过的行为回归。本审查未改动源码或测试。未检查全量真实数据是否可读或 pilot 是否已完成，这由负责实际索引执行的工作线程验证。
