# Dy_Search_Win · 事件预测动态检索窗口

面向《一种面向事件预测的动态检索窗口调度方法及系统》的研究原型。提供固定窗口、基础调度、增强调度三种模式，以及本地可视化工作台、自动语义抽取、逐轮证据诊断和可追溯实验输出。

**当前定位：机制已实现的离线研究系统，尚未完成真实参数标定与独立效果验证。** 代码运行成功、测试通过或方向性证据增加，都不能直接解释为预测准确率提升。

## 快速运行

Python 3.11+；Python运行与测试仅使用标准库。前端无需构建，ECharts已随仓库保存。Node.js 22+仅用于前端逻辑测试。开发与本次发布在Windows / PowerShell验证。

```powershell
git clone https://github.com/Icey18899877399/Dy_Search_Win.git
Set-Location Dy_Search_Win

# 不需要原始数据、API密钥或GPU
python -B test.py
python -B run.py demo --output artifacts/demo
python -B run_web.py --port 8765
```

打开 http://127.0.0.1:8765/ 浏览工作台；合成演示报告也可直接打开 `artifacts/demo/report.html`。演示使用构造数据，不是真实预测成绩。尚未建立真实数据索引时，新事件列表不可用，演示和本地结果浏览仍可使用。

前端测试：

```powershell
$tests = @(Get-ChildItem tests -Filter '*.mjs' | ForEach-Object { $_.FullName })
node --test @tests
```

## 仓库结构

| 路径 | 内容 |
|---|---|
| `src/dynamic_retrieval/` | 调度引擎、专利数学机制、证据处理、数据索引、模型适配与本地服务 |
| `web/` | 原生JavaScript工作台与本地ECharts资源、许可证 |
| `tests/` | Python/JavaScript行为测试，含独立可用的小型任务定义夹具 |
| `configs/` | 固定、基础、增强策略及任务规则示例 |
| `scripts/` | 开发诊断、历史回放、来源观测与交付校验工具 |
| `docs/` | 设计、专利对应关系、使用指南、阶段交付和已知缺口 |
| `.github/workflows/ci.yml` | 无密钥、无原始新闻依赖的自动测试与合成演示 |

常用入口：`run.py`（索引/任务/单次运行/对照/演示）、`run_web.py`（工作台）、`run_deepseek.py`（语义抽取）、`run_pipeline.py`（自动流程）、`run_quality.py`（评价）。各入口使用 `--help` 查看参数。

## 接入自己的数据

本仓库不附带原始新闻、市场全量快照、SQLite索引、模型缓存或历史实验输出。原开发环境的数据目录为 `D:\agents-main\agents\polymarket\data`，作为只读输入；其他环境请显式指定自己的归档目录。

```powershell
python -B run.py index --data 'D:\agents-main\agents\polymarket\data' --db artifacts/index.sqlite
python -B run.py tasks --cutoff '2026-05-15T23:59:59Z' --limit 10
# 将市场ID和截止时间替换为实际任务
python -B run.py compare --market 559684 --cutoff '2026-05-15T23:59:59Z' --output artifacts/my-comparison
```

索引按归档内部结构识别市场元数据和新闻正文。发表时间与该正文版本的采集时间必须同时不晚于预测截止时间；结算标签只用于预测后的评价。详见[数据说明](docs/data-report.md)。

DeepSeek抽取需要在启动进程的运行时环境中设置 `DEEPSEEK_API_KEY`；切勿把实际密钥写入配置、脚本或Git提交。自动标注保持 `reviewed:false`。本地规则、合成演示与缓存回放不需要密钥。

## 已实现机制与使用边界

- 五要素规范化、交集比例准入、精确事实键归并、重复来源几何折减与事态概率计算。
- 来源节律、预算覆盖、空尽判断、过渡带损失、边界回收/收缩、守候与停止原因。
- 显式专利预算、整带回收、逐格预算及来源成本配置；保留历史策略，避免改写旧实验。
- 可选 `patent_elements_v4`：有限任务契约、原文绑定、事件时间与生效时间区分、非终局进展相容规则。
- 新事件选择 → 截止时间 → 冻结输入 → 共享/按需抽取 → 三策略运行；工作台可查看每轮证据与预算。
- 历史正文恢复检查：最新归档为技术空壳时，寻找截止前的实质正文候选；不覆盖实质性更正，不自动替换预测输入。

**重要限制：** 默认参数仍含示例值，语义规则仅覆盖有限句型。当前调度面对固定截止可见归档，尚不能据此声称真实在线来源已经空尽。模拟预算、API tokens与实际费用分别记账。原文缺失的日期、任务条件和计数来源不能靠扩大窗口或降低准入阈值补造。

## 当前开发状态（2026-10-23）

最近本地开发验证为606项Python测试通过；这属于工程验证，不是独立预测评价。公开源码的干净目录验证记录见[发布验证](docs/release-validation.json)。

- 三个既有开发事件已核查595个去重URL＋正文版本，新增检查68个历史版本，恢复1个完整正文候选。
- 7篇冻结开发案例的事实窗口包含12段既有证据段；v4仍为3/7准入、0/7方向性支持。
- 可靠事件日期、完整条件判定和指定口径计数来源尚未补齐；真实标定与独立评价未完成。
- 正文版本数、转载数和开发重复回放数均不能当作独立事实或独立样本数。

这些数字来自原本地开发工件。本仓库提供代码、说明和小型测试夹具；全量历史工件保留在原D盘工作区，未随源码发布。

## 文档入口

- [文档导航](docs/README.md) · [模块与执行说明](docs/repository-guide.md)
- [专利条款与实现映射](docs/patent-map.md) · [设计说明](docs/design.md)
- [工作台使用指南](docs/frontend-user-guide.md) · [新事件操作流程](docs/fresh-workflow-user-guide.md)
- [最新来源缺口与后续工作](docs/source-gaps-delivery.md)
- [事件时间与方向支持v4](docs/temporal-progress-delivery.md)
- [开发进度记录](docs/progress.md)

历史文档保留阶段性参数、结论和本机路径；其中指向 `artifacts/`、生成HTML/JSON或日志的链接需要原本地工件。不能把旧阶段结论当作当前版本结论。

## 数据与第三方资源

原始归档只读，运行输出默认写入 `artifacts/`，临时文件写入 `.runtime/`；两者均不提交Git。测试夹具仅含三个公开任务的冻结定义，不含新闻全文、预测标签或API响应。其来源与哈希见 `tests/fixtures/task-contracts/manifest.json`。

ECharts保留原许可证与NOTICE，见 `web/vendor/`。专利全文未包含在源码仓库内。
