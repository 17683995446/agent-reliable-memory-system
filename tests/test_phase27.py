#!/usr/bin/env python3
"""
验证第27阶段 - 消息系统模块（阶段336-340）

测试覆盖：
- 336: MessageQueue - FIFO/FILO/Priority/Delay队列
- 337: EventBus - 发布订阅、主题路由、通配符
- 338: MessageBroker - 路由引擎、负载均衡、确认机制
- 339: DeadLetterQueue - 死信收集、重试策略、归档
- 340: StreamProcessor - 窗口聚合、背压控制、流拓扑
"""

import sys
import os
import time
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

passed = 0
failed = 0
errors = []


def test(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✓ {name}")
    else:
        failed += 1
        msg = f"  ✗ {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)
        errors.append((name, detail))


# ============================================================
# 阶段336: MessageQueue
# ============================================================
print("\n=== 阶段336: MessageQueue ===")

from messaging.message_queue import (
    Message, MessageStatus, QueueType,
    FIFOQueue, FILOQueue, PriorityQueue, DelayQueue, QueueManager
)

# 336-1: FIFO基本操作
q = FIFOQueue("test_fifo", max_size=10)
m1 = Message(payload="a", topic="t1")
m2 = Message(payload="b", topic="t1")
test("336-1 FIFO put/get", q.put(m1) and q.put(m2))
r1 = q.get()
r2 = q.get()
test("336-1 FIFO order", r1.payload == "a" and r2.payload == "b",
     f"got {r1.payload}, {r2.payload}")

# 336-2: FILO基本操作
s = FILOQueue("test_filo")
s.put(Message(payload="x"))
s.put(Message(payload="y"))
test("336-2 FILO order", s.get().payload == "y" and s.get().payload == "x")

# 336-3: PriorityQueue
pq = PriorityQueue("test_pq")
pq.put(Message(payload="low", priority=100))
pq.put(Message(payload="high", priority=1))
pq.put(Message(payload="mid", priority=50))
test("336-3 Priority order", pq.get().payload == "high")

# 336-4: DelayQueue
dq = DelayQueue("test_delay")
dq.put(Message(payload="delayed"), delay_seconds=0.1)
test("336-4 DelayQueue empty before delay", dq.get() is None)
time.sleep(0.15)
msg = dq.get()
test("336-4 DelayQueue delivers after delay", msg is not None and msg.payload == "delayed")

# 336-5: 队列容量限制
small_q = FIFOQueue("small", max_size=2)
test("336-5 Queue accepts within capacity", small_q.put(Message(payload="1")) and small_q.put(Message(payload="2")))
test("336-5 Queue rejects over capacity", not small_q.put(Message(payload="3")))

# 336-6: QueueManager
qm = QueueManager()
qm.create_queue("q1", QueueType.FIFO)
qm.create_queue("q2", QueueType.PRIORITY)
test("336-6 QueueManager creates queues", qm.get_queue("q1") is not None and qm.get_queue("q2") is not None)
test("336-6 QueueManager stats", qm.get_stats()["queues"] == 2)

# 336-7: Message属性
msg = Message(payload="test", topic="order.created", headers={"type": "order"})
test("336-7 Message auto-id", len(msg.id) > 0)
test("336-7 Message created_at set", msg.created_at > 0)
test("336-7 Message not expired by default", not msg.is_expired)


# ============================================================
# 阶段337: EventBus
# ============================================================
print("\n=== 阶段337: EventBus ===")

from messaging.event_bus import (
    DeliveryMode, EventBus, PublishResult
)

# 337-1: 基本发布订阅
bus = EventBus()
received = []
bus.subscribe("order.created", lambda m: received.append(m.payload))
result = bus.publish("order.created", payload={"id": 1})
test("337-1 Basic pub/sub", len(received) == 1 and received[0] == {"id": 1})
test("337-1 PublishResult delivered", result.delivered_count == 1)

# 337-2: 通配符匹配 *
received2 = []
bus.subscribe("order.*", lambda m: received2.append(m.topic))
bus.publish("order.created", payload="test")
bus.publish("order.updated", payload="test")
test("337-2 Wildcard * matches", len(received2) == 2)

# 337-3: 通配符匹配 #
received3 = []
bus.subscribe("sys.#", lambda m: received3.append(m.topic))
bus.publish("sys.cpu.load", payload="")
bus.publish("sys.mem.usage", payload="")
bus.publish("sys.disk.io.read", payload="")
test("337-3 Wildcard # matches all levels", len(received3) == 3)

# 337-4: 优先级排序
priority_log = []
bus2 = EventBus()
bus2.subscribe("test", lambda m: priority_log.append("low"), priority=200)
bus2.subscribe("test", lambda m: priority_log.append("high"), priority=10)
bus2.subscribe("test", lambda m: priority_log.append("mid"), priority=100)
bus2.publish("test")
test("337-4 Priority order", priority_log == ["high", "mid", "low"],
     f"got {priority_log}")

# 337-5: 头部过滤
filtered = []
bus3 = EventBus()
bus3.subscribe("data", lambda m: filtered.append(m.payload),
               filter_headers={"version": "2"})
bus3.publish("data", payload="v1", headers={"version": "1"})
bus3.publish("data", payload="v2", headers={"version": "2"})
test("337-5 Header filter", filtered == ["v2"], f"got {filtered}")

# 337-6: 拦截器
bus4 = EventBus()
bus4.add_interceptor(lambda m: None)  # 丢弃所有消息
intercepted = []
bus4.subscribe("test", lambda m: intercepted.append(1))
bus4.publish("test", payload="should_not_arrive")
test("337-6 Interceptor drops message", len(intercepted) == 0)

# 337-7: 取消订阅
bus5 = EventBus()
sid = bus5.subscribe("temp", lambda m: None)
test("337-7 Unsubscribe", bus5.unsubscribe(sid))

# 337-8: 统计
bus6 = EventBus()
bus6.subscribe("a", lambda m: None)
bus6.subscribe("b", lambda m: None)
bus6.publish("a")
bus6.publish("b")
stats = bus6.get_stats()
test("337-8 Stats", stats["total_published"] == 2 and stats["total_subscriptions"] == 2)


# ============================================================
# 阶段338: MessageBroker
# ============================================================
print("\n=== 阶段338: MessageBroker ===")

from messaging.message_broker import (
    AckStatus, RouteAction, LoadBalanceStrategy,
    RouteRule, RouteEngine, LoadBalancer, AckManager,
    ConsumerGroup, MessageBroker
)

# 338-1: 路由引擎 - 主题匹配
engine = RouteEngine()
engine.add_rule(RouteRule(
    name="order_rule",
    match_topic="order.*",
    action=RouteAction.QUEUE,
    target="order_queue",
    priority=10,
))
engine.set_default(RouteAction.QUEUE, "default_queue")

msg_order = Message(topic="order.created", payload="order1")
action, target, delay = engine.route(msg_order)
test("338-1 Route engine topic match", action == RouteAction.QUEUE and target == "order_queue")

msg_other = Message(topic="user.login", payload="user1")
action2, target2, _ = engine.route(msg_other)
test("338-1 Route engine default", action2 == RouteAction.QUEUE and target2 == "default_queue")

# 338-2: 路由引擎 - 头部匹配
engine2 = RouteEngine()
engine2.add_rule(RouteRule(
    name="vip_rule",
    match_topic="order.*",
    match_headers={"priority": "high"},
    action=RouteAction.QUEUE,
    target="vip_queue",
    priority=10,
))
engine2.add_rule(RouteRule(
    name="normal_rule",
    match_topic="order.*",
    action=RouteAction.QUEUE,
    target="normal_queue",
    priority=50,
))

msg_vip = Message(topic="order.created", headers={"priority": "high"})
_, tgt_vip, _ = engine2.route(msg_vip)
test("338-2 Header-based routing", tgt_vip == "vip_queue")

msg_normal = Message(topic="order.created", headers={"priority": "low"})
_, tgt_normal, _ = engine2.route(msg_normal)
test("338-2 Header fallback", tgt_normal == "normal_queue")

# 338-3: 负载均衡 - 轮询
lb = LoadBalancer(LoadBalanceStrategy.ROUND_ROBIN)
lb.register("c1")
lb.register("c2")
lb.register("c3")
results = [lb.select() for _ in range(6)]
test("338-3 Round robin", results == ["c1", "c2", "c3", "c1", "c2", "c3"],
     f"got {results}")

# 338-4: 负载均衡 - 加权
lb2 = LoadBalancer(LoadBalanceStrategy.WEIGHTED)
lb2.register("heavy", weight=10)
lb2.register("light", weight=1)
# 运行多次，heavy应该被选中更多
counts = {}
for _ in range(100):
    sel = lb2.select()
    counts[sel] = counts.get(sel, 0) + 1
test("338-4 Weighted balance", counts.get("heavy", 0) > counts.get("light", 0),
     f"heavy={counts.get('heavy',0)}, light={counts.get('light',0)}")

# 338-5: 负载均衡 - 一致性哈希
lb3 = LoadBalancer(LoadBalanceStrategy.CONSISTENT_HASH)
lb3.register("node_a")
lb3.register("node_b")
lb3.register("node_c")
# 相同key应该路由到相同节点
r1 = lb3.select("user_123")
r2 = lb3.select("user_123")
r3 = lb3.select("user_456")
test("338-5 Consistent hash same key", r1 == r2)
test("338-5 Consistent hash different key", r1 is not None and r3 is not None)

# 338-6: AckManager
ack_mgr = AckManager(timeout_seconds=1.0)
msg_ack = Message(payload="ack_test")
ack_mgr.track(msg_ack, "consumer_1", max_retries=3)
test("338-6 Track message", ack_mgr.in_flight_count == 1)
test("338-6 ACK message", ack_mgr.ack(msg_ack.id))
test("338-6 ACK removes from flight", ack_mgr.in_flight_count == 0)

# 338-7: NACK
msg_nack = Message(payload="nack_test")
ack_mgr.track(msg_nack, "consumer_2")
nacked = ack_mgr.nack(msg_nack.id)
test("338-7 NACK returns message", nacked is not None and nacked.payload == "nack_test")

# 338-8: REQUEUE
msg_rq = Message(payload="requeue_test")
ack_mgr.track(msg_rq, "consumer_3", max_retries=3)
requeued = ack_mgr.requeue(msg_rq.id)
test("338-8 Requeue returns message", requeued is not None)
test("338-8 Requeue increments retry", ack_mgr.get_in_flight()[0]["retry_count"] == 1)

# 338-9: 消费者组
group = ConsumerGroup("test_group", LoadBalanceStrategy.ROUND_ROBIN)
c1_id = group.register(lambda m: AckStatus.ACK, weight=1)
c2_id = group.register(lambda m: AckStatus.ACK, weight=1)
test("338-9 Consumer group size", group.size == 2)

msg_cg = Message(payload="group_test")
cid = group.deliver(msg_cg)
test("338-9 Group deliver", cid is not None)
test("338-9 Group unregister", group.unregister(c1_id) and group.size == 1)

# 338-10: MessageBroker集成
broker = MessageBroker()
broker.create_queue("orders", QueueType.FIFO)
broker.add_route(RouteRule(
    name="broker_order",
    match_topic="order.*",
    action=RouteAction.QUEUE,
    target="orders",
    priority=10,
))
broker.set_default_route(RouteAction.QUEUE, "default")

mid = broker.send("order.created", payload={"item": "book"})
test("338-10 Broker send routes to queue", mid is not None and len(mid) > 0)

received_msg = broker.receive("orders")
test("338-10 Broker receive", received_msg is not None and received_msg.payload == {"item": "book"})

broker_stats = broker.get_stats()
test("338-10 Broker stats", broker_stats["routed"] >= 1)


# ============================================================
# 阶段339: DeadLetterQueue
# ============================================================
print("\n=== 阶段339: DeadLetterQueue ===")

from messaging.dead_letter_queue import (
    RetryStrategy, DeadLetterReason, ArchivePolicy,
    RetryConfig, DeadLetterQueue, RetryPolicyManager
)

# 339-1: 死信入队
dlq = DeadLetterQueue()
msg_dl = Message(payload="failed_order", topic="order.process")
dlq_id = dlq.enqueue(msg_dl, DeadLetterReason.MAX_RETRIES,
                      original_queue="orders", error_detail="timeout")
test("339-1 DLQ enqueue", dlq_id is not None and len(dlq_id) > 0)

entry = dlq.get(dlq_id)
test("339-1 DLQ get entry", entry is not None and entry.reason == DeadLetterReason.MAX_RETRIES)

# 339-2: 按原因查询
dlq.enqueue(Message(payload="e1"), DeadLetterReason.EXPIRED)
dlq.enqueue(Message(payload="e2"), DeadLetterReason.EXPIRED)
by_reason = dlq.get_by_reason(DeadLetterReason.EXPIRED)
test("339-2 Query by reason", len(by_reason) >= 2)

# 339-3: 按队列查询
dlq.enqueue(Message(payload="e3"), DeadLetterReason.ERROR, original_queue="payments")
by_queue = dlq.get_by_queue("payments")
test("339-3 Query by queue", len(by_queue) >= 1)

# 339-4: 重试策略 - 固定间隔
fixed_config = RetryConfig(strategy=RetryStrategy.FIXED, initial_delay=2.0)
test("339-4 Fixed delay", fixed_config.get_delay(0) == 2.0)
test("339-4 Fixed delay same for all", fixed_config.get_delay(5) == 2.0)

# 339-5: 重试策略 - 指数退避
exp_config = RetryConfig(
    strategy=RetryStrategy.EXPONENTIAL,
    initial_delay=1.0,
    multiplier=2.0,
    max_delay=60.0,
)
d0 = exp_config.get_delay(0)
d1 = exp_config.get_delay(1)
d2 = exp_config.get_delay(2)
test("339-5 Exponential backoff", d0 == 1.0 and d1 == 2.0 and d2 == 4.0,
     f"got {d0}, {d1}, {d2}")

# 339-6: 重试策略 - 自定义
custom_config = RetryConfig(
    strategy=RetryStrategy.CUSTOM,
    custom_delays=[1.0, 3.0, 5.0, 10.0],
)
test("339-6 Custom delay sequence", custom_config.get_delay(0) == 1.0)
test("339-6 Custom delay index 2", custom_config.get_delay(2) == 5.0)
test("339-6 Custom delay overflow", custom_config.get_delay(10) == 10.0)

# 339-7: 重试消息
dlq2 = DeadLetterQueue()
dlq2.set_retry_policy("orders", RetryConfig(max_retries=3))
msg_retry = Message(payload="retry_me")
dlq2.enqueue(msg_retry, DeadLetterReason.MAX_RETRIES, original_queue="orders")
retried = dlq2.retry(msg_retry.id)
test("339-7 Retry message", retried is not None and retried.payload == "retry_me")

# 339-8: 解决死信
dlq2.resolve(msg_retry.id)
test("339-8 Resolve entry", dlq2.get(msg_retry.id).resolved)

# 339-9: 移除死信
msg_rm = Message(payload="remove_me")
dlq2.enqueue(msg_rm, DeadLetterReason.ERROR)
removed = dlq2.remove(msg_rm.id)
test("339-9 Remove entry", removed is not None)
test("339-9 Entry gone", dlq2.get(msg_rm.id) is None)

# 339-10: RetryPolicyManager
rpm = RetryPolicyManager()
rpm.set_policy("orders", RetryConfig(strategy=RetryStrategy.FIXED, initial_delay=5.0))
policy = rpm.get_policy("orders")
test("339-10 Policy manager get", policy.strategy == RetryStrategy.FIXED)
test("339-10 Policy manager compute delay", rpm.compute_delay("orders", 0) == 5.0)

# 339-11: DLQ统计
stats = dlq.get_stats()
test("339-11 DLQ stats", stats["total_enqueued"] >= 4)

# 339-12: 归档
dlq3 = DeadLetterQueue(max_size=10)
for i in range(8):
    dlq3.enqueue(Message(payload=f"msg_{i}"), DeadLetterReason.ERROR)
dlq3.set_archive_policy(ArchivePolicy.SIZE, size_threshold=5)
archived_count = dlq3.archive()
test("339-12 Archive triggers", archived_count >= 1)
test("339-12 Archives list", len(dlq3.get_archives()) >= 1)


# ============================================================
# 阶段340: StreamProcessor
# ============================================================
print("\n=== 阶段340: StreamProcessor ===")

from messaging.stream_processor import (
    WindowType, BackPressureStrategy, ProcessorState,
    WindowConfig, BackPressureConfig,
    StreamRecord, WindowResult,
    WindowManager, BackPressureController,
    StreamProcessor, StreamTopology
)

# 340-1: 计数窗口
wc = WindowConfig(window_type=WindowType.COUNT, count=3)
wm = WindowManager(wc, aggregate_fn=lambda records: sum(r.value for r in records))

results = []
for i in range(5):
    r = StreamRecord(key="counter", value=i)
    results.extend(wm.add(r))

test("340-1 Count window triggers", len(results) == 1)
test("340-1 Count window result", results[0].count == 3 and results[0].result == 0 + 1 + 2,
     f"got count={results[0].count}, result={results[0].result}")

# 340-2: 窗口flush
remaining = wm.flush()
test("340-2 Flush remaining", len(remaining) == 1 and remaining[0].count == 2)

# 340-3: 会话窗口
session_config = WindowConfig(window_type=WindowType.SESSION, gap_ms=200)
session_wm = WindowManager(session_config, aggregate_fn=lambda r: len(r))

# 同一会话的两条消息（间隔小于200ms）
r1 = StreamRecord(key="session", value=1)
session_wm.add(r1)
time.sleep(0.05)  # 50ms间隔，在200ms gap内
r2 = StreamRecord(key="session", value=2)
session_wm.add(r2)

# 等待超过gap间隔
time.sleep(0.25)  # 250ms > 200ms gap
r3 = StreamRecord(key="session", value=3)
session_results = session_wm.add(r3)

test("340-3 Session window triggers", len(session_results) == 1)
if session_results:
    test("340-3 Session window count", session_results[0].count == 2)
else:
    test("340-3 Session window count", False, "no results returned")

# 340-4: 背压控制器 - 正常情况
bp = BackPressureController(BackPressureConfig(
    strategy=BackPressureStrategy.BUFFER,
    max_buffer_size=100,
))
test("340-4 BP accepts normal", bp.submit(StreamRecord(value="ok")))
test("340-4 BP buffer size", bp.buffer_size == 1)

# 340-5: 背压控制器 - DROP策略
bp_drop = BackPressureController(BackPressureConfig(
    strategy=BackPressureStrategy.DROP,
    max_buffer_size=5,
    high_watermark=0.6,
))
for i in range(5):
    bp_drop.submit(StreamRecord(value=i))
# 超过高水位
test("340-5 BP under pressure", bp_drop.is_under_pressure)
dropped = not bp_drop.submit(StreamRecord(value="overflow"))
test("340-5 BP drops when full", dropped)

# 340-6: 背压控制器 - 速率限制
bp_rate = BackPressureController(BackPressureConfig(
    strategy=BackPressureStrategy.BUFFER,
    max_buffer_size=1000,
    max_rate=10.0,  # 每秒10个
))
accepted = sum(1 for _ in range(20) if bp_rate.submit(StreamRecord(value=i)))
test("340-6 Rate limiting", accepted <= 15, f"accepted {accepted}")  # 应该被限制

# 340-7: StreamProcessor基本处理
sp = StreamProcessor("test_processor")
sp.start()

output = []
sp.add_sink(lambda r: output.append(r.value))
sp.process(StreamRecord(key="k1", value="hello"))
sp.process(StreamRecord(key="k1", value="world"))
test("340-7 Processor output", output == ["hello", "world"],
     f"got {output}")

# 340-8: Transform管道
sp2 = StreamProcessor("transform_test")
sp2.start()
sp2.add_transform(lambda r: StreamRecord(key=r.key, value=r.value.upper()) if isinstance(r.value, str) else r)
sp2.add_transform(lambda r: StreamRecord(key=r.key, value=r.value + "!"))

transformed = []
sp2.add_sink(lambda r: transformed.append(r.value))
sp2.process(StreamRecord(key="k", value="hi"))
test("340-8 Transform chain", transformed == ["HI!"],
     f"got {transformed}")

# 340-9: Transform过滤（返回None）
sp3 = StreamProcessor("filter_test")
sp3.start()
sp3.add_transform(lambda r: None)  # 全部过滤
filtered_out = []
sp3.add_sink(lambda r: filtered_out.append(r.value))
sp3.process(StreamRecord(value="should_not_pass"))
test("340-9 Transform filter", filtered_out == [])

# 340-10: 状态管理
sp4 = StreamProcessor("state_test")
sp4.start()
sp4.set_state("counter", 0)
sp4.set_state("last_key", "")

def stateful_transform(r):
    count = sp4.get_state("counter", 0) + 1
    sp4.set_state("counter", count)
    sp4.set_state("last_key", r.key)
    return r

sp4.add_transform(stateful_transform)
sp4.process(StreamRecord(key="a"))
sp4.process(StreamRecord(key="b"))
test("340-10 State counter", sp4.get_state("counter") == 2)
test("340-10 State last_key", sp4.get_state("last_key") == "b")

# 340-11: 生命周期
sp5 = StreamProcessor("lifecycle")
test("340-11 Initial state", sp5.status == ProcessorState.CREATED)
sp5.start()
test("340-11 Running", sp5.status == ProcessorState.RUNNING)
sp5.pause()
test("340-11 Paused", sp5.status == ProcessorState.PAUSED)
sp5.resume()
test("340-11 Resumed", sp5.status == ProcessorState.RUNNING)
sp5.stop()
test("340-11 Stopped", sp5.status == ProcessorState.STOPPED)

# 340-12: StreamTopology
topo = StreamTopology("test_topo")

p1 = StreamProcessor("source")
p1.start()
p2 = StreamProcessor("transform")
p2.start()
p3 = StreamProcessor("sink")
p3.start()

sink_output = []
p3.add_sink(lambda r: sink_output.append(r.value))

topo.add_processor("source", p1)
topo.add_processor("transform", p2)
topo.add_processor("sink", p3)
topo.connect("source", "transform")
topo.connect("transform", "sink")

topo.submit("source", StreamRecord(key="flow", value="data"))
test("340-12 Topology flow", sink_output == ["data"],
     f"got {sink_output}")

topo_stats = topo.get_stats()
test("340-12 Topology stats", topo_stats["processors"] == 3 and topo_stats["edges"] == 2)

# 340-13: Processor统计
sp_stats = sp.get_stats()
test("340-13 Processor stats", sp_stats["processed"] == 2 and sp_stats["status"] == "running")

# 340-14: 错误处理
error_caught = []
sp_err = StreamProcessor("error_test")
sp_err.start()
sp_err.set_error_handler(lambda e, r: error_caught.append(str(e)))
sp_err.add_transform(lambda r: 1 / 0)  # 故意出错
sp_err.process(StreamRecord(value="trigger"))
test("340-14 Error handler called", len(error_caught) >= 1)
test("340-14 Error counted", sp_err.get_stats()["errors"] >= 1)


# ============================================================
# 汇总
# ============================================================
print(f"\n{'='*50}")
print(f"第27阶段验证完成: ✓ {passed} 通过, ✗ {failed} 失败")
print(f"{'='*50}")

if errors:
    print("\n失败详情:")
    for name, detail in errors:
        print(f"  - {name}: {detail}")

sys.exit(0 if failed == 0 else 1)
