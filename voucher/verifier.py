"""
Voucher 链完整性验证器

检查:
- units_used 单调递增 (不可回退)
- previous_cumulative 形成链, 可验证完整性
- overcharged → 进入 escrow 争议
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional


@dataclass
class UsageRecord:
    voucher_id: str
    units_consumed: int          # 本次消费的 units
    cumulative_used: int         # 紧计已用 (单调递增)
    previous_cumulative: int     # 上一次的 cumulative (形成链)
    timestamp: int
    signature: str = ""


class VoucherChainVerifier:
    """验证 Voucher 使用链的完整性"""

    def verify_chain(self, records: List[UsageRecord]) -> Dict:
        """验证整个使用记录链"""
        if not records:
            return {"valid": True, "error": ""}

        errors = []

        # 1. 检查 cumulative 单调递增
        prev_cum = 0
        for i, r in enumerate(records):
            if r.cumulative_used <= prev_cum and i > 0:
                errors.append(f"cumulative 回退 at record {i}: {r.cumulative_used} <= {prev_cum}")
            if r.cumulative_used < r.units_consumed:
                errors.append(f"cumulative < consumed at record {i}: {r.cumulative_used} < {r.units_consumed}")
            prev_cum = r.cumulative_used

        # 2. 检查 previous_cumulative 链断裂
        for i, r in enumerate(records):
            if i > 0 and r.previous_cumulative != records[i - 1].cumulative_used:
                errors.append(
                    f"链断裂 at record {i}: previous_cumulative={r.previous_cumulative} "
                    f"!= prev record cumulative={records[i - 1].cumulative_used}"
                )

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "total_units_used": records[-1].cumulative_used if records else 0,
        }

    def verify_no_overcharge(
        self,
        records: List[UsageRecord],
        total_units: int,
    ) -> Dict:
        """检查是否超额使用"""
        if not records:
            return {"overcharged": False, "units_used": 0, "total_units": total_units}

        total_used = records[-1].cumulative_used
        overcharged = total_used > total_units

        return {
            "overcharged": overcharged,
            "units_used": total_used,
            "total_units": total_units,
            "excess": total_used - total_units if overcharged else 0,
        }