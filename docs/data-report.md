# 数据适配与时点隔离报告

实现：`src/dynamic_retrieval/data/store.py`。纯 Python 标准库和 SQLite。源目录 `D:\agents-main\agents\polymarket\data` 仅做枚举、读取和 SHA-256，未写入、移动或修改权限。

## 实际结构映射

| 结构判别字段 | 实际含义 | 索引用法 |
|---|---|---|
| 顶层 `collected_at`，`events[].markets[]` 含 `description` 和 `outcomes` | 完整市场元数据 | 在截止时刻前选择最后一条完整记录；只输出题目、规则、选项和归档时间，不输出价格、最终状态或标签 |
| 顶层 `scraped_at`，`events[].articles[]` 含 `full_text` | 正文抓取快照 | 正文 observed_at 取该批次 scraped_at；`published_at` 和 observed_at 同时满足截止时刻；不拿 created_at、文件日期或首次 URL 命中冒充正文可用时刻 |
| `events[].news.newsapi_articles/google_news_articles` | 元数据检索结果，常见于 market 文件 | 保留可审计的记录，未抓取正文的摘要或 description 不作为全文输入 |
| 抓取快照的 `markets[]` 只有 market_id/question | 部分市场元数据 | 只有截止前没有完整元数据时才使用；标记 `partial_inferred_binary`、description 为空、Yes/No 为明确推断 |
| 顶层 `resolved_markets[]`、`recorded_at` | 代理标签 | 独立 labels 表和显式 labels() API；统一 `is_proxy=true`，不会经 tasks()/documents() 进入预测 |
| 根目录运行日志、事件池、manifest 及未知类型 | 非预期新闻/任务数据 | 每个 JSON 纳入文件清单并标记 unrecognized；不递归把任意字段当正文 |

文件夹名称不能可靠表示结构：例如 market/2026-08-28.json 实际是抓取正文快照；raw_news 的市场信息常为部分元数据。适配以字段判断，ground_truth 路径额外禁止作为新闻入口。

## 版本与来源策略

同事件、同规范化 URL 在数据库保留历史快照；预测查询仅返回截止前最后一条有正文且抓取未失败的版本。后来的失败记录不会清空此前成功正文。URL 只去 fragment、已知跟踪参数以及规范化域名；保留业务 query 和路径大小写。优先 resolved_url，缺失时用 url。来源为发布方名字的大小写/空白规范化，发布方缺失才用 URL 域名；provider 单独保存。未合并发布方别名，避免凭空声称这些来源独立。

记录 ID 依据内容字段计算 SHA-256，排除文件路径；相同快照跨文件重复只计一次。同 URL 不同正文仍保留。所有可比较时间统一为带六位微秒的 UTC ISO 字符串；无时区、缺时间、无法解析时间均排除并计数，不用文件名猜测。

## 安全与资源

SQLite 先在输出目录构建临时库，事务提交与 quick_check 后替换正式库。源目录内禁止生成数据库；已有数据库须同时匹配本应用标记和源路径才允许重建，防止覆盖无关数据库。逐 JSON 文件解析和入库，不把整个归档装入内存。正文按 SHA-256 仅存一份 zlib 压缩内容，快照记录保留时间、URL、状态等元数据；查询时无损解压为相同公开 API 的 text。文件清单包含相对路径、大小、可读取文件的 SHA-256、结构类别、排除计数和错误。源读取失败时处理剩余文件，但将覆盖状态明确标为 partial_source_read；没有为不可读文件伪造 SHA-256。数据库内部亦保存 audit，可与旁边 audit.json 核对。

## 验证

测试先编写，首次运行出现 5 个预期的缺适配功能失败，然后实现；增补不可读文件测试后观察 PermissionError，再实现可审计的跳过；覆盖状态字段同样先验证缺失再实现。最终数据测试命令：

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests -p test_data.py -v
```

使用已提供的 Python 3.12.14 标准库运行，15 个数据测试通过。测试涵盖错目录结构、旧完整元数据优先于较新部分信息、未来完整记录隔离、未来发布时间、同 URL 正文更新、后续抓取失败、标签隔离、缺失/无效时间、畸形 JSON、确定 ID、跨文件重复、重复构建、未知数据库防覆盖、源目录禁写与源文件不可读、已知非二分类题目禁用推断二分类、事务失败保留旧库、重复正文压缩与 Unicode 往返一致，以及 audit.json 保留名禁用。

## 全归档执行

完整遍历执行完成，退出码 0，耗时 423.2 秒；最终数据库已通过 SQLite quick_check。统计见下面结果和最终目标目录的 `artifacts/audit.json`。已遇到源文件系统 PermissionError；按用户指定源路径以沙箱外授权读取重试后，部分文件仍不可读。只做只读诊断，未修改源 ACL。不能据此将当前索引称为所有源记录的完整索引。

原始未压缩快照方案曾在 C: 构建时触发 database or disk is full，未发布不完整数据库，仅清除本次临时库和 journal。随后增加正文内容寻址与压缩，通过测试后改在用户授权的 D: 最终目标 artifacts 直接构建。重试前 C: 可用 2,967,076,864 字节、D: 可用 316,885,905,408 字节，未进行其他磁盘清理。


## 最终真实归档结果

最终数据库：`D:\27专利\事件预测动态检索窗口\artifacts\index.sqlite`，大小 1,550,569,472 字节；旁边为 `audit.json`。索引构建完成，但源覆盖状态明确为 **partial_source_read**。

| 指标 | 数量 |
|---|---:|
| 枚举 JSON | 414 |
| 枚举源文件字节 | 4,527,414,021 |
| 可读取并有 SHA-256 的 JSON | 396 |
| 不可读取 JSON | 18 |
| JSON 解析失败 | 0 |
| 非新闻/任务结构 JSON | 3 |
| 完整元数据和新闻混合快照 | 136 |
| 部分元数据和新闻混合快照 | 139 |
| 可读取标签快照文件 | 118 |
| 存储文章观察记录 | 1,005,155 |
| 有效正文观察记录 | 434,992 |
| 全局唯一正文 | 56,954 |
| 唯一正文压缩字节 | 176,111,532 |
| 有正文的事件+URL | 48,829 |
| 唯一 market_id | 1,270 |
| 市场元数据历史记录 | 151,748 |
| 代理标签历史记录 | 280,654 |
| 发布时间晚于批次观察时间的记录 | 33 |

18 个不可读文件为 ground_truth/2026-04-11 至 04-14、04-18 至 04-30 共 17 个日快照，以及根目录 run_log.json。授权沙箱外读取重试仍 PermissionError；Get-Acl 只读诊断亦被拒绝。所有 market/raw_news JSON 均可读且完成结构处理。未识别的 3 个文件是 `.cloud_manifest.json`、`event_history.json`、`event_pool.json`，它们保留文件级 hash 和结构记录，没有被当作新闻导入。不可读文件只有路径、已知大小和错误，没有伪造 hash。

所有正文成功记录的 scrape_status 为 success。其余记录状态计数：metadata_only 496,434；failed_download 46,753；failed_extract 17,086；skipped_paywall 6,109；failed_resolve 3,712；watchdog_timeout 69。空正文 570,163 条不进入 documents()。33 条发布时间异常记录仍保留审计，查询需要 published_at 和 observed_at 同时不晚于截止时刻。

截止 2026-08-29T00:00:00Z 有 1,270 个任务，其中 1,266 个 full_metadata、4 个 partial_inferred_binary。部分任务 market_id 为 1163699、3758940、601836、682723，均明确标识规则缺失和选项推断。代理标签类型为 price_collapsed 253,032 条、expired 27,622 条，均非官方核验真值。

样本实查：market 1006891 与 1006892（event 33647）各有 47 篇可用正文；1094735（event 140376）有 393 篇；1105740 与 1105741（event 143443）各有 1,071 篇。同事件的市场共用新闻库，不代表独立文章样本。

冻结产物 SHA-256：

- index.sqlite：`00a37f4f5a533a97c75184b88146a50d289f150649a4964dd03b4bd6bb34211e`
- audit.json：`98647f300d66a144e678b679bffac6a7712479f1ecc608b5e6c350db3fb45d89`


## 最终审查修复及现有索引适用性

审查后补测并修复两个边界：

1. `outcomes` 一旦显式提供，就独立检查是否 Yes/No，不再依赖 description 是否存在。明确非二分类记录保留为排除标记，阻止后续部分记录凭空推断 Yes/No；显式反序 `["No","Yes"]` 按原顺序保留。只有完全缺少有效选项的部分记录才推断 `["Yes","No"]`。带明确二分类但缺规则的部分记录标为 `partial_explicit_binary`，仍不能覆盖截止前完整元数据。
2. 两个产物按小 audit 先发布、SQLite 后原子替换提交。发布新 audit 失败时数据库未改变；数据库替换失败时用预先保存的同卷旧 audit 恢复，测试验证旧数据库和旧 audit 字节均保持一致。如文件系统连恢复动作也拒绝，则抛出明确错误并保留旧 audit 恢复文件，不静默丢弃恢复材料。此为运行异常的一致性策略；两个独立文件的断电级原子提交不作声称，数据库内嵌 audit 是已提交库的权威审计副本。

新增用例先得到 3 个预期行为失败，再修复；包括无 description 的明确非二分类、部分元数据反序选项和 audit 发布注入失败。另注入数据库发布失败验证 audit 回滚。最终共 15 个数据测试通过。

未重新构建真实索引。仅对 139 个 partial+articles 源快照进行只读元数据核查，耗时 54.2 秒，共 76,841 条部分市场观察，**全部没有 outcomes 字段**；因此这些真实记录不存在被错误改写显式选项的情况。存储的 74,907 条完整元数据选项全部为 `["Yes","No"]`。数据库内嵌 audit 与旁边 audit.json 经结构比较完全一致。现有真实索引不需要元数据迁移，冻结产物 hash 保持不变，源读取失败数仍为 **18**。

将来若源归档新增受影响结构，可在 D: 上复制已验证数据库，单独从源快照重建 tasks 表并在事务内替换；保留 bodies、documents、labels 和原始文件 manifest。核对新的任务/质量统计及 quick_check 后再按上述一致发布策略提交数据库和对应 audit，不需要重复抓取或重建百万条新闻记录。本次没有执行该增量迁移。
