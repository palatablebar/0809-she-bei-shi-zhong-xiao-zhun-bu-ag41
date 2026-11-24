# 设备时钟校准簿

工厂数据采集工程师可在工作台上传来源 CSV，对照规则判断差异，签发合格批次或记录暂缓意见。

以两侧可信同步点做分段线性校准并拦截外推。异常按检查点与相邻同步点归因：设备漂移、基准跳变或证据不足（冲突时保留不确定），并标出受影响读数；输入、隔离与诊断对账一致后才能发布。

## 启动

```sh
docker compose up --build -d --wait
```

打开 <http://localhost:18303>。页面预览带异常样例。选中阶段查看计算证据，选择可签发样例并执行批次，然后提交复核意见。

## 核验

```sh
docker compose exec -T app pytest -q
```

[输入字段](docs/DATA-DICTIONARY.md) · [阶段接口](docs/HTTP.md) · [操作步骤](docs/OPERATIONS.md) · [规则与测试](docs/DEPTH.md)
