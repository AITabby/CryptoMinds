#!/usr/bin/env python3
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from x402_pay import x402_pay


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "usage: managed_x402_payment.py <json_payload>"}))
        return

    # Accept either a JSON payload (single arg) or positional args (5 args)
    if len(sys.argv) == 2:
        try:
            payload = json.loads(sys.argv[1])
        except json.JSONDecodeError:
            print(json.dumps({"ok": False, "error": "无法解析 JSON 参数"}))
            return
        from_name = payload.get("from_name", "")
        to_name = payload.get("to_name", "")
        amount_bnb = float(payload.get("amount_bnb", payload.get("amount", 0)))
        order_id = payload.get("order_id", payload.get("service_id", ""))
        description = payload.get("description", "CryptoMinds x402 支付")
    else:
        from_name = sys.argv[1]
        to_name = sys.argv[2]
        amount_bnb = float(sys.argv[3])
        order_id = sys.argv[4]
        description = sys.argv[5]

    success, tx_hash, payment_info = x402_pay(
        from_name=from_name,
        to_name=to_name,
        amount_bnb=amount_bnb,
        order_id=order_id,
        description=description,
    )

    print(json.dumps({
        "ok": bool(success),
        "tx_hash": tx_hash,
        "payment_info": payment_info,
        "error": payment_info.get("error") if isinstance(payment_info, dict) else None,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
