"""
Context Completeness & Quality Validator.
Audits the execution of Context Planner and Context Retriever:
1. Checks Semantic Consistency (Did Planner miss any critical context required by Semantic Graph?).
2. Checks Retrieval Completeness (Did Retriever fail to fetch data, return empty/None, or miss targeted entities?).
3. Computes a Completeness & Grounding Score (0.0 - 1.0).
4. Generates detailed warnings, missing information lists, and actionable recommendations.
"""

import os
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

# Thêm thư mục gốc vào path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from database import Database


class ContextCompletenessValidator:
    """
    Module kiểm tra và thẩm định tính toàn vẹn của Context:
    Phát hiện các thiếu sót quan trọng giữa yêu cầu người dùng, kế hoạch (Planner) và dữ liệu thực tế (Retriever).
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            self.db_path = os.path.join(parent_dir, "warehouse.db")
        else:
            self.db_path = db_path
        self.db = Database(db_path=self.db_path)

    def _get_semantic_graph_dependencies(self) -> Dict[str, List[Dict[str, str]]]:
        """Lấy các quan hệ ngữ nghĩa từ cơ sở dữ liệu để kiểm tra phụ thuộc."""
        try:
            relationships = self.db.list_context_relationships()
            graph: Dict[str, List[Dict[str, str]]] = {}
            for r in relationships:
                src = r["source_name"]
                if src not in graph:
                    graph[src] = []
                graph[src].append({
                    "relation": r["relation"],
                    "target": r["target_name"],
                    "description": r.get("description", "")
                })
            return graph
        except Exception:
            return {}

    def audit(
        self,
        query: str,
        plan: Dict[str, Any],
        retrieved_context: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Thực hiện đánh giá toàn diện tính đầy đủ của context:
        - `query`: Câu hỏi ban đầu của người dùng
        - `plan`: Kết quả từ Planner (intent, entities, required_context, reasoning)
        - `retrieved_context`: Kết quả từ Retriever ([{"context": ..., "data": ...}])
        """
        required_contexts: List[str] = plan.get("required_context", [])
        entities: Dict[str, Any] = plan.get("entities", {})
        intent: str = plan.get("intent", "general_inquiry")

        missing_contexts: List[str] = []
        missing_entities: List[Dict[str, Any]] = []
        empty_contexts: List[str] = []
        warnings: List[str] = []
        recommendations: List[str] = []

        # 1. KIỂM TRA MỨC ĐỘ THỰC THI CỦA RETRIEVER (Retrieved vs Planned)
        retrieved_map: Dict[str, Any] = {}
        for item in retrieved_context:
            ctx_name = item.get("context", "")
            data = item.get("data")
            retrieved_map[ctx_name] = data

            # Kiểm tra dữ liệu rỗng hoặc None
            if data is None or data == "" or data == {} or data == []:
                empty_contexts.append(ctx_name)
                warnings.append(f"Context '{ctx_name}' đã được lên kế hoạch nhưng không lấy được dữ liệu (rỗng/None).")

        # Kiểm tra context nào được lên kế hoạch nhưng hoàn toàn vắng mặt trong retrieved_context
        for req in required_contexts:
            if req not in retrieved_map:
                missing_contexts.append(req)
                warnings.append(f"Context '{req}' có trong required_context nhưng Retriever không trả về mục này.")

        # 2. KIỂM TRA KHỚP THỰC THỂ (Entity Grounding Verification)
        # 2.1 Kiểm tra khách hàng
        target_customer = entities.get("customer")
        if target_customer:
            cust_data = retrieved_map.get("customer") or retrieved_map.get("customers")
            if not cust_data:
                missing_entities.append({"entity": "customer", "expected": target_customer, "actual": None})
                warnings.append(f"Khách hàng '{target_customer}' được chỉ định nhưng không tìm thấy trong dữ liệu truy xuất.")
            elif isinstance(cust_data, dict):
                actual_name = cust_data.get("name", "")
                if target_customer.lower() not in actual_name.lower():
                    warnings.append(f"Khách hàng truy xuất được '{actual_name}' có thể không khớp chính xác với '{target_customer}'.")

        # 2.2 Kiểm tra đơn hàng
        target_order_id = entities.get("order_id")
        if target_order_id:
            order_data = retrieved_map.get("order") or retrieved_map.get("orders")
            if not order_data:
                missing_entities.append({"entity": "order_id", "expected": target_order_id, "actual": None})
                warnings.append(f"Đơn hàng ID '{target_order_id}' được chỉ định nhưng không tìm thấy trong database.")
            elif isinstance(order_data, dict):
                actual_id = str(order_data.get("id", ""))
                if str(target_order_id) != actual_id:
                    warnings.append(f"Đơn hàng lấy được (ID #{actual_id}) khác với mã đơn yêu cầu (ID #{target_order_id}).")

        # 3. KIỂM TRA PHỤ THUỘC NGỮ NGHĨA (Semantic Graph & Policy Rules)
        query_lower = query.lower()
        semantic_graph = self._get_semantic_graph_dependencies()

        # Quy tắc 1: Nếu hỏi về hoàn tiền / đổi trả -> bắt buộc phải có refund_policy
        if any(w in query_lower for w in ["hoàn tiền", "đổi trả", "refund", "return"]):
            if "refund_policy" not in required_contexts and "refund_policy" not in retrieved_map:
                missing_contexts.append("refund_policy")
                warnings.append("Câu hỏi liên quan đến đổi trả/hoàn tiền nhưng thiếu chính sách 'refund_policy'.")
                recommendations.append("Bổ sung 'refund_policy' để có căn cứ thời hạn và điều kiện hoàn tiền.")

        # Quy tắc 2: Nếu có khách VIP / Hạng thành viên -> bắt buộc có vip_policy
        if any(w in query_lower for w in ["vip", "hạng", "tier", "platinum", "gold", "silver", "bronze"]):
            if "vip_policy" not in required_contexts and "vip_policy" not in retrieved_map:
                missing_contexts.append("vip_policy")
                warnings.append("Câu hỏi liên quan đến phân hạng/VIP nhưng thiếu chính sách 'vip_policy'.")
                recommendations.append("Bổ sung 'vip_policy' để tra cứu đặc quyền và mức chiết khấu của hạng thành viên.")

        # Quy tắc 3: Nếu hỏi về giao hàng / ship / vận chuyển -> bắt buộc có delivery_policy
        if any(w in query_lower for w in ["giao hàng", "vận chuyển", "ship", "delivery", "hỏa tốc"]):
            if "delivery_policy" not in required_contexts and "delivery_policy" not in retrieved_map:
                missing_contexts.append("delivery_policy")
                warnings.append("Câu hỏi liên quan đến vận chuyển nhưng thiếu chính sách 'delivery_policy'.")
                recommendations.append("Bổ sung 'delivery_policy' để tra cứu phí ship và thời gian giao hàng.")

        # Quy tắc 4: Nếu có orders và cần tính chính sách đổi trả -> cần tier của customer
        if ("orders" in required_contexts or "order" in required_contexts) and ("refund_policy" in required_contexts or "refund_policy" in retrieved_map):
            if "customers" not in required_contexts and "customer" not in required_contexts:
                recommendations.append("Nên bổ sung 'customers' để xác định cấp bậc thành viên, giúp áp dụng đúng thời hạn đổi trả trong refund_policy.")

        # 4. TÍNH TOÁN ĐIỂM CHẤT LƯỢNG (Completeness Score: 0.0 - 1.0)
        total_checks = max(len(required_contexts), 1) + len(missing_entities) + len(missing_contexts)
        penalty = (len(empty_contexts) * 0.25) + (len(missing_contexts) * 0.3) + (len(missing_entities) * 0.35)
        raw_score = max(0.0, 1.0 - penalty)
        completeness_score = round(raw_score, 2)

        is_complete = (len(missing_contexts) == 0 and len(empty_contexts) == 0 and len(missing_entities) == 0)

        # Trạng thái tổng quát
        if completeness_score >= 0.9:
            status = "EXCELLENT"
        elif completeness_score >= 0.7:
            status = "GOOD"
        elif completeness_score >= 0.5:
            status = "WARNING_INCOMPLETE"
        else:
            status = "CRITICAL_MISSING"

        return {
            "is_complete": is_complete,
            "status": status,
            "completeness_score": completeness_score,
            "missing_contexts": list(set(missing_contexts)),
            "empty_contexts": list(set(empty_contexts)),
            "missing_entities": missing_entities,
            "warnings": warnings,
            "recommendations": list(set(recommendations))
        }


def validate_pipeline(
    query: str,
    plan: Dict[str, Any],
    retrieved_context: List[Dict[str, Any]],
    **kwargs
) -> Dict[str, Any]:
    """Hàm helper tiện lợi để thẩm định nhanh luồng Context Pipeline."""
    validator = ContextCompletenessValidator(**kwargs)
    return validator.audit(query=query, plan=plan, retrieved_context=retrieved_context)


if __name__ == "__main__":
    import json

    # Test trường hợp đầy đủ
    q_good = "Tôi là Nguyễn Văn An muốn kiểm tra đơn hàng 5 và điều kiện hoàn tiền"
    plan_good = {
        "intent": "refund_eligibility",
        "entities": {"customer": "Nguyễn Văn An", "order_id": 5},
        "required_context": ["customer", "order", "refund_policy", "vip_policy"]
    }
    retrieved_good = [
        {"context": "customer", "data": {"id": 4, "name": "Nguyễn Văn An", "tier": "platinum"}},
        {"context": "order", "data": {"id": 5, "amount": 3499.0, "status": "completed"}},
        {"context": "refund_policy", "data": "Chính sách đổi trả trong 45 ngày cho Platinum..."},
        {"context": "vip_policy", "data": "Đặc quyền Platinum..."}
    ]

    validator = ContextCompletenessValidator()
    res_good = validator.audit(q_good, plan_good, retrieved_good)
    print("=== TEST 1: ĐẦY ĐỦ THÔNG TIN ===")
    print(json.dumps(res_good, indent=2, ensure_ascii=False))

    # Test trường hợp THIẾU THÔNG TIN (Ví dụ: hỏi hoàn tiền nhưng thiếu refund_policy, order_id không tìm thấy)
    q_bad = "Khách hàng 9999 có được hoàn tiền đơn hàng 8888 không?"
    plan_bad = {
        "intent": "refund_eligibility",
        "entities": {"customer": "9999", "order_id": 8888},
        "required_context": ["order"]  # Thiếu customer, refund_policy, vip_policy
    }
    retrieved_bad = [
        {"context": "order", "data": None}  # Order không tìm thấy
    ]
    res_bad = validator.audit(q_bad, plan_bad, retrieved_bad)
    print("\n=== TEST 2: THIẾU SÓT THÔNG TIN QUAN TRỌNG ===")
    print(json.dumps(res_bad, indent=2, ensure_ascii=False))
