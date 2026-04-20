#!/usr/bin/env python3
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from x402_pay import x402_pay


def main():
    if len(sys.argv) < 6:
      print(json.dumps({"ok": False, "error": "usage: managed_x402_payment.py <from_name> <to_name> <amount_bnb> <service_id> <description>"}))
      return

    from_name = sys.argv[1]
    to_name = sys.argv[2]
    amount_bnb = float(sys.argv[3])
    service_id = sys.argv[4]
    description = sys.argv[5]

    success, tx_hash, payment_info = x402_pay(
        from_name=from_name,
        to_name=to_name,
        amount_bnb=amount_bnb,
        service_id=service_id,
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
