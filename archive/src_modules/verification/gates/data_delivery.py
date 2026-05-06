"""
数据交付验证门

验证卖家是否正确交付数据（文件、分析结果、翻译等）。
"""

import hashlib
import time
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from ..base import VerificationGate, VerificationResult, TaskInput, TaskOutput


class DataDeliveryGate(VerificationGate):
    """
    数据交付验证门

    gate_id: data_delivery
    task_type: data_delivery

    验证逻辑：
    1. 检查数据是否存在（通过 hash 或 URL）
    2. 检查数据格式是否符合预期
    3. 检查数据大小是否在合理范围
    """

    gate_id = "data_delivery"
    task_type = "data_delivery"
    version = "1.0.0"
    description = "验证数据是否正确交付"
    supported_chains = []  # 数据交付不依赖特定链

    def __init__(self, min_size_bytes: int = 0, max_size_bytes: int = 100 * 1024 * 1024):
        """
        Args:
            min_size_bytes: 最小数据大小（字节）
            max_size_bytes: 最大数据大小（字节）
        """
        self.min_size_bytes = min_size_bytes
        self.max_size_bytes = max_size_bytes

    # ── 输入/输出验证 ─────────────────────────────────

    def validate_input(self, input: TaskInput) -> Tuple[bool, str]:
        """验证输入格式"""
        if not input.buyer_wallet:
            return False, "缺少买家钱包地址"

        if input.task_type != "data_delivery":
            return False, f"任务类型不匹配: {input.task_type}"

        # 检查参数
        params = input.params
        if not params.get("data_type"):
            return False, "缺少数据类型参数"

        return True, "输入验证通过"

    def validate_output(self, output: TaskOutput) -> Tuple[bool, str]:
        """验证输出格式"""
        # 数据交付需要以下之一：
        # 1. file_hash + data（数据内容）
        # 2. file_hash + URL（数据链接）
        # 3. data（直接数据）

        if not output.file_hash and not output.data:
            return False, "缺少数据或文件哈希"

        return True, "输出验证通过"

    # ── 核心验证逻辑 ───────────────────────────────────

    def verify(self, input: TaskInput, output: TaskOutput) -> VerificationResult:
        """
        验证数据交付

        检查：
        1. 数据是否存在
        2. 数据哈希是否匹配
        3. 数据格式是否符合预期
        """

        # 1. 验证输入输出格式
        valid, msg = self.validate_input(input)
        if not valid:
            return VerificationResult(
                success=False,
                gate_id=self.gate_id,
                task_type=self.task_type,
                error=msg,
            )

        valid, msg = self.validate_output(output)
        if not valid:
            return VerificationResult(
                success=False,
                gate_id=self.gate_id,
                task_type=self.task_type,
                error=msg,
            )

        # 2. 验证数据
        data_type = input.params.get("data_type", "raw")
        expected_format = input.params.get("expected_format", None)
        expected_hash = input.params.get("expected_hash", None)

        evidence = {
            "data_type": data_type,
            "file_hash": output.file_hash,
            "data_size": len(output.data) if output.data else 0,
        }

        # 如果提供了数据内容，验证哈希
        if output.data:
            actual_hash = hashlib.sha256(output.data.encode() if isinstance(output.data, str) else output.data).hexdigest()

            if expected_hash and actual_hash != expected_hash:
                return VerificationResult(
                    success=False,
                    gate_id=self.gate_id,
                    task_type=self.task_type,
                    error=f"数据哈希不匹配: 期望 {expected_hash}, 实际 {actual_hash}",
                    evidence=evidence,
                )

            evidence["actual_hash"] = actual_hash

            # 验证数据大小
            data_size = len(output.data)
            if data_size < self.min_size_bytes:
                return VerificationResult(
                    success=False,
                    gate_id=self.gate_id,
                    task_type=self.task_type,
                    error=f"数据太小: {data_size} < {self.min_size_bytes}",
                    evidence=evidence,
                )

            if data_size > self.max_size_bytes:
                return VerificationResult(
                    success=False,
                    gate_id=self.gate_id,
                    task_type=self.task_type,
                    error=f"数据太大: {data_size} > {self.max_size_bytes}",
                    evidence=evidence,
                )

            # 验证数据格式
            if expected_format:
                format_valid, format_msg = self._validate_format(output.data, expected_format)
                if not format_valid:
                    return VerificationResult(
                        success=False,
                        gate_id=self.gate_id,
                        task_type=self.task_type,
                        error=format_msg,
                        evidence=evidence,
                    )

        # 3. 成功
        score = 1.0
        if output.extra.get("quality_score"):
            try:
                score = float(output.extra.get("quality_score"))
            except:
                pass

        return VerificationResult(
            success=True,
            score=score,
            gate_id=self.gate_id,
            task_type=self.task_type,
            evidence=evidence,
        )

    def _validate_format(self, data: str, expected_format: str) -> Tuple[bool, str]:
        """验证数据格式"""

        if expected_format == "json":
            try:
                import json
                json.loads(data)
                return True, "JSON 格式正确"
            except:
                return False, "数据不是有效的 JSON"

        elif expected_format == "csv":
            # 简单检查：包含换行和逗号
            if "\n" in data and "," in data:
                return True, "CSV 格式正确"
            return False, "数据不是有效的 CSV"

        elif expected_format == "text":
            # 文本格式总是有效
            return True, "文本格式正确"

        elif expected_format == "base64":
            try:
                import base64
                base64.b64decode(data)
                return True, "Base64 格式正确"
            except:
                return False, "数据不是有效的 Base64"

        # 其他格式，默认通过
        return True, f"格式检查跳过: {expected_format}"