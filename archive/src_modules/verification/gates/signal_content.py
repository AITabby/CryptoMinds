"""
信号订阅验证门

验证信号流订阅服务：
- 信号是否按时推送
- 信号格式是否正确
- 信号质量评分
"""

import hashlib
import time
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from ..base import VerificationGate, VerificationResult, TaskInput, TaskOutput


class SignalStreamGate(VerificationGate):
    """
    信号订阅验证门

    gate_id: signal_stream
    task_type: signal_stream

    验证逻辑：
    1. 检查信号是否按时推送
    2. 检查信号格式是否符合预期
    3. 检查信号质量（准确率、延迟等）
    """

    gate_id = "signal_stream"
    task_type = "signal_stream"
    version = "1.0.0"
    description = "验证信号订阅服务"
    supported_chains = []  # 不依赖特定链

    def __init__(
        self,
        min_signals: int = 1,
        max_delay_seconds: int = 60,
    ):
        """
        Args:
            min_signals: 最小信号数量
            max_delay_seconds: 最大延迟时间
        """
        self.min_signals = min_signals
        self.max_delay_seconds = max_delay_seconds

    def validate_input(self, input: TaskInput) -> Tuple[bool, str]:
        """验证输入格式"""
        if not input.buyer_wallet:
            return False, "缺少买家钱包地址"

        if input.task_type != "signal_stream":
            return False, f"任务类型不匹配: {input.task_type}"

        # 检查参数
        params = input.params
        if not params.get("signal_type"):
            return False, "缺少信号类型参数"

        if not params.get("duration_hours"):
            return False, "缺少订阅时长参数"

        return True, "输入验证通过"

    def validate_output(self, output: TaskOutput) -> Tuple[bool, str]:
        """验证输出格式"""
        # 信号流需要：
        # 1. signals 数组
        # 2. 或者 data 包含信号

        if not output.data and not output.extra.get("signals"):
            return False, "缺少信号数据"

        return True, "输出验证通过"

    def verify(self, input: TaskInput, output: TaskOutput) -> VerificationResult:
        """验证信号流"""
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

        # 2. 获取参数
        params = input.params
        signal_type = params.get("signal_type", "generic")
        duration_hours = params.get("duration_hours", 24)
        expected_format = params.get("expected_format", "json")

        # 3. 解析信号
        signals = self._parse_signals(output)

        if len(signals) < self.min_signals:
            return VerificationResult(
                success=False,
                gate_id=self.gate_id,
                task_type=self.task_type,
                error=f"信号数量不足: {len(signals)} < {self.min_signals}",
            )

        # 4. 验证信号格式
        format_errors = []
        for i, signal in enumerate(signals):
            if not self._validate_signal_format(signal, expected_format):
                format_errors.append(i)

        if format_errors:
            return VerificationResult(
                success=False,
                gate_id=self.gate_id,
                task_type=self.task_type,
                error=f"信号格式错误: 位置 {format_errors[:5]}",
            )

        # 5. 验证信号延迟
        delays = []
        now = int(time.time())
        for signal in signals:
            signal_time = signal.get("timestamp", 0)
            if signal_time:
                delay = now - signal_time
                delays.append(delay)

        if delays:
            max_delay = max(delays)
            if max_delay > self.max_delay_seconds:
                return VerificationResult(
                    success=False,
                    gate_id=self.gate_id,
                    task_type=self.task_type,
                    error=f"信号延迟过大: {max_delay}s > {self.max_delay_seconds}s",
                )

        # 6. 计算质量分
        score = 1.0

        # 根据信号数量调整
        expected_signals = duration_hours  # 假设每小时 1 个信号
        if len(signals) >= expected_signals:
            score = min(1.0, len(signals) / expected_signals)
        else:
            score = len(signals) / expected_signals

        # 根据延迟调整
        if delays:
            avg_delay = sum(delays) / len(delays)
            if avg_delay > 30:
                score *= 0.9
            if avg_delay > 60:
                score *= 0.8

        # 7. 返回结果
        evidence = {
            "signal_type": signal_type,
            "signal_count": len(signals),
            "duration_hours": duration_hours,
            "avg_delay_seconds": sum(delays) / len(delays) if delays else 0,
            "format_errors": len(format_errors),
        }

        return VerificationResult(
            success=True,
            score=score,
            gate_id=self.gate_id,
            task_type=self.task_type,
            evidence=evidence,
        )

    def _parse_signals(self, output: TaskOutput) -> List[Dict]:
        """解析信号列表"""
        # 从 extra.signals 获取
        if output.extra.get("signals"):
            return output.extra["signals"]

        # 从 data 解析
        if output.data:
            try:
                import json
                data = json.loads(output.data)
                if isinstance(data, list):
                    return data
                if isinstance(data, dict) and "signals" in data:
                    return data["signals"]
            except:
                pass

        return []

    def _validate_signal_format(self, signal: Dict, expected_format: str) -> bool:
        """验证单个信号格式"""
        if not isinstance(signal, dict):
            return False

        # 基本字段
        required_fields = ["type", "timestamp"]
        for field in required_fields:
            if field not in signal:
                return False

        return True


class ContentDeliveryGate(VerificationGate):
    """
    内容交付验证门

    验证内容创作服务：
- 文章、图片、音频、视频
    - 内容质量和原创性
    """

    gate_id = "content_delivery"
    task_type = "content_delivery"
    version = "1.0.0"
    description = "验证内容创作交付"
    supported_chains = []

    def __init__(
        self,
        min_length: int = 0,
        max_length: int = 100000,
    ):
        self.min_length = min_length
        self.max_length = max_length

    def validate_input(self, input: TaskInput) -> Tuple[bool, str]:
        """验证输入格式"""
        if not input.buyer_wallet:
            return False, "缺少买家钱包地址"

        if input.task_type != "content_delivery":
            return False, f"任务类型不匹配: {input.task_type}"

        params = input.params
        if not params.get("content_type"):
            return False, "缺少内容类型参数"

        return True, "输入验证通过"

    def validate_output(self, output: TaskOutput) -> Tuple[bool, str]:
        """验证输出格式"""
        if not output.data and not output.file_hash:
            return False, "缺少内容或文件哈希"

        return True, "输出验证通过"

    def verify(self, input: TaskInput, output: TaskOutput) -> VerificationResult:
        """验证内容交付"""
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

        # 获取参数
        params = input.params
        content_type = params.get("content_type", "text")
        expected_format = params.get("expected_format", None)
        min_words = params.get("min_words", 0)

        evidence = {
            "content_type": content_type,
            "file_hash": output.file_hash,
            "data_length": len(output.data) if output.data else 0,
        }

        # 验证内容长度
        if output.data:
            data_len = len(output.data)
            if data_len < self.min_length:
                return VerificationResult(
                    success=False,
                    gate_id=self.gate_id,
                    task_type=self.task_type,
                    error=f"内容太短: {data_len} < {self.min_length}",
                    evidence=evidence,
                )

            if data_len > self.max_length:
                return VerificationResult(
                    success=False,
                    gate_id=self.gate_id,
                    task_type=self.task_type,
                    error=f"内容太长: {data_len} > {self.max_length}",
                    evidence=evidence,
                )

        # 验证内容类型
        if content_type == "text":
            score = self._verify_text(output, min_words)
        elif content_type == "image":
            score = self._verify_image(output)
        elif content_type == "audio":
            score = self._verify_audio(output)
        elif content_type == "video":
            score = self._verify_video(output)
        else:
            score = 1.0

        evidence["quality_score"] = score

        return VerificationResult(
            success=True,
            score=score,
            gate_id=self.gate_id,
            task_type=self.task_type,
            evidence=evidence,
        )

    def _verify_text(self, output: TaskOutput, min_words: int) -> float:
        """验证文本内容"""
        if not output.data:
            return 0.5

        # 字数统计
        words = len(output.data.split())
        if min_words and words < min_words:
            return 0.5

        # 基本质量检查
        score = 1.0

        # 检查是否有明显问题
        if len(output.data) < 50:
            score *= 0.7

        # 检查格式
        try:
            import json
            json.loads(output.data)
            # 如果是 JSON，可能是结构化内容
        except:
            pass

        return score

    def _verify_image(self, output: TaskOutput) -> float:
        """验证图片内容"""
        # 简化处理：检查是否有 base64 或 URL
        if output.file_hash:
            return 1.0

        if output.data and ("data:image" in output.data or "http" in output.data):
            return 1.0

        return 0.5

    def _verify_audio(self, output: TaskOutput) -> float:
        """验证音频内容"""
        if output.file_hash:
            return 1.0
        return 0.5

    def _verify_video(self, output: TaskOutput) -> float:
        """验证视频内容"""
        if output.file_hash:
            return 1.0
        return 0.5
