"""
Context Package Module.
Transforms raw ContextPlan and RetrievedContext into a clean, validated, and structured Context Package:
1. Validates plan & retrieved completeness using ContextCompletenessValidator (validator.py).
2. Filters and extracts only necessary fields/sections into a clean schema dictionary.
3. Formats clean data into standard prompt blocks (=== SECTION ===) ready for LLM consumption.
"""

import json
import os
import sys
from typing import Any, Dict, List, Optional, Union

# Thêm thư mục gốc vào path để import
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from ultis.validator import ContextCompletenessValidator


class ContextPackage:
    """
    Đối tượng Context Package:
    - Nhận vào Context Plan + Retrieved Context (+ Query người dùng).
    - Thẩm định tính đầy đủ thông qua validator.py.
    - Lọc và làm sạch dữ liệu (loại bỏ trường thừa, chuẩn hóa tên key, cắt tỉa text policy).
    - Xuất schema dạng dict sạch và format text chuẩn (=== HEADER ===) cho LLM.
    """

    # Ánh xạ chuẩn hóa tên context (chuyển số nhiều/tên bảng về dạng khóa đại diện chuẩn)
    KEY_NORMALIZATION = {
        "customers": "customer",
        "customer": "customer",
        "orders": "order",
        "order": "order",
        "products": "product",
        "product": "product",
        "users": "user",
        "user": "user",
        "catalog": "catalog",
        "refund_policy": "refund_policy",
        "vip_policy": "vip_policy",
        "delivery_policy": "delivery_policy",
    }

    def __init__(
        self,
        plan: Dict[str, Any],
        retrieved_context: List[Dict[str, Any]],
        query: Optional[str] = None,
        validator: Optional[ContextCompletenessValidator] = None,
        db_path: Optional[str] = None
    ) -> None:
        self.plan = plan or {}
        self.retrieved_context = retrieved_context or []
        self.query = query or ""
        self.db_path = db_path

        # Khởi tạo hoặc gán validator
        if validator is not None:
            self.validator = validator
        else:
            self.validator = ContextCompletenessValidator(db_path=db_path)

        # 1. Thẩm định tính đầy đủ và toàn vẹn của context
        self.validation_report: Dict[str, Any] = self._run_validation()

        # 2. Xây dựng Schema dữ liệu đã được lọc và làm sạch
        self.clean_data: Dict[str, Any] = self._build_clean_schema()

        # 3. Tạo chuỗi format chuẩn chỉnh cho LLM prompt
        self.formatted_text: str = self._format_text()

    def _run_validation(self) -> Dict[str, Any]:
        """Kiểm tra xem required_context và dữ liệu retrieve có đầy đủ, chuẩn xác không."""
        return self.validator.audit(
            query=self.query,
            plan=self.plan,
            retrieved_context=self.retrieved_context
        )

    def _normalize_key(self, raw_key: str) -> str:
        """Chuẩn hóa tên context key (ví dụ: customers -> customer)."""
        key = raw_key.lower().strip()
        return self.KEY_NORMALIZATION.get(key, key)

    def _clean_dict_item(self, item: Dict[str, Any], target_fields: Optional[List[str]] = None) -> Dict[str, Any]:
        """Lọc và giữ lại đúng các trường cần thiết trong dict record."""
        if not isinstance(item, dict):
            return item

        # Nếu có target_fields được chỉ định từ plan
        if target_fields and target_fields != ["all"] and "*" not in target_fields:
            cleaned = {}
            for f in target_fields:
                if f in item:
                    cleaned[f] = item[f]
                # Hỗ trợ alias như total_price <-> amount
                elif f == "amount" and "total_price" in item:
                    cleaned["amount"] = item["total_price"]
                elif f == "total_price" and "amount" in item:
                    cleaned["total_price"] = item["amount"]
            if cleaned:
                return cleaned

        # Mặc định: loại bỏ các trường nội bộ không cần thiết nếu có
        unwanted_fields = ["password", "hashed_password", "token", "secret", "created_by"]
        return {k: v for k, v in item.items() if k not in unwanted_fields and v is not None}

    def _clean_policy_text(self, text: str) -> str:
        """Làm sạch văn bản markdown policy (bỏ khoảng trắng thừa)."""
        if not isinstance(text, str):
            return str(text)
        lines = [line.rstrip() for line in text.strip().split("\n")]
        cleaned_lines = []
        consecutive_empty = 0
        for line in lines:
            if not line:
                consecutive_empty += 1
                if consecutive_empty <= 1:
                    cleaned_lines.append(line)
            else:
                consecutive_empty = 0
                cleaned_lines.append(line)
        return "\n".join(cleaned_lines).strip()

    def _build_clean_schema(self) -> Dict[str, Any]:
        """
        Trích xuất và làm sạch dữ liệu từ retrieved_context thành schema dict chuẩn:
        {
            "customer": {"name": "Nguyễn Văn An", "tier": "platinum"},
            "order": {"id": 5, "amount": 3499.0, "status": "completed", ...},
            "refund_policy": "..."
        }
        """
        clean_schema: Dict[str, Any] = {}
        plan_fields = self.plan.get("fields", {})

        for item in self.retrieved_context:
            raw_context_name = item.get("context", "")
            data = item.get("data")
            if not raw_context_name or data is None or data == "" or data == {} or data == []:
                continue

            normalized_key = self._normalize_key(raw_context_name)
            target_fields = plan_fields.get(raw_context_name) or plan_fields.get(normalized_key)

            if isinstance(data, dict):
                clean_schema[normalized_key] = self._clean_dict_item(data, target_fields)
            elif isinstance(data, list):
                # Danh sách các records
                cleaned_list = []
                for sub_item in data:
                    if isinstance(sub_item, dict):
                        cleaned_list.append(self._clean_dict_item(sub_item, target_fields))
                    else:
                        cleaned_list.append(sub_item)
                
                # Nếu chỉ có 1 record và key là số ít -> gán trực tiếp record
                if len(cleaned_list) == 1 and normalized_key in ["customer", "order", "product", "user"]:
                    clean_schema[normalized_key] = cleaned_list[0]
                else:
                    clean_schema[normalized_key] = cleaned_list
            elif isinstance(data, str):
                clean_schema[normalized_key] = self._clean_policy_text(data)
            else:
                clean_schema[normalized_key] = data

        return clean_schema

    def _format_text(self) -> str:
        """
        Format schema đã làm sạch thành chuỗi văn bản chuẩn chỉnh:
        === CUSTOMER ===
        {'name': 'Nguyễn Văn An', 'tier': 'platinum'}

        === ORDER ===
        {'id': 5, 'amount': 3499.0, 'status': 'completed', ...}

        === REFUND_POLICY ===
        ...
        """
        blocks: List[str] = []

        for key, value in self.clean_data.items():
            header = f"=== {key.upper()} ==="
            if isinstance(value, dict):
                content = str(value)
            elif isinstance(value, list):
                if all(isinstance(x, dict) for x in value):
                    content = "\n".join([str(x) for x in value])
                else:
                    content = str(value)
            elif isinstance(value, str):
                content = value
            else:
                content = str(value)

            blocks.append(f"{header}\n{content}")

        return "\n\n".join(blocks)

    def get_clean_data(self) -> Dict[str, Any]:
        """Trả về Schema dict đã lọc và làm sạch."""
        return self.clean_data

    def format_for_llm(self) -> str:
        """Trả về chuỗi format chuẩn chỉnh cho LLM."""
        return self.formatted_text

    @property
    def is_complete(self) -> bool:
        """Kiểm tra xem context package có đạt chuẩn đầy đủ không."""
        return bool(self.validation_report.get("is_complete", False))

    @property
    def completeness_score(self) -> float:
        """Điểm toàn vẹn của context package (0.0 -> 1.0)."""
        return float(self.validation_report.get("completeness_score", 0.0))

    def to_dict(self) -> Dict[str, Any]:
        """Xuất toàn bộ package thành dictionary đầy đủ thông tin."""
        return {
            "query": self.query,
            "intent": self.plan.get("intent"),
            "clean_data": self.clean_data,
            "formatted_text": self.formatted_text,
            "validation_report": self.validation_report,
            "is_complete": self.is_complete,
            "completeness_score": self.completeness_score
        }

    def __str__(self) -> str:
        return self.formatted_text

    def __repr__(self) -> str:
        keys = list(self.clean_data.keys())
        return f"<ContextPackage keys={keys} score={self.completeness_score} status={self.validation_report.get('status')}>"


def build_context_package(
    plan: Dict[str, Any],
    retrieved_context: List[Dict[str, Any]],
    query: Optional[str] = None,
    **kwargs
) -> ContextPackage:
    """Hàm helper tiện lợi để tạo nhanh đối tượng ContextPackage."""
    return ContextPackage(
        plan=plan,
        retrieved_context=retrieved_context,
        query=query,
        **kwargs
    )


if __name__ == "__main__":
    # Test thử nghiệm ContextPackage
    q_sample = "Khách hàng Nguyễn Văn An muốn kiểm tra đơn hàng 5 và điều kiện hoàn tiền"
    plan_sample = {
        "intent": "refund_eligibility",
        "entities": {"customer": "Nguyễn Văn An", "order_id": 5},
        "required_context": ["customers", "orders", "refund_policy"],
        "fields": {
            "customers": ["name", "tier"],
            "orders": ["id", "amount", "status", "order_date"]
        }
    }
    retrieved_sample = [
        {
            "context": "customers",
            "source_doc": "SQLite/warehouse.db (table: customers)",
            "section": ["name", "tier"],
            "data": {"id": 4, "name": "Nguyễn Văn An", "tier": "platinum", "phone": "0901234567"}
        },
        {
            "context": "orders",
            "source_doc": "SQLite/warehouse.db (table: orders)",
            "section": ["id", "amount", "status", "order_date"],
            "data": {"id": 5, "total_price": 3499.0, "status": "completed", "order_date": "2026-08-29 08:28:53"}
        },
        {
            "context": "refund_policy",
            "source_doc": "refund_policy.md",
            "section": "tier_based_return_timing",
            "data": "## 2. Thời Gian Đổi Trả Theo Cấp Bậc Khách Hàng (Customer Tier)\n- Platinum: 45 ngày\n- Hoàn tiền 100%"
        }
    ]

    package = ContextPackage(
        plan=plan_sample,
        retrieved_context=retrieved_sample,
        query=q_sample
    )

    print("================ 1. CLEAN DATA SCHEMA (DICT) ================")
    print(json.dumps(package.get_clean_data(), indent=4, ensure_ascii=False))

    print("\n================ 2. FORMATTED FOR LLM (TEXT) ================")
    print(package.format_for_llm())

    print("\n================ 3. VALIDATION REPORT ================")
    print(json.dumps(package.validation_report, indent=2, ensure_ascii=False))
