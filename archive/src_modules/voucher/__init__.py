"""
Voucher 按量计费模块

cumulative 单调递增, 旧 voucher 自动失效
结算只认最新 cumulative
overcharged → 进入 escrow 争议窗口
"""

from .state import VoucherState, VoucherStateMachine, InvalidTransitionError
from .models import Voucher
from .verifier import VoucherChainVerifier, UsageRecord