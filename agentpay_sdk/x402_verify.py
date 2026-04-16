#!/usr/bin/env python3
"""
x402 支付验证 CLI — 供 web/server.js shell 调用

参数: <payment_header> <service_id> [services_json]
输出: JSON 到 stdout
"""
import sys
import os
import json

DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, DIR)

from x402_pay import verify_x402_payment

def main():
    if len(sys.argv) < 3:
        print(json.dumps({"valid": False, "error": "用法: x402_verify.py <payment_header> <service_id> [services_json]"}))
        sys.exit(1)

    payment_header = sys.argv[1]
    service_id = sys.argv[2]
    services_json = sys.argv[3] if len(sys.argv) > 3 else "[]"

    try:
        payment_info = json.loads(payment_header) if payment_header.startswith('{') else {"header": payment_header, "service_id": service_id}
    except json.JSONDecodeError:
        payment_info = {"header": payment_header, "service_id": service_id}

    valid, msg = verify_x402_payment(payment_info)

    result = {
        "valid": valid,
        "error": None if valid else msg,
        "tx_hash": payment_info.get("tx_hash"),
        "from_address": payment_info.get("from"),
        "to_address": payment_info.get("to"),
    }
    print(json.dumps(result))

if __name__ == "__main__":
    main()
