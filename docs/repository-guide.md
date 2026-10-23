# 源码组织与复现范围

## 主要模块

| 模块 | 职责 |
|---|---|
| `data/store.py` | 归档审计、SQLite索引、双时间截止、正文版本选择 |
| `core.py`、`engine.py` | 独立当量、概率、来源空尽、损失、预算与调度状态机 |
| `evidence.py`、`patent_evidence*.py` | 任务/事实要素、原文见证、准入与事态相容规则 |
| `fact_coverage.py`、`source_history.py` | 原文片段覆盖与历史正文诊断候选 |
| `semantic.py`、`semantic_pipeline.py`、`on_demand.py` | 模型协议、冻结输入、共享/按需抽取及缓存 |
| `calibration*.py`、`source_cost_profile.py`、`runtime_policy.py` | 显式观测转换、成本与运行档位接口 |
| `official.py`、`quality.py` | 官方结算数据及预测后评价 |
| `web_server.py`、`web_backend.py`、`web_jobs.py` | 本地HTTP服务、任务浏览和后台执行 |
| `web/` | 工作台视图、图表、操作表单和可单独测试的前端模型 |

## 两类复现

**源码自包含验证：** `python -B test.py`、Node前端测试、`run.py demo`，仅使用本仓库代码和夹具。测试中的HTTP接口/模型客户端使用本地服务或替身，不要求真实DeepSeek密钥。

**历史真实数据复现：** 需要原归档、冻结输入、机器标注、历史源码哈希和相应实验manifest。`scripts/verify_artifacts.py`、历史回放脚本以及来源缺口审计脚本属于这一类，不能在空白下载目录中假定已经存在原实验。原文描述的真实样本结果不会因下载源码自动复现。

## 本次仓库整理

- 保持已有模块目录、公共入口和预测算法不变，添加Git排除规则、文档导航与CI。
- 将语义回归测试读取的三个冻结任务定义逐字复制到`tests/fixtures/task-contracts/`，调整测试定位；不改变任务内容或断言。
- 原本地README保存在`.runtime/publication-backup/README.md`；完整历史实验仍保存在原`artifacts/`目录。
- 上传源码、全部测试、前端依赖的许可证、配置、Markdown开发资料及发布验证摘要。
- 不上传原始新闻/市场语料、数据库、模型缓存、运行日志、专利PDF、历史实验输出和本机交付清单。

## 后续开发约束

原始数据只读；密钥只由运行时环境读取；机器标注保持`reviewed:false`；历史工件不得覆盖。修改预测模块前，应使用已有归档工具保留历史运行依赖的源码，继续区分专利路径和显式工程变体。

下一阶段先解决原文事件日期、任务条件和真实计数口径，再开展真实标定、证据到达回放和未参与开发事件的独立评价。不要用测试数量或重复运行数量代替研究效果证据。
