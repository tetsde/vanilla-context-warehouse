"""
Context Planner Module.
Analyzes incoming user requests to determine which database tables and policy contexts
are strictly required, using Google Gemini with structured JSON output and XML prompt formatting.
"""

import json
import os
import sys
from typing import Any, Dict, List, Optional

import dotenv
import google.generativeai as genai

# Thêm thư mục gốc vào path để import
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from composer.catalog import CatalogContextLoader


class ContextPlanner:
    """
    Module phân tích yêu cầu người dùng và xác định các context cần thiết (tables & policies).
    Sử dụng mô hình Gemini (mặc định gemini-2.5-flash-lite với cơ chế tự động fallback sang gemini-3.5-flash-lite).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-2.5-flash-lite",
        fallback_models: Optional[List[str]] = None,
        db_path: Optional[str] = None,
        context_dir: Optional[str] = None
    ) -> None:
        # 1. Đọc API Key từ .env
        dotenv_path = os.path.join(parent_dir, ".env")
        if os.path.exists(dotenv_path):
            dotenv.load_dotenv(dotenv_path)
        else:
            dotenv.load_dotenv()

        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Không tìm thấy GEMINI_API_KEY! Vui lòng cấu hình trong file .env hoặc truyền trực tiếp."
            )

        genai.configure(api_key=self.api_key)
        self.model_name = model_name
        self.fallback_models = fallback_models or [
            "gemini-3.5-flash-lite",
            "gemini-2.5-flash",
            "gemini-flash-lite-latest",
            "gemini-flash-latest"
        ]

        # 2. Khởi tạo loader lấy metadata catalog dưới dạng XML
        self.catalog_loader = CatalogContextLoader(db_path=db_path, context_dir=context_dir)

    def build_prompt_xml(self, user_query: str) -> str:
        """
        Tạo prompt hoàn chỉnh dưới định dạng XML bao gồm:
        - <system_instructions>: Vai trò và nguyên tắc lựa chọn context
        - <available_contexts>: Toàn bộ metadata của Database Tables, Policies và Semantic Relationships
        - <user_query>: Yêu cầu của người dùng
        - <output_format>: Yêu cầu định dạng JSON
        """
        metadata_xml = self.catalog_loader.build_xml_context_metadata()

        prompt = f"""<context_planning_request>
  <system_instructions>
    Bạn là một AI Context Planner chuyên nghiệp cho hệ thống Data Warehouse & Context Engine.
    Nhiệm vụ của bạn là phân tích câu hỏi/yêu cầu của người dùng (<user_query>), đối chiếu với các bảng dữ liệu (<database_tables>), các tài liệu chính sách (<context_policies>) và các mối quan hệ ngữ nghĩa (<semantic_relationships>) có sẵn trong hệ thống.
    
    Hãy xác định chính xác danh sách các context (tên bảng dữ liệu hoặc tên chính sách) BẮT BUỘC cần phải truy xuất để xử lý hoàn chỉnh yêu cầu.
    
    Quy tắc quan trọng:
    1. Xác định 'intent' phù hợp nhất với yêu cầu (ví dụ: 'refund_eligibility', 'order_lookup', 'vip_benefits', 'delivery_inquiry', 'product_inquiry', 'general_inquiry').
    2. Trích xuất 'entities' từ câu hỏi (như 'customer', 'order_id', 'product', 'tier', ...). NẾU KHÔNG CÓ THỰC THỂ ĐÓ TRONG CÂU HỎI, BẮT BUỘC ĐỂ GIÁ TRỊ LÀ null.
    3. Chỉ chọn các context thực sự cần thiết vào 'required_context'. Tên context PHẢI khớp với thuộc tính 'name' trong catalog (ví dụ: 'customers', 'orders', 'products', 'users', 'refund_policy', 'vip_policy', 'delivery_policy').
    4. Chỉ định 'fields': 
       - Đối với Database Tables: chọn danh sách các cột cần truy vấn (ví dụ: "customers": ["name", "tier"], "orders": ["id", "total_price", "status"], "products": ["name", "price"]).
       - Đối với Context Policies: chọn đúng các 'section id' cụ thể tương ứng với nội dung cần đọc trong thẻ <sections> của policy đó (ví dụ: "delivery_policy": ["free_shipping_conditions"], "refund_policy": ["tier_based_return_timing"], "vip_policy": ["tier_privileges"]). KHÔNG CẦN tải toàn bộ policy nếu chỉ cần 1 section.
    5. Trường 'reasoning' BẮT BUỘC PHẢI SIÊU NGẮN GỌN TRONG VÒNG TỐI ĐA 10 TOKENS / TỪ (ví dụ: 'Tra cứu phí ship và ưu đãi VIP').
  </system_instructions>

  <available_contexts>
{metadata_xml}
  </available_contexts>

  <user_query>
    {user_query}
  </user_query>

  <output_format>
    Bạn PHẢI trả về duy nhất một JSON object hợp lệ (không kèm markdown format ```json) theo đúng cấu trúc sau:
    {{
      "intent": "vip_benefits",
      "entities": {{
        "customer": "Tên khách hàng hoặc null",
        "order_id": "Mã đơn hàng hoặc null",
        "product": "Tên sản phẩm hoặc null",
        "tier": "Hạng thành viên hoặc null"
      }},
      "required_context": [
        "delivery_policy",
        "vip_policy"
      ],
      "fields": {{
        "delivery_policy": ["free_shipping_conditions"],
        "vip_policy": ["tier_privileges"]
      }},
      "reasoning": "Lý do siêu ngắn dưới 10 tokens"
    }}
  </output_format>
</context_planning_request>"""
        return prompt

    def plan(self, user_query: str) -> Dict[str, Any]:
        """
        Thực thi phân tích yêu cầu của người dùng và trả về dict kết quả chuẩn hóa schema:
        {
          "intent": "...",
          "entities": {"customer": ... or None, "order_id": ... or None},
          "required_context": [...],
          "fields": {"customer": ["name", "tier"], ...},
          "reasoning": "..."
        }
        Có cơ chế try-except bắt lỗi toàn diện để chống crash.
        """
        prompt = self.build_prompt_xml(user_query)
        generation_config = {
            "response_mime_type": "application/json",
            "temperature": 0.1,
        }

        candidate_models = [self.model_name] + [m for m in self.fallback_models if m != self.model_name]
        last_error = None

        for m_name in candidate_models:
            try:
                model = genai.GenerativeModel(
                    model_name=m_name,
                    generation_config=generation_config
                )
                response = model.generate_content(prompt)
                
                # Làm sạch phản hồi JSON
                raw_text = response.text.strip()
                if raw_text.startswith("```json"):
                    raw_text = raw_text[7:]
                if raw_text.startswith("```"):
                    raw_text = raw_text[3:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]
                raw_text = raw_text.strip()

                # Parse JSON an toàn
                try:
                    result = json.loads(raw_text)
                except Exception as json_err:
                    result = {
                        "intent": "general_inquiry",
                        "entities": {"customer": None, "order_id": None, "product": None, "tier": None},
                        "required_context": [],
                        "fields": {},
                        "reasoning": "Lỗi phân tích JSON"
                    }

                # Chuẩn hóa các trường đầu ra để chống crash
                try:
                    # 1. intent
                    if not isinstance(result.get("intent"), str):
                        result["intent"] = "general_inquiry"

                    # 2. entities
                    if not isinstance(result.get("entities"), dict):
                        result["entities"] = {}
                    
                    # Đảm bảo các trường phổ biến có giá trị None nếu không có
                    standard_keys = ["customer", "order_id", "product", "tier"]
                    for k in standard_keys:
                        if k not in result["entities"] or result["entities"][k] in ["null", "None", "", None]:
                            result["entities"][k] = None

                    # 3. required_context
                    if not isinstance(result.get("required_context"), list):
                        result["required_context"] = []

                    # 4. fields
                    if not isinstance(result.get("fields"), dict):
                        result["fields"] = {}

                    # 5. reasoning (giới hạn <= 10 tokens/từ)
                    if "reasoning" in result and isinstance(result["reasoning"], str):
                        words = result["reasoning"].strip().split()
                        if len(words) > 10:
                            result["reasoning"] = " ".join(words[:10])
                    else:
                        result["reasoning"] = None

                except Exception as format_err:
                    result.setdefault("intent", "general_inquiry")
                    result.setdefault("entities", {"customer": None, "order_id": None, "product": None, "tier": None})
                    result.setdefault("required_context", [])
                    result.setdefault("fields", {})
                    result.setdefault("reasoning", None)

                return result

            except Exception as e:
                last_error = e
                continue

        # Fallback an toàn nếu toàn bộ API gặp lỗi
        return {
            "intent": "general_inquiry",
            "entities": {
                "customer": None,
                "order_id": None,
                "product": None,
                "tier": None
            },
            "required_context": ["customers", "orders"],
            "fields": {
                "customers": ["name", "tier"],
                "orders": ["id", "total_price", "status"]
            },
            "reasoning": "Lỗi kết nối API",
            "error": str(last_error)
        }


def plan_context(user_query: str, **kwargs) -> Dict[str, Any]:
    """Hàm helper tiện lợi để gọi nhanh ContextPlanner."""
    planner = ContextPlanner(**kwargs)
    return planner.plan(user_query)


if __name__ == "__main__":
    test_query = "Tôi muốn kiểm tra chính sách hoàn tiền cho đơn hàng của khách hàng VIP"
    print(f"User Query: {test_query}\n")
    
    planner = ContextPlanner()
    print("--- XML PROMPT ĐƯỢC SINH RA ---")
    print(planner.build_prompt_xml(test_query)[:500] + "\n... [truncated] ...\n")
    
    print("--- KẾT QUẢ TỪ GEMINI ---")
    plan_result = planner.plan(test_query)
    print(json.dumps(plan_result, indent=2, ensure_ascii=False))
