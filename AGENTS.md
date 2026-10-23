# Project instructions

- 用户明确要求本项目所有代码、缓存、报告和临时数据均在 D:\27专利\事件预测动态检索窗口；直接在此开发，不要创建 C 盘开发副本。
- 原始数据 D:\agents-main\agents\polymarket\data 只读。
- 测试与一次性运行临时目录使用项目内 .runtime；test.py 已固定 TEMP/TMP。
- DeepSeek 密钥只从运行时环境读取，不写入任何项目文件或日志。
- 无需人工审核门槛；机器标注必须保持 reviewed:false。
- 保留历史实验及内容哈希。价格代理不能当官方真值；结构通过不能当语义正确或预测质量成立。
