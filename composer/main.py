"""
Main Entrypoint for Context Warehouse Composer.
Demonstrates end-to-end execution:
User Query -> Context Planner (Gemini) -> Context Retriever -> Response Composer
"""

import json
import os
import sys

# Thêm thư mục gốc vào path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from composer.composer import ContextComposer


def run_demo():
    print("=" * 80)
    print("       CONTEXT WAREHOUSE COMPOSER - DEMO PLANNER & RETRIEVER & SYNTHESIS")
    print("=" * 80)

    composer = ContextComposer()

    test_queries = [
        "Khách hàng hạng Platinum được đổi trả hàng trong bao lâu và có mất phí không?",
        "Kiểm tra danh sách đơn hàng của khách hàng Nguyễn Văn An và các sản phẩm đã mua?",
        "Chính sách giao hàng hỏa tốc 2 giờ có miễn phí cho khách hàng Gold và Platinum không?",
    ]

    for idx, query in enumerate(test_queries, 1):
        print(f"\n[{idx}] USER QUERY: {query}")
        print("-" * 80)
        
        result = composer.answer(query)
        
        print("🔍 [BƯỚC 1 - CONTEXT PLANNER (GEMINI)]:")
        print(f"  • Intent:           {result.get('intent', 'N/A')}")
        print(f"  • Entities:         {json.dumps(result.get('entities', {}), ensure_ascii=False)}")
        print(f"  • Required Context: {json.dumps(result['required_context'], ensure_ascii=False)}")
        print(f"  • Reasoning:        {result.get('reasoning', 'N/A')}")
        print(f"  • Model Used:       {result.get('model_used', 'N/A')}")

        print("\n📥 [BƯỚC 2 - CONTEXT RETRIEVER]:")
        retrieved = result["retrieved_context"]
        print(f"  • Retrieved Context Items: {len(retrieved)}")
        for item in retrieved:
            ctx_name = item.get("context")
            source_doc = item.get("source_doc", "N/A")
            section = item.get("section", "all")
            data = item.get("data")
            if isinstance(data, str):
                summary = data.split('\n')[0][:60] + "..." if len(data) > 60 else data
                print(f"    - [{ctx_name}] ({source_doc} -> section: {section}): {summary}")
            elif isinstance(data, dict):
                print(f"    - [{ctx_name}] ({source_doc} -> fields: {section}): {json.dumps(data, ensure_ascii=False)}")
            elif isinstance(data, list):
                print(f"    - [{ctx_name}] ({source_doc}): {len(data)} records")

        print("\n📦 [BƯỚC 3 - CONTEXT PACKAGE (VALIDATION & CLEANING)]:")
        report = result.get("validation_report", {})
        print(f"  • Completeness Score: {report.get('completeness_score', 0) * 100:.0f}% ({report.get('status', 'N/A')})")
        print(f"  • Is Complete:        {'✅ Đầy đủ' if report.get('is_complete') else '⚠️ Có thiếu sót'}")
        if report.get("warnings"):
            print("  • Cảnh báo thiếu sót:")
            for w in report["warnings"]:
                print(f"    - ⚠️ {w}")
        if report.get("recommendations"):
            print("  • Khuyến nghị bổ sung:")
            for r in report["recommendations"]:
                print(f"    - 💡 {r}")

        print("\n  ✨ Clean Schema (Dict):")
        print("  " + json.dumps(result.get("context_package", {}), indent=4, ensure_ascii=False).replace("\n", "\n  "))

        print("\n  📄 Formatted for LLM Prompt:")
        for line in result.get("context_package_text", "").split("\n"):
            print(f"    {line}")

        print("\n🤖 [BƯỚC 4 - SYNTHESIZED ANSWER]:")
        print(result["answer"].strip())
        print("=" * 80)


if __name__ == "__main__":
    run_demo()
