"""
计算结果验证门

验证卖家是否正确完成计算任务（GPU 推理、模型训练等）。
"""

import hashlib
import time
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from ..base import VerificationGate, VerificationResult, TaskInput, TaskOutput


class ComputeResultGate(VerificationGate):
    """
    计算结果验证门

    gate_id: compute_result
    task_type: compute_result

    验证逻辑：
    1. 检查输出结果是否存在
    2. 如果有预期结果，进行对比验证
    3. 如果有验证函数，执行验证
    """

    gate_id = "compute_result"
    task_type = "compute_result"
    version = "1.0.0"
    description = "验证计算结果是否正确"
    supported_chains = []  # 计算任务不依赖特定链

    def __init__(self):
        pass

    # ── 输入/输出验证 ─────────────────────────────────

    def validate_input(self, input: TaskInput) -> Tuple[bool, str]:
        """验证输入格式"""
        if not input.buyer_wallet:
            return False, "缺少买家钱包地址"

        if input.task_type != "compute_result":
            return False, f"任务类型不匹配: {input.task_type}"

        # 检查参数
        params = input.params
        if not params.get("compute_type"):
            return False, "缺少计算类型参数"

        return True, "输入验证通过"

    def validate_output(self, output: TaskOutput) -> Tuple[bool, str]:
        """验证输出格式"""
        # 计算结果需要：
        # 1. data（结果数据）
        # 2. 或者 file_hash（结果文件）

        if not output.data and not output.file_hash:
            return False, "缺少计算结果"

        return True, "输出验证通过"

    # ── 核心验证逻辑 ───────────────────────────────────

    def verify(self, input: TaskInput, output: TaskOutput) -> VerificationResult:
        """
        验证计算结果

        检查：
        1. 结果是否存在
        2. 结果是否匹配预期（如果有）
        3. 执行验证函数（如果有）
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

        # 2. 获取参数
        params = input.params
        compute_type = params.get("compute_type", "generic")
        expected_result = params.get("expected_result", None)
        verify_function = params.get("verify_function", None)
        tolerance = params.get("tolerance", 0.01)  # 允许误差

        evidence = {
            "compute_type": compute_type,
            "file_hash": output.file_hash,
            "data_size": len(output.data) if output.data else 0,
        }

        # 3. 如果有预期结果，进行对比
        if expected_result and output.data:
            match_result = self._compare_results(output.data, expected_result, tolerance)

            if not match_result["match"]:
                return VerificationResult(
                    success=False,
                    gate_id=self.gate_id,
                    task_type=self.task_type,
                    error=match_result["error"],
                    evidence=evidence,
                )

            evidence["match_score"] = match_result["score"]

        # 4. 如果有验证函数描述，检查输出是否满足
        if verify_function:
            # 这里简化处理：验证函数是字符串描述
            # 实际实现可以支持动态执行验证代码
            verify_passed = self._check_verify_conditions(output, verify_function)

            if not verify_passed:
                return VerificationResult(
                    success=False,
                    gate_id=self.gate_id,
                    task_type=self.task_type,
                    error="结果不满足验证条件",
                    evidence=evidence,
                )

        # 5. 计算质量分
        score = 1.0
        if output.extra.get("quality_score"):
            try:
                score = float(output.extra.get("quality_score"))
            except:
                pass

        # 根据计算类型调整评分
        if compute_type == "inference":
            # 推理任务：检查置信度
            confidence = output.extra.get("confidence", 1.0)
            score = min(1.0, confidence)

        elif compute_type == "training":
            # 训练任务：检查损失值
            loss = output.extra.get("final_loss")
            if loss:
                # 损失越低，分数越高
                score = max(0.5, 1.0 - float(loss))

        return VerificationResult(
            success=True,
            score=score,
            gate_id=self.gate_id,
            task_type=self.task_type,
            evidence=evidence,
        )

    def _compare_results(self, actual: str, expected: str, tolerance: float) -> Dict:
        """对比结果"""

        try:
            import json

            # 尝试 JSON 解析
            actual_data = json.loads(actual)
            expected_data = json.loads(expected)

            # 数值对比
            if isinstance(actual_data, (int, float)) and isinstance(expected_data, (int, float)):
                diff = abs(actual_data - expected_data)
                max_val = max(abs(actual_data), abs(expected_data), 1)

                if diff / max_val <= tolerance:
                    return {"match": True, "score": 1.0 - diff / max_val}
                return {"match": False, "error": f"数值差异过大: {diff}"}

            # 字符串对比
            if isinstance(actual_data, str) and isinstance(expected_data, str):
                if actual_data == expected_data:
                    return {"match": True, "score": 1.0}
                return {"match": False, "error": "字符串不匹配"}

            # 数组对比
            if isinstance(actual_data, list) and isinstance(expected_data, list):
                if len(actual_data) != len(expected_data):
                    return {"match": False, "error": "数组长度不匹配"}

                matches = sum(1 for a, e in zip(actual_data, expected_data) if a == e)
                score = matches / len(actual_data)

                if score >= 1.0 - tolerance:
                    return {"match": True, "score": score}
                return {"match": False, "error": f"数组匹配率过低: {score:.2%}"}

            # 对象对比
            if isinstance(actual_data, dict) and isinstance(expected_data, dict):
                keys_match = set(actual_data.keys()) == set(expected_data.keys())
                if not keys_match:
                    return {"match": False, "error": "键不匹配"}

                matches = sum(1 for k in actual_data if actual_data[k] == expected_data[k])
                score = matches / len(actual_data)

                if score >= 1.0 - tolerance:
                    return {"match": True, "score": score}
                return {"match": False, "error": f"对象匹配率过低: {score:.2%}"}

            # 其他类型：直接对比
            if actual_data == expected_data:
                return {"match": True, "score": 1.0}
            return {"match": False, "error": "结果不匹配"}

        except json.JSONDecodeError:
            # 非 JSON：字符串对比
            if actual == expected:
                return {"match": True, "score": 1.0}

            # 计算相似度
            similarity = self._string_similarity(actual, expected)
            if similarity >= 1.0 - tolerance:
                return {"match": True, "score": similarity}
            return {"match": False, "error": f"字符串相似度过低: {similarity:.2%}"}

    def _string_similarity(self, s1: str, s2: str) -> float:
        """计算字符串相似度（简单的 Jaccard）"""
        if not s1 or not s2:
            return 0.0

        set1 = set(s1.split())
        set2 = set(s2.split())

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        return intersection / union if union > 0 else 0.0

    def _check_verify_conditions(self, output: TaskOutput, verify_function: str) -> bool:
        """检查验证条件"""

        # 简化实现：检查关键字
        conditions = verify_function.lower()

        # 检查常见条件
        if "non_empty" in conditions:
            if not output.data:
                return False

        if "valid_json" in conditions:
            try:
                import json
                json.loads(output.data)
            except:
                return False

        if "positive" in conditions:
            try:
                val = float(output.data)
                if val <= 0:
                    return False
            except:
                pass

        # 默认通过
        return True