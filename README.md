# Python 性能分析技术分享

建议用 45–50 分钟。先用 5 分钟区分**请求延迟、CPU 热点和内存问题**，用 30–35 分钟演示七个案例，最后用 10 分钟做基准验证和答疑。每个 Demo 都可以独立运行，也可以按下表顺序串讲。

| 遇到的现象 | 首选工具 | 现场让观众读哪一项 |
| --- | --- | --- |
| 请求慢，CPU 却很空闲 | Pyinstrument | 墙钟时间调用树，耗时落在哪条 `await` 路径 |
| Python worker 已在运行，持续占用 CPU | py-spy | PID 的调用栈、实时热点、采样火焰图 |
| 批处理慢，怀疑某个函数调用太频繁 | cProfile | `ncalls`、`tottime`、`cumtime` 和调用者 |
| 已找到热点函数，想定位循环里最贵的一行 | line_profiler | `Hits`、`Per Hit`、`% Time` |
| NumPy 流水线慢，还出现数组复制和临时分配 | Scalene | 每行的 Python / native CPU、内存与复制指标 |
| 每完成一波任务，Python 内存基线就上涨 | tracemalloc | 同一阶段的快照差分 `size_diff`、`count_diff` |
| 批任务短时触及内存上限，结束后恢复 | Memray | 峰值时仍存活的已跟踪分配，以及 Python / native 栈 |
| 修复后需要验证提升或跟踪性能回归 | pyperf | 同名基准的跨进程多轮结果，比较均值和波动 |

## 环境准备

从项目根目录执行。建议使用 **64 位 CPython 3.12**。七个脚本用固定的合成数据，无需服务、数据下载或访问线上进程。Memray 官方支持 Linux 和 macOS。Windows 用户可在 WSL2 Ubuntu 中创建 Linux 虚拟环境，跑完整套 Demo，或者只把第 7 节放到 WSL2。Scalene 的 Windows 本机内存分析使用 2.x。安装后可用 `python -m pip list` 记录彩排版本。 [Memray 平台支持](https://github.com/bloomberg/memray#installation) · [Scalene 安装与平台说明](https://pypi.org/project/scalene/#installation)

### Linux / macOS / WSL2（Bash 或 Zsh）

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
mkdir -p out
```

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
New-Item -ItemType Directory -Force out
```

Ubuntu 若提示缺少 `ensurepip`，安装与 Python 版本匹配的 `python3-venv` 后再创建虚拟环境。同一份项目同时从 Windows 和 WSL 打开时，给两边的虚拟环境使用不同目录，例如 WSL 用 `.venv-linux`。下面各节的命令在激活环境后执行。报告写入 `out/`，Scalene 的独立 HTML 默认写到项目根目录。HTML 和 SVG 用浏览器打开。耗时、采样比例和内存数字会随硬件、调度、Python 与依赖版本变化。

## 1. Pyinstrument — 结算接口慢在哪里？

**适用场景**　Web 请求端到端延迟、串行远程调用、文件读写或数据库等待。演示场景是结算接口依次读取购物车、运费报价和优惠。三个读取彼此独立，用 `asyncio.sleep` 模拟耗时，无网络依赖。

**原理**　在进程内按间隔采样调用栈，并用墙钟时间给调用树计时。异步模式跟踪当前异步上下文，把暂停等待归到相应的 `await` 路径。短小函数可能采不到。并发子操作会重叠，不能把各操作的延迟直接相加作为请求总延迟。 [Pyinstrument 工作原理](https://pyinstrument.readthedocs.io/en/stable/how-it-works.html)

**演示步骤**

1. 跑串行版本，先投屏 `wall` 与 `cpu` 的差距，再打开 HTML，沿 `run_requests → checkout` 找三个等待分支。
2. 切到 `asyncio.gather` 版本。四次请求的 `total_cents` 都应为 `47200`。按模拟延时计算，每次请求约从 0.84 秒降到 0.36 秒。
3. 问观众「如果优惠查询依赖购物车返回的金额，哪些调用仍可并行？」引出依赖关系、超时和连接池容量。

```sh
python demos/async_checkout.py --html out/checkout-slow.html
python demos/async_checkout.py --mode fast --html out/checkout-fast.html
```

代码在当前协程中使用 `Profiler(async_mode="enabled")`，只统计请求循环。优化后，调用树可能把等待集中到 `gather` 或 `[await]`，此时可以结合总墙钟耗时讲并发收益。

## 2. py-spy — 正在运行的标签 worker 为什么吃 CPU？

**适用场景**　对已运行的 CPython worker 采样、抓卡顿当下的线程栈、定位反复出现的 CPU 热点。Demo 中的 worker 持续消费合成商品标签，逐条去空白、统一大小写、合并分隔符。

**原理**　独立进程读取目标 CPython 的内存并重建线程调用栈。可按 PID 读取，也可由 py-spy 启动目标。火焰图框宽表示该调用路径在所选样本中的占比，横轴没有时间顺序。默认采样会尝试排除空闲线程。附加权限取决于操作系统及容器配置。 [py-spy 用法、机制与权限](https://github.com/benfred/py-spy#usage)

**演示步骤**

1. 终端 A 运行 `python demos/live_worker.py --seconds 90`，复制第一行打印的 PID。
2. 终端 B 执行以下命令，将 `12345` 替换为实际 PID。先用 `dump` 看当下在执行什么，再用 `top` 看持续热点，按 Ctrl+C 退出 `top` 后执行 `record`。

   ```sh
   py-spy dump --pid 12345
   py-spy top --pid 12345
   py-spy record --pid 12345 --duration 10 -o out/tags-slow.svg
   ```

3. 在 SVG 中找 `summarize_batch → normalize_tag`。单次 `dump` 可能碰到模拟等待的 `sleep`，用 10 秒的样本确认频繁出现的栈。在 `top` 里观察 `normalize_tag` 的 `%Own` 和父函数 `summarize_batch` 的 `%Total`。
4. 修复版先用 `Counter` 统计原始标签，再按权重累加规范化后的标签。运行 `python demos/live_worker.py --mode fast --seconds 10`，对照相同观察时长的 slow 模式。两版每批都处理 60,000 个标签，观察 `tags_per_second`。

环境限制附加或 PID 已结束时，用启动模式录图。优化后的单次规范化很快，预期在采样火焰图中所占宽度大幅缩小。

```sh
py-spy record -o out/tags-slow.svg -- python demos/live_worker.py --seconds 10
py-spy record -o out/tags-fast.svg -- python demos/live_worker.py --seconds 10 --mode fast
```

## 3. cProfile — 订单计价的函数调用哪里多？

**适用场景**　可重跑的脚本、报表或任务，尤其想确认某个函数调用次数。Demo 按地区为 18 万笔订单计算税费与运费。在规则固定的一批订单中，每笔都重新解析同一份 JSON。

**原理**　标准库确定性分析器，在函数调用和返回事件上计数和计时。用 `cumtime` 找包含子调用的高成本路径，用 `tottime` 找函数本体成本，用 `ncalls` 区分高频小调用和低频大调用。累计时间在父子函数之间重叠。调用密集时追踪开销会改变绝对耗时。 [Python 3.12 profiler 文档](https://docs.python.org/3.12/library/profile.html)

**演示步骤**

```sh
python -m cProfile -o out/pricing-slow.prof demos/order_pricing.py
python -m cProfile -o out/pricing-fast.prof demos/order_pricing.py --mode fast
python -c "import pstats; pstats.Stats('out/pricing-slow.prof').strip_dirs().sort_stats('cumulative').print_stats(12).print_callers('read_rules')"
python -c "import pstats; pstats.Stats('out/pricing-fast.prof').strip_dirs().sort_stats('cumulative').print_stats(12).print_callers('read_rules')"
```

1. 先读 `price_batch_slow` 的累计时间，再对照 `read_rules` 和 `json.loads`，追到高频解析的调用路径。
2. 把规则读取提升到批次入口，`read_rules` 从 180,000 次降到 1 次，`price_order` 仍处理全部订单。
3. 核对 `total_cents` 相等。要对外报告加速幅度，用最后一节的无 profiler 基准。

## 4. line_profiler — 库存对账哪一行跑了上百万次？

**适用场景**　热点已缩小到一个函数，函数内同时有查找、运算、缺失处理等路径。Demo 将 2,500 条销售记录与 2,000 个商品 SKU 对账，汇总收入和缺失记录数。

**原理**　跟踪指定 Python 函数的行执行事件，把一次次执行的耗时归到源码行。看 `Hits` 和 `Per Hit` 能区分一行是反复执行还是单次昂贵。一行调用外部函数时，该行的计时可包含被调用操作，无法进一步拆出扩展内部的每一行。细粒度跟踪适合圈小范围。 [line_profiler 和 kernprof 文档](https://kernprof.readthedocs.io/en/stable/auto/kernprof.html)

**演示步骤**

```sh
python -m kernprof -l -v -o out/inventory-slow.lprof demos/inventory_join.py
python -m kernprof -l -v -o out/inventory-fast.lprof demos/inventory_join.py --mode fast
```

1. 已用 `@profile` 标记两个对账函数。让观众先预测加法与查找谁更贵，再看慢版 `if candidate == sku` 命中 2,515,011 次，`revenue += ...` 只命中 2,478 次。
2. 快版一次性建 `dict(catalog)`，每笔销售只调用一次 `prices.get(sku)`。展示一次建索引的成本、2,500 次查找，以及两版一致的 `revenue_cents` 和 `missing`。
3. 目录 SKU 在 Demo 中唯一。真实对账中若可能重复，先决定用首条、末条还是报错。课后可用 `python -m line_profiler out/inventory-slow.lprof` 重开报告。

## 5. Scalene — Python 解码和 NumPy 校准分别花在哪里？

**适用场景**　数据处理、机器学习预处理或混合 Python / C 扩展的热点。Demo 先用 Python 逐条解析传感器头部，再用 NumPy 校准浮点矩阵。每批额外复制输入并分配两个中间输出。

**原理**　通过采样并结合解释器与系统信息，把消耗归到源码行，区分 Python、原生代码及系统时间。内存模式通过分配采样归因，还可报告捕捉到的复制速率。CPU 占比、分配量与复制速率的单位和分母不同。复制列是否显著取决于拦截覆盖与样本，优先对照 CPU 分类、分配和源码。 [Scalene 项目说明](https://github.com/plasma-umass/scalene#scalene-overview) · [OSDI 论文](https://arxiv.org/abs/2212.07597)

**演示步骤**

```sh
python -m scalene run --memory -o out/scalene-slow.json demos/sensor_frames.py
python -m scalene view --cli out/scalene-slow.json
python -m scalene run --memory -o out/scalene-fast.json demos/sensor_frames.py --- --mode fast
python -m scalene view --cli out/scalene-fast.json
```

1. 在 `decode_gains` 的逐字符校验与数值累加处看 Python 栏，在 `frames.copy()`、`np.multiply` 和 `np.add` 附近看 native CPU 和内存。抽样较少时可在脚本参数区加 `--- --batches 128`，快版则在 `--mode fast` 后追加 `--batches 128`。
2. 快版复用独立的 `scratch`，用 ufunc 的 `out=` 写入预分配缓冲区，保留原输入。两版 `checksum` 应一致。观察数组分配下降、Python 解码仍在，以及它在总时间中的占比可能上升。
3. 图形演示用 `python -m scalene view --standalone out/scalene-slow.json`，打开命令打印的 HTML 路径。需要单独看 CPU 时，用下面的命令减少分配追踪对采样结果的影响。

```sh
python -m scalene run --cpu-only -o out/scalene-cpu.json demos/sensor_frames.py --- --batches 128
python -m scalene view --cli out/scalene-cpu.json
```

## 6. tracemalloc — 缓存为何每过一波就多 8 MiB？

**适用场景**　服务空闲后内存基线仍逐步抬升，怀疑缓存、队列或对象引用长期存活。Demo 每波生成 256 个 32 KiB 响应，以唯一请求 ID 放入字典。每波另有一个 4 MiB 的临时工作缓冲区。

**原理**　标准库记录已跟踪分配块的分配位置和调用栈。开启追踪后，在相同业务阶段用 `take_snapshot()`，再用 `compare_to(..., "lineno")` 看两时点间的净变化。刚分配又释放的块可能只出现在阶段峰值里。追踪范围以 Python 分配及主动接入的扩展为主。`get_traced_memory()` 衡量追踪到的内存块，进程 RSS 还受原生分配、分配器保留页等影响。 [tracemalloc 文档](https://docs.python.org/3.12/library/tracemalloc.html)

**演示步骤**

```sh
python demos/session_cache.py
python demos/session_cache.py --mode fast
```

1. 先预热 64 条，再在每波完成后拍快照。慢版三波各净增约 8 MiB，最显著的正差分指向 `payload = ...ljust(...)`。
2. 顺着代码找到 `cache[request_id] = payload`。分配行帮你定位这些字节从哪来，保留它们的引用需要回到缓存逻辑核对。
3. 快版设置 64 条容量，先进先出淘汰。解释缓存条目稳定后，`traced_current` 在约 2 MiB，而 `phase_peak` 仍在约 6 MiB。临时缓冲区在波次结束前已释放。

也可以把 `"lineno"` 改成 `"traceback"`，按完整分配栈区分同一行被不同路径调用的情况。

## 7. Memray — 临时 NumPy 数组把峰值推到多高？

**适用场景**　进程在批处理高峰接近容器内存上限，任务完成后内存看起来正常，或怀疑峰值来自 NumPy 等原生扩展。Demo 汇总 10 天的密集网格，慢版同时保留每天的数组、`np.stack` 创建的大数组和求和结果。

**原理**　跟踪原生分配器的分配与释放事件，关联 Python 调用栈。采集时开启 `--native` 会额外记录原生栈，符号是否可读取决于二进制及调试信息。默认火焰图的框宽是堆峰值时该路径仍存活的已跟踪分配字节。`stats` 还可看整个采集期间的累计分配量。若要观测更细的 Python 小对象分配，可另开 `run --trace-python-allocators`。 [Memray 采集](https://bloomberg.github.io/memray/run.html) · [火焰图](https://bloomberg.github.io/memray/flamegraph.html)

**演示步骤**（在 Linux / macOS / WSL2 环境执行）

```sh
python -c "import numpy"
python -m memray run --native -f -o out/peak-slow.bin demos/array_report.py
python -m memray stats out/peak-slow.bin
python -m memray flamegraph -f -o out/peak-slow.html out/peak-slow.bin

python -m memray run --native -f -o out/peak-fast.bin demos/array_report.py --mode fast
python -m memray stats out/peak-fast.bin
python -m memray flamegraph -f -o out/peak-fast.html out/peak-fast.bin
```

1. 首行先导入 NumPy，让两次采集从相同的字节码缓存状态开始。打开慢版报告搜索 `materialize_report`，寻找 `load_day` 和 `np.stack` 两条分配路径。单个输入约 4 MiB，10 个输入与堆叠副本各约 40 MiB，另有约 8 MiB 的求和输出。
2. 快版逐日读入并累加，用 `int64` 保持累计类型。两版均输出 `checksum=5283601920`。一次 WSL2 彩排中，Memray 报告的 `Peak memory usage` 从 98.75 MB 降到 23.19 MB。该环境的 CPython 缺少调试信息，部分原生帧没有文件名和行号。
3. 让观众比较 py-spy 与 Memray 的两张火焰图。前者框宽表示采样占比，后者框宽表示对应的内存字节。再问「如果 `np.stack` 在两次快照之间分配又释放，差分里会留下什么？」NumPy 的 CPU 数组数据分配可以接入 tracemalloc，快照差分仍取决于分配块在采样时点是否存活。 [NumPy 内存管理文档](https://numpy.org/doc/stable/reference/c-api/data_memory.html)

## 加餐 — 用 pyperf 验证 cProfile 指出的修复

pyperf 是基准工具，适合回答「改完快了多少」和「是否有性能回归」。它在独立 worker 中预热、重复测量，并可比较同名基准。两版均在 setup 中生成同样的 20,000 笔订单，把数据构造排除在被测区间外。 [pyperf CLI 文档](https://pyperf.readthedocs.io/en/stable/cli.html)

```sh
python -m pyperf timeit --fast --name pricing -s "from demos.order_pricing import make_orders, price_batch_slow; orders = make_orders(20000)" -o out/bench-slow.json "price_batch_slow(orders)"
python -m pyperf timeit --fast --name pricing -s "from demos.order_pricing import make_orders, price_batch_fast; orders = make_orders(20000)" -o out/bench-fast.json "price_batch_fast(orders)"
python -m pyperf compare_to out/bench-slow.json out/bench-fast.json --table
```

`--fast` 用于现场缩短等待。正式测量时去掉它，在同一台空闲机器上复跑，并查看 `python -m pyperf stats out/bench-slow.json` 中的分布。若要重复生成报告，给 `-o` 换新文件名。若业务关心真实服务的 P95 延迟，还要用生产近似负载做端到端验证。

## 收尾提问

- CPU 很空闲、接口还是慢，先问用户等了多久，再从 Pyinstrument 的等待路径开始。
- 已有 worker 持续吃 CPU，用 py-spy 拿第一个可信热点。能稳定复现后，再用 cProfile 或 line_profiler 追调用次数或具体源码行。
- 内存问题先画出时间曲线。基线持续涨，用 tracemalloc 做同阶段差分。阶段性尖峰或原生分配，用 Memray 看峰值的组成。
- 修复前后保留同一份输入并核对结果，再用无 profiler 的基准验证收益。
