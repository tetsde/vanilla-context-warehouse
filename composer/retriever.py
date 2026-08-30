"""
Context Retriever Module with Section-Level Chunking.
Directly queries and fetches context data based on the planner's output:
- Identifies whether a context is a database table or a policy document.
- Queries SQLite database (warehouse.db) for table records, filtering by extracted entities and columns.
- Reads and extracts specific SECTIONS from Markdown files in context/ directory.
- Attaches the source document address and section name to each retrieved item.
- Returns a structured list:
  [
    {
      "context": "delivery_policy",
      "source_doc": "delivery_policy.md",
      "section": "free_shipping_conditions",
      "data": "## 2. Chính Sách Miễn Phí Vận Chuyển...\n"
    },
    {
      "context": "customer",
      "source_doc": "SQLite/warehouse.db (table: customers)",
      "section": ["name", "tier"],
      "data": {"name": "Nguyễn Văn An", "tier": "platinum"}
    }
  ]
"""

import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

# Thêm thư mục gốc vào path để import database.py và catalog.py
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from database import Database
from composer.catalog import parse_markdown_into_sections


class ContextRetriever:
    """Truy vấn và lấy dữ liệu context theo cấp độ Section từ database hoặc thư mục context/."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        context_dir: Optional[str] = None
    ) -> None:
        if db_path is None:
            self.db_path = os.path.join(parent_dir, "warehouse.db")
        else:
            self.db_path = db_path

        if context_dir is None:
            self.context_dir = os.path.join(parent_dir, "context")
        else:
            self.context_dir = context_dir

        self.db = Database(db_path=self.db_path)

    def _normalize_table_name(self, context_name: str) -> Optional[str]:
        """Chuẩn hóa tên context thành tên bảng trong SQLite (singular/plural)."""
        mapping = {
            "customer": "customers",
            "customers": "customers",
            "order": "orders",
            "orders": "orders",
            "product": "products",
            "products": "products",
            "user": "users",
            "users": "users",
            "catalog": "catalog",
            "context_relationship": "context_relationships",
            "context_relationships": "context_relationships",
        }
        return mapping.get(context_name.lower().strip())

    def _is_policy_context(self, context_name: str) -> bool:
        """Kiểm tra xem context có phải là tệp chính sách (policy document) hay không."""
        name = context_name.lower().strip()
        if "policy" in name:
            return True
        file_path = os.path.join(self.context_dir, f"{name}.md")
        return os.path.exists(file_path)

    def retrieve_policy_sections(
        self,
        policy_name: str,
        target_sections: Optional[List[str]] = None
    ) -> Tuple[Optional[str], str, Union[str, List[str]]]:
        """
        Đọc và trích xuất các section cụ thể từ file markdown chính sách.
        Trả về tuple: (nội dung data, tên file nguồn source_doc, tên/id section).
        """
        name = policy_name.strip()
        entry = self.db.get_catalog_entry(name)
        file_name = (entry.get("source") if entry else None) or f"{name}.md"
        if not file_name.endswith(".md"):
            file_name += ".md"

        file_path = os.path.join(self.context_dir, file_name)
        if not os.path.exists(file_path):
            alt_path = os.path.join(self.context_dir, f"{name}.md")
            if os.path.exists(alt_path):
                file_path = alt_path
                file_name = f"{name}.md"
            else:
                return None, file_name, "not_found"

        try:
            sections = parse_markdown_into_sections(file_path)
            
            # Nếu không yêu cầu section cụ thể hoặc yêu cầu "all" / "content"
            if not target_sections or any(s in ["all", "*", "content"] for s in target_sections):
                with open(file_path, "r", encoding="utf-8") as f:
                    return f.read().strip(), file_name, "all"

            # Tìm kiếm các section khớp theo section_id hoặc title
            matched_contents = []
            matched_ids = []

            for sec in sections:
                sec_id = sec["section_id"].lower()
                sec_title = sec["title"].lower()
                
                for t in target_sections:
                    t_lower = t.lower().strip()
                    if t_lower == sec_id or t_lower in sec_id or t_lower in sec_title:
                        matched_contents.append(sec["content"])
                        matched_ids.append(sec["section_id"])
                        break

            if matched_contents:
                combined_data = "\n\n".join(matched_contents)
                section_label = matched_ids[0] if len(matched_ids) == 1 else matched_ids
                return combined_data, file_name, section_label
            else:
                # Nếu không khớp section cụ thể nào, fallback trả về toàn bộ file
                with open(file_path, "r", encoding="utf-8") as f:
                    return f.read().strip(), file_name, "full_document_fallback"

        except Exception as e:
            return f"Lỗi đọc tài liệu chính sách {policy_name}: {e}", file_name, "error"

    def retrieve_customer_data(self, customer_name: Optional[str] = None) -> Union[Dict[str, Any], List[Dict[str, Any]], None]:
        """Truy vấn thông tin khách hàng từ bảng customers."""
        try:
            if customer_name:
                query = "SELECT * FROM customers WHERE name LIKE ? LIMIT 1;"
                row = self.db.fetch_one(query, (f"%{customer_name.strip()}%",))
                if row:
                    return {
                        "id": row["id"],
                        "name": row["name"],
                        "tier": row["tier"],
                        "phone": row["phone"],
                        "address": row["address"]
                    }

            row = self.db.fetch_one("SELECT * FROM customers ORDER BY id ASC LIMIT 1;")
            if row:
                return {
                    "id": row["id"],
                    "name": row["name"],
                    "tier": row["tier"],
                    "phone": row["phone"],
                    "address": row["address"]
                }
            return None
        except Exception as e:
            return {"error": f"Lỗi truy vấn customers: {e}"}

    def retrieve_order_data(
        self,
        order_id: Optional[Union[int, str]] = None,
        customer_name: Optional[str] = None
    ) -> Union[Dict[str, Any], List[Dict[str, Any]], None]:
        """Truy vấn thông tin đơn hàng từ bảng orders."""
        try:
            if order_id:
                try:
                    clean_id = int(str(order_id).replace("#", "").strip())
                    query = "SELECT * FROM orders WHERE id = ? LIMIT 1;"
                    row = self.db.fetch_one(query, (clean_id,))
                    if row:
                        return {
                            "id": row["id"],
                            "customer_id": row["customer_id"],
                            "product_id": row["product_id"],
                            "quantity": row["quantity"],
                            "amount": row["total_price"],
                            "total_price": row["total_price"],
                            "status": row["status"],
                            "order_date": row["order_date"]
                        }
                except ValueError:
                    pass

            if customer_name:
                query = """
                    SELECT o.*, c.name as customer_name
                    FROM orders o
                    JOIN customers c ON o.customer_id = c.id
                    WHERE c.name LIKE ?
                    ORDER BY o.id DESC
                    LIMIT 1;
                """
                row = self.db.fetch_one(query, (f"%{customer_name.strip()}%",))
                if row:
                    return {
                        "id": row["id"],
                        "customer_name": row["customer_name"],
                        "product_id": row["product_id"],
                        "quantity": row["quantity"],
                        "amount": row["total_price"],
                        "total_price": row["total_price"],
                        "status": row["status"],
                        "order_date": row["order_date"]
                    }

            row = self.db.fetch_one("SELECT * FROM orders ORDER BY id DESC LIMIT 1;")
            if row:
                return {
                    "id": row["id"],
                    "customer_id": row["customer_id"],
                    "product_id": row["product_id"],
                    "quantity": row["quantity"],
                    "amount": row["total_price"],
                    "total_price": row["total_price"],
                    "status": row["status"],
                    "order_date": row["order_date"]
                }
            return None
        except Exception as e:
            return {"error": f"Lỗi truy vấn orders: {e}"}

    def retrieve_product_data(self, product_name: Optional[str] = None) -> Union[Dict[str, Any], List[Dict[str, Any]], None]:
        """Truy vấn thông tin sản phẩm từ bảng products."""
        try:
            if product_name:
                query = "SELECT * FROM products WHERE name LIKE ? LIMIT 1;"
                row = self.db.fetch_one(query, (f"%{product_name.strip()}%",))
                if row:
                    return {
                        "id": row["id"],
                        "name": row["name"],
                        "price": row["price"],
                        "category": row["category"],
                        "stock": row["stock"]
                    }

            row = self.db.fetch_one("SELECT * FROM products ORDER BY id ASC LIMIT 1;")
            if row:
                return {
                    "id": row["id"],
                    "name": row["name"],
                    "price": row["price"],
                    "category": row["category"],
                    "stock": row["stock"]
                }
            return None
        except Exception as e:
            return {"error": f"Lỗi truy vấn products: {e}"}

    def retrieve_user_data(self, username_or_email: Optional[str] = None) -> Union[Dict[str, Any], None]:
        """Truy vấn thông tin tài khoản từ bảng users."""
        try:
            if username_or_email:
                query = "SELECT id, username, email, role, is_active, created_at FROM users WHERE username LIKE ? OR email LIKE ? LIMIT 1;"
                row = self.db.fetch_one(query, (f"%{username_or_email.strip()}%", f"%{username_or_email.strip()}%"))
                if row:
                    return dict(row)

            row = self.db.fetch_one("SELECT id, username, email, role, is_active, created_at FROM users LIMIT 1;")
            return dict(row) if row else None
        except Exception as e:
            return {"error": f"Lỗi truy vấn users: {e}"}

    def _filter_fields(self, data: Any, target_fields: Optional[List[str]]) -> Any:
        """Lọc các trường dữ liệu theo danh sách fields được yêu cầu bởi Planner."""
        if not target_fields or not isinstance(data, dict):
            return data
        if "all" in target_fields or "*" in target_fields:
            return data
        
        filtered = {}
        for f in target_fields:
            if f in data:
                filtered[f] = data[f]
            elif f == "amount" and "total_price" in data:
                filtered["amount"] = data["total_price"]
            elif f == "total_price" and "amount" in data:
                filtered["total_price"] = data["amount"]
        return filtered if filtered else data

    def retrieve_context(
        self,
        context_name: str,
        entities: Optional[Dict[str, Any]] = None,
        target_fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Truy vấn 1 context đơn lẻ và trả về dict dạng:
        {
          "context": context_name,
          "source_doc": "delivery_policy.md" / "table: customers",
          "section": "free_shipping_conditions" / ["name", "tier"],
          "data": ...
        }
        """
        entities = entities or {}
        c_name = context_name.strip()

        # 1. Kiểm tra nếu là Policy (trong context folder)
        if self._is_policy_context(c_name):
            data, source_doc, section_id = self.retrieve_policy_sections(c_name, target_sections=target_fields)
            return {
                "context": c_name,
                "source_doc": source_doc,
                "section": section_id,
                "data": data or f"Không tìm thấy tài liệu chính sách '{c_name}'"
            }

        # 2. Kiểm tra nếu là Table trong Database
        table_name = self._normalize_table_name(c_name)
        source_doc = f"SQLite/warehouse.db (table: {table_name or c_name})"

        if table_name == "customers":
            data = self.retrieve_customer_data(customer_name=entities.get("customer"))
            data = self._filter_fields(data, target_fields)
            return {
                "context": c_name,
                "source_doc": source_doc,
                "section": target_fields or ["all"],
                "data": data or {}
            }

        elif table_name == "orders":
            data = self.retrieve_order_data(
                order_id=entities.get("order_id"),
                customer_name=entities.get("customer")
            )
            data = self._filter_fields(data, target_fields)
            return {
                "context": c_name,
                "source_doc": source_doc,
                "section": target_fields or ["all"],
                "data": data or {}
            }

        elif table_name == "products":
            data = self.retrieve_product_data(product_name=entities.get("product"))
            data = self._filter_fields(data, target_fields)
            return {
                "context": c_name,
                "source_doc": source_doc,
                "section": target_fields or ["all"],
                "data": data or {}
            }

        elif table_name == "users":
            data = self.retrieve_user_data(username_or_email=entities.get("customer"))
            data = self._filter_fields(data, target_fields)
            return {
                "context": c_name,
                "source_doc": source_doc,
                "section": target_fields or ["all"],
                "data": data or {}
            }

        # 3. Fallback: Thử truy vấn bảng bất kỳ hoặc file policy
        try:
            generic_rows = self.db.fetch_all(f"SELECT * FROM {c_name} LIMIT 3;")
            if generic_rows:
                return {
                    "context": c_name,
                    "source_doc": source_doc,
                    "section": ["all"],
                    "data": [dict(r) for r in generic_rows]
                }
        except Exception:
            pass

        data, source_doc, section_id = self.retrieve_policy_sections(c_name, target_sections=target_fields)
        if data:
            return {
                "context": c_name,
                "source_doc": source_doc,
                "section": section_id,
                "data": data
            }

        return {
            "context": c_name,
            "source_doc": "unknown",
            "section": "none",
            "data": None
        }

    def retrieve(
        self,
        plan: Union[Dict[str, Any], List[str]],
        entities: Optional[Dict[str, Any]] = None,
        fields: Optional[Dict[str, List[str]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Nhận vào kế hoạch (từ Planner hoặc danh sách context) và thực hiện truy xuất.
        Lọc đúng các fields/sections được yêu cầu.
        """
        if isinstance(plan, dict):
            required_contexts = plan.get("required_context", [])
            extracted_entities = entities or plan.get("entities", {})
            extracted_fields = fields or plan.get("fields", {})
        else:
            required_contexts = plan
            extracted_entities = entities or {}
            extracted_fields = fields or {}

        retrieved_context: List[Dict[str, Any]] = []

        for ctx in required_contexts:
            target_f = extracted_fields.get(ctx) or extracted_fields.get(self._normalize_table_name(ctx) or "")
            item = self.retrieve_context(
                ctx,
                entities=extracted_entities,
                target_fields=target_f
            )
            retrieved_context.append(item)

        return retrieved_context


def retrieve_contexts(
    plan: Union[Dict[str, Any], List[str]],
    entities: Optional[Dict[str, Any]] = None,
    fields: Optional[Dict[str, List[str]]] = None,
    **kwargs
) -> List[Dict[str, Any]]:
    """Hàm helper tiện lợi để gọi nhanh ContextRetriever."""
    retriever = ContextRetriever(**kwargs)
    return retriever.retrieve(plan=plan, entities=entities, fields=fields)


if __name__ == "__main__":
    retriever = ContextRetriever()

    # Test lấy 1 section cụ thể từ delivery_policy
    test_plan = {
        "intent": "vip_benefits",
        "entities": {"customer": None, "tier": "Gold"},
        "required_context": ["delivery_policy", "customers"],
        "fields": {
            "delivery_policy": ["free_shipping_conditions"],
            "customers": ["name", "tier"]
        }
    }

    results = retriever.retrieve(test_plan)
    print("=== TEST RETRIEVER SECTION-LEVEL ===")
    print(json.dumps(results, indent=2, ensure_ascii=False))
