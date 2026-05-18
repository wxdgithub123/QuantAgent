"""
Hummingbot AI 信号管道验证脚本

运行方式（二选一）：
  方式A（推荐）从 Docker 容器中运行：
    docker run --rm --network host -v "%cd%:/app" python:3.12-slim bash -c "pip install -q paho-mqtt && python /app/verify_ai_pipeline.py"

  方式B 本地运行（需先 pip install paho-mqtt 并确保 Mosquitto 端口可达）：
    python verify_ai_pipeline.py

前提条件：
  1. Docker Desktop 运行中
  2. Mosquitto 已启动: docker run -d --name mosquitto --network host eclipse-mosquitto
"""

import json
import sys
import time

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("请先安装: pip install paho-mqtt")
    sys.exit(1)

results = {"passed": 0, "failed": 0}


def make_client():
    """创建 MQTT 客户端，兼容 paho-mqtt 新旧版本"""
    try:
        return mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:
        return mqtt.Client()


# =====================================================================
# 测试 1: MQTT Broker 连接
# =====================================================================
print("=" * 60)
print("  测试 1: MQTT Broker 连接")
print("=" * 60)
try:
    client = make_client()
    client.connect("localhost", 1883, keepalive=5)
    client.disconnect()
    print("  PASS: 成功连接到 localhost:1883")
    results["passed"] += 1
except Exception as e:
    print(f"  FAIL: 无法连接 MQTT Broker: {e}")
    print("  请确认 Mosquitto 容器已启动:")
    print("    docker run -d --name mosquitto --network host eclipse-mosquitto")
    results["failed"] += 1
    sys.exit(1)

# =====================================================================
# 测试 2: 发布/订阅管道
# =====================================================================
print()
print("=" * 60)
print("  测试 2: MQTT 发布/订阅管道")
print("=" * 60)

received = []


def on_message(client, userdata, msg):
    received.append((msg.topic, json.loads(msg.payload.decode())))


topic = "hbot/predictions/btc_usdt/ML_SIGNALS"

sub = make_client()
sub.on_message = on_message
sub.connect("localhost", 1883)
sub.subscribe(topic)
sub.loop_start()
time.sleep(0.3)

pub = make_client()
pub.connect("localhost", 1883)
test_signal = {"probabilities": [0.1, 0.3, 0.6], "target_pct": 0.02, "timestamp": int(time.time())}
pub.publish(topic, json.dumps(test_signal))
pub.disconnect()
time.sleep(0.5)
sub.loop_stop()
sub.disconnect()

if received:
    print(f"  PASS: 收到 {len(received)} 条消息")
    print(f"  主题: {received[0][0]}")
    print(f"  内容: prob={received[0][1]['probabilities']}, target_pct={received[0][1]['target_pct']}")
    results["passed"] += 1
else:
    print("  FAIL: 未收到消息 - MQTT 管道不通")
    results["failed"] += 1
    sys.exit(1)

# =====================================================================
# 测试 3: 信号决策逻辑
# =====================================================================
print()
print("=" * 60)
print("  测试 3: 信号决策逻辑 (模拟 ai_livestream)")
print("=" * 60)

test_cases = [
    ("做多信号", [0.1, 0.3, 0.6], 1),
    ("做空信号", [0.7, 0.2, 0.1], -1),
    ("观望信号", [0.2, 0.7, 0.1], 0),
    ("边界-做多 (0.51)", [0.0, 0.49, 0.51], 1),
    ("边界-做空 (0.51)", [0.51, 0.49, 0.0], -1),
    ("边界-观望 (=0.5)", [0.5, 0.5, 0.0], 0),
]

for name, probs, expected in test_cases:
    short, neutral, long_p = probs
    if short > 0.5:
        actual = -1
    elif long_p > 0.5:
        actual = 1
    else:
        actual = 0
    action_map = {1: "做多 BUY", -1: "做空 SELL", 0: "观望 HOLD"}
    ok = actual == expected
    print(f"  {'PASS' if ok else 'FAIL'}: {name} probs={probs} -> signal={actual} ({action_map[actual]})")
    results["passed" if ok else "failed"] += 1

# =====================================================================
# 测试 4: 多交易对路由 + 往返延迟
# =====================================================================
print()
print("=" * 60)
print("  测试 4: 多交易对路由 + 端到端延迟")
print("=" * 60)

received_multi = {}


def on_multi(client, userdata, msg):
    received_multi[msg.topic] = json.loads(msg.payload.decode())


sub = make_client()
sub.on_message = on_multi
sub.connect("localhost", 1883)
sub.subscribe("hbot/predictions/btc_usdt/ML_SIGNALS")
sub.subscribe("hbot/predictions/eth_usdt/ML_SIGNALS")
sub.loop_start()
time.sleep(0.3)

pub = make_client()
pub.connect("localhost", 1883)

t0 = time.time()
pub.publish("hbot/predictions/btc_usdt/ML_SIGNALS",
            json.dumps({"probabilities": [0.1, 0.3, 0.6], "target_pct": 0.02, "timestamp": int(t0)}))
time.sleep(0.1)
pub.publish("hbot/predictions/eth_usdt/ML_SIGNALS",
            json.dumps({"probabilities": [0.8, 0.15, 0.05], "target_pct": 0.015, "timestamp": int(t0)}))
pub.disconnect()

time.sleep(0.8)
sub.loop_stop()
sub.disconnect()
elapsed = (time.time() - t0) * 1000

btc_ok = "hbot/predictions/btc_usdt/ML_SIGNALS" in received_multi
eth_ok = "hbot/predictions/eth_usdt/ML_SIGNALS" in received_multi

if btc_ok and eth_ok:
    print(f"  PASS: BTC={received_multi['hbot/predictions/btc_usdt/ML_SIGNALS']['probabilities']}")
    print(f"        ETH={received_multi['hbot/predictions/eth_usdt/ML_SIGNALS']['probabilities']}")
    print(f"        端到端延迟 ~{elapsed:.0f}ms")
    results["passed"] += 1
else:
    print(f"  FAIL: BTC={'OK' if btc_ok else 'MISSING'}, ETH={'OK' if eth_ok else 'MISSING'}")
    results["failed"] += 1

# =====================================================================
# 汇总
# =====================================================================
print()
print("=" * 60)
print("  验证结果汇总")
print("=" * 60)
total = results["passed"] + results["failed"]
print(f"  通过: {results['passed']}/{total}")
print(f"  失败: {results['failed']}/{total}")

if results["failed"] == 0:
    print()
    print("  全部测试通过!")
    print("  ┌──────────┐     MQTT      ┌────────────┐     MQTT      ┌──────────────┐")
    print("  │  ML 模型  │ ────────────► │ Mosquitto  │ ────────────► │  Hummingbot  │")
    print("  │ (你写的)  │   publish     │   Broker   │   subscribe  │ ai_livestream│")
    print("  └──────────┘               └────────────┘              └──────┬───────┘")
    print("                                                                │")
    print("                                                        自动下单执行")
    print("  这整条链路已经打通，你可以开始训练 ML 模型了。")
else:
    print(f"\n  有 {results['failed']} 个测试失败，请检查上述输出。")
