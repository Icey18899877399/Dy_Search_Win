# 阶段十三：证据损失、回收决策与参数调整

2026-10-23。本轮完成显式诊断和运行时参数接口；默认调度保持不变。所有代码、试验、日志和临时文件位于 D:\27专利\事件预测动态检索窗口，原始数据只读，没有新增模型请求。

[打开链路报告](../artifacts/phase13-chain-20261023/index.html) · [执行计划](phase13-chain-plan.md) · [实验独立核验](phase13-experiment-check.json)

## 已补齐

|链路|实现|可检查内容|
|---|---|---|
|证据损失观测|engine.run 的 decision_trace|决策前窗口当量、过渡带逐篇权重与损失贡献；区分回收后的当量|
|回收决策|decision_trace.recovery|来源资格、预算各项上限、请求/读取预留、跨度、净收益候选值、冷却状态及未执行原因|
|窗口调整|boundary_adjustment 与 contraction|证据进入/移出、收缩前后损失、探测是否完成、收缩上界与拒绝原因|
|参数调整|runtime_policy.py；engine.run 和 run_on_demand 均接入|紧迫度与剩余预算插值，实际更新降频倍率、守候份额、共用配额；守候额度只在进入时锁定|
|标定观测|calibration_observations.py|专利 [0249] 三指标按来源总量归一；[0250] 同类事件真实酝酿期高分位与中位跨度；不足样本显式返回 underidentified|

参数表需要明确的跨度来源、任务时限、预算单位和完整矩形档位。越界默认报错，只有显式 clamp 才截断并记轨迹；不接受把外部输入自称为独立验证的实测标定。时钟仍为模拟运行时长，证据 cutoff 不变。轮首查表，轮末进入 slow 时用该轮表值锁定额度；slow_fraction 不随表改变。

## 根因与单变量结果

焦点事件 2354063 的 cc2515… 文档是程序进展证据，不是最终解散证明。

- enhanced 第17轮：有效预算 8，回收预留 2；9 来源请求开销 1.8，加读取预留 1。可回收跨度 max(0,(2−1.8−1)/0.45)=0。net_gain=null 是尚未进入收益门槛，不是收益为负。
- basic 第1轮：额度 5，回收跨度 4.888889 天，证据进入窗口；第2轮决策前损失为0，收缩3.5天后移出此证据。诊断现可直接展示进出文档。
- enhanced 将单轮预算从20改40，出现6次回收扩窗，但最终方向证据仍为0；回收成功不保证最终保留。
- basic 单独把单轮预算改40或回收份额改0.5，最终保留1条方向证据；其余变化详见报告。这些是开发敏感性现象，不能据此挑选最优参数或声明准确率提高。
- 单改 slow_multiplier、waiting_share、shared_quota 没有解除本例最终无方向证据状态；显式合成参数表验证了联动入口，不冒充实测标定。

## 验证与复现

- 18 个此前已检查事件，356 篇有效文档；54 份新输出去除新增诊断后，与阶段十二保存的完整输出逐字段相同。
- 16 次单变量对照、2 次明确标为合成的运行时表联调；没有读取结算标签计算新的质量分数。
- 304 项 Python 测试通过，20 项前端模型测试通过。测试覆盖参数单调性、表格插值、额度锁定、任务截止、按需入口、预算拒绝、收缩解释和输入不变性。
- 新实验75个文件、108个来源文件哈希与逐轮算术已独立核验。运行首次中断的副本单独保留在 interrupted 目录，没有完成清单，不属于正式实验。

```powershell
Set-Location 'D:\27专利\事件预测动态检索窗口'
$pythonExe = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $pythonExe -B scripts/verify_phase13.py artifacts/phase13-chain-20261023
# 重跑使用新空目录，保护原实验
& $pythonExe -B scripts/run_phase13_chain.py --output artifacts/phase13-chain-repeat
```

模块入口：

```python
# 默认 trace=False；打开只增加解释，不修改默认计算。
result = run(task, documents, config, annotations, decision_trace=True)
# profile 的完整合成格式可在 runtime-demo/enhanced.json 的 provenance.runtime_policy 查看。
result = run(task, documents, config, annotations, runtime_policy=profile)
result = run_on_demand(task, documents, config, client,
                       decision_trace=True, runtime_policy=profile)
```

`normalize_source_costs` 需要来源、真实响应延迟、限流配额、返回数量、相同观测窗口和配额单位及来源凭据。其 cost_per_day 仅在 config_compatible=True 且已确认模拟预算单位时，才可显式映射到 source_parameters；不会自动把货币换算成模拟预算。`estimate_incubation_band` 需要 first_relevant_evidence_at / event_occurred_at、两个时刻的出处、事件类型和标定截止；拒绝发表间隔代理，截止后事件不纳入。

## 交付边界与后续顺序

本轮是代码接口和独立离线报告交付，新参数表未发布为原前端默认策略。仍缺真实来源成本与覆盖观测、历史同类事件酝酿期、独立验证过的档位表，尚未完成实测标定或真实冷缓存成本比较。

专利 [0252] 是整过渡带回收；当前保留的部分跨度回收为工程变体，basic 绕过净收益门槛为对照策略。常规单轮预算仍为显式配置，尚未按总预算/计划轮数派生。已经明确记录这些差异，没有将其写成完全忠实实现。

后续先补整带回收和预算派生的显式专利对照模式，采集满足字段与出处要求的来源/事件历史观测，冻结标定结果，再选择未用于开发的事件开展真实调用成本与预测评价。当前已检查18事件只作开发回归。

历史校验补充：1,376 份已保存运行与8,154次历史源文件归档检查通过（phase13-artifact-check.txt）。报告在1366/900宽度均无页面溢出、无脚本错误，逐轮折叠表和所有本地链接检查通过（phase13-browser-check.json）。
