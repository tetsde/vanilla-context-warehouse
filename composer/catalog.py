"""
Catalog Context Loader & XML Formatter.
Loads metadata from SQLite database (catalog, context_relationships tables)
and parses markdown context files (context/*.md) into structured sections with descriptions.
"""

import os
import re
import sys
from typing import Any, Dict, List, Optional

# Thêm thư mục gốc vào path để import database.py
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from database import Database


def parse_markdown_into_sections(file_path: str) -> List[Dict[str, Any]]:
    """
    Phân tách tệp markdown thành danh sách các section độc lập.
    Tự động đọc `{#section_id}` từ heading và `<!-- description: ... -->` từ nội dung markdown.
    """
    if not os.path.exists(file_path):
        return []

    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()

    lines = text.split("\n")
    sections: List[Dict[str, Any]] = []
    current_raw_title = ""
    current_content: List[str] = []

    def _process_section(raw_title: str, content_lines: List[str]) -> Optional[Dict[str, Any]]:
        if not raw_title:
            return None

        # 1. Trích xuất section_id từ {#id_name} trong heading (hoặc tự sinh fallback)
        id_match = re.search(r'\{#([a-zA-Z0-9_-]+)\}', raw_title)
        if id_match:
            section_id = id_match.group(1).strip()
            clean_title = re.sub(r'\{#([a-zA-Z0-9_-]+)\}', '', raw_title).strip()
        else:
            clean_title = raw_title.strip()
            slug = re.sub(r'^[0-9\.\s]+', '', clean_title)
            slug = re.sub(r'[^\w\s-]', '', slug).strip().lower()
            section_id = re.sub(r'[-\s]+', '_', slug) or "section"

        # 2. Trích xuất description từ comment <!-- description: ... --> hoặc 2 dòng đầu
        description = ""
        filtered_lines = []
        for line in content_lines:
            desc_match = re.search(r'<!--\s*description:\s*(.*?)\s*-->', line, re.IGNORECASE)
            if desc_match:
                description = desc_match.group(1).strip()
            else:
                filtered_lines.append(line)

        section_body = "\n".join(filtered_lines).strip()
        if not description:
            # Fallback nếu không có tag description trong .md
            snippet_lines = [l.strip() for l in filtered_lines if l.strip() and not l.startswith("#")]
            description = " ".join(snippet_lines[:2])[:160] if snippet_lines else clean_title

        return {
            "section_id": section_id,
            "title": clean_title,
            "description": description,
            "content": f"## {clean_title}\n{section_body}"
        }

    for line in lines:
        if line.startswith("## "):
            if current_raw_title and current_content:
                sec = _process_section(current_raw_title, current_content)
                if sec:
                    sections.append(sec)
                current_content = []
            current_raw_title = line.replace("## ", "").strip()
        else:
            if current_raw_title:
                current_content.append(line)

    if current_raw_title and current_content:
        sec = _process_section(current_raw_title, current_content)
        if sec:
            sections.append(sec)

    return sections


class CatalogContextLoader:
    """Đọc và định dạng siêu dữ liệu từ database và thư mục context thành định dạng XML có chia section chi tiết."""

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

    def get_catalog_tables(self) -> List[Dict[str, Any]]:
        """Lấy danh sách các bảng trong catalog kèm schema cột."""
        tables = self.db.list_catalog(type_filter="table")
        
        table_columns_map = {
            "users": "id (INTEGER PK), username, email, password_hash, role, is_active",
            "customers": "id (INTEGER PK), user_id, name, phone, tier (standard/bronze/silver/gold/platinum), address",
            "products": "id (INTEGER PK), name, category, price, stock, description",
            "orders": "id (INTEGER PK), customer_id, product_id, quantity, unit_price, total_price, status, order_date",
            "catalog": "id (INTEGER PK), name, type, description, source",
            "context_relationships": "id (INTEGER PK), source_id, relation, target_id, description",
        }
        for t in tables:
            t["columns"] = table_columns_map.get(t["name"], "Không xác định")
        return tables

    def get_catalog_policies_with_sections(self) -> List[Dict[str, Any]]:
        """Lấy danh sách các chính sách kèm danh sách các section đã phân tách."""
        policies = self.db.list_catalog(type_filter="policy")
        for p in policies:
            file_name = p.get("source") or f"{p['name']}.md"
            if not file_name.endswith(".md"):
                file_name += ".md"
            file_path = os.path.join(self.context_dir, file_name)
            p["source_file"] = file_name
            p["sections"] = parse_markdown_into_sections(file_path)
        return policies

    def get_semantic_relationships(self) -> List[Dict[str, Any]]:
        """Lấy danh sách các mối quan hệ ngữ nghĩa từ context_relationships."""
        return self.db.list_context_relationships()

    def build_xml_context_metadata(self) -> str:
        """
        Xây dựng chuỗi XML chứa toàn bộ metadata dạng section-level để tiết kiệm token cho Planner.
        """
        tables = self.get_catalog_tables()
        policies = self.get_catalog_policies_with_sections()
        relationships = self.get_semantic_relationships()

        xml_parts = ["<context_warehouse_catalog>"]

        # 1. Tables Section
        xml_parts.append("  <database_tables>")
        for t in tables:
            xml_parts.append(f'    <table name="{t["name"]}" type="table" source="{t.get("source", "SQLite")}">')
            xml_parts.append(f'      <description>{t.get("description", "")}</description>')
            xml_parts.append(f'      <columns>{t.get("columns", "")}</columns>')
            xml_parts.append('    </table>')
        xml_parts.append("  </database_tables>")

        # 2. Policies Section with Granular Sub-sections
        xml_parts.append("  <context_policies>")
        for p in policies:
            xml_parts.append(f'    <policy name="{p["name"]}" type="policy" source_file="{p.get("source_file", "")}">')
            xml_parts.append(f'      <description>{p.get("description", "")}</description>')
            if p.get("sections"):
                xml_parts.append('      <sections>')
                for s in p["sections"]:
                    xml_parts.append(
                        f'        <section id="{s["section_id"]}" title="{s["title"]}">'
                        f'{s["description"]}</section>'
                    )
                xml_parts.append('      </sections>')
            xml_parts.append('    </policy>')
        xml_parts.append("  </context_policies>")

        # 3. Semantic Context Relationships
        xml_parts.append("  <semantic_relationships>")
        for r in relationships:
            xml_parts.append(
                f'    <relation source="{r["source_name"]}" type="{r["relation"]}" target="{r["target_name"]}">'
                f'{r.get("description", "")}</relation>'
            )
        xml_parts.append("  </semantic_relationships>")

        xml_parts.append("</context_warehouse_catalog>")
        return "\n".join(xml_parts)
