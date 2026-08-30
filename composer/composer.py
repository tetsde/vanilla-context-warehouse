"""
Context Composer Module with Full Checkpoint Logging.
Orchestrates the full pipeline:
1. Init & Catalog Snapshot (Checkpoint 1)
2. Planner: Identifies required contexts (tables & policies) based on user query (Checkpoint 2)
3. Retriever: Fetches actual content (markdown policies and database records) (Checkpoint 3)
4. Validator: Quality and completeness audit (Checkpoint 4)
5. Package: Clean schema dictionary and formatted LLM block (Checkpoint 5)
6. Synthesizer: Generates an accurate, context-aware answer using Gemini (Checkpoint 6)
7. Telemetry & Summary: Execution metrics and latency breakdown (Checkpoint 7)
"""

import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

import dotenv
import google.generativeai as genai

# Thêm thư mục gốc vào path để import
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from composer.planner import ContextPlanner
from composer.retriever import ContextRetriever
from composer.package import ContextPackage
from composer.tracer import PipelineTracer

from ultis.validator import ContextCompletenessValidator
from database import Database


class ContextComposer:
    """Điều phối toàn bộ quy trình từ lập kế hoạch context, truy xuất tài nguyên, đóng gói ContextPackage đến tổng hợp câu trả lời."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-2.5-flash-lite",
        fallback_models: Optional[List[str]] = None,
        db_path: Optional[str] = None,
        context_dir: Optional[str] = None
    ) -> None:
        dotenv_path = os.path.join(parent_dir, ".env")
        if os.path.exists(dotenv_path):
            dotenv.load_dotenv(dotenv_path)
        else:
            dotenv.load_dotenv()

        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("Không tìm thấy GEMINI_API_KEY trong .env")

        genai.configure(api_key=self.api_key)
        self.model_name = model_name
        self.fallback_models = fallback_models or [
            "gemini-2.5-flash",
            "gemini-flash-latest",
            "gemini-flash-lite-latest",
            "gemini-2.5-pro"
        ]

        self.db_path = db_path or os.path.join(parent_dir, "warehouse.db")
        self.context_dir = context_dir or os.path.join(parent_dir, "context")

        self.planner = ContextPlanner(
            api_key=self.api_key,
            model_name=self.model_name,
            fallback_models=self.fallback_models,
            db_path=self.db_path,
            context_dir=self.context_dir
        )
        self.retriever = ContextRetriever(db_path=self.db_path, context_dir=self.context_dir)
        self.validator = ContextCompletenessValidator(db_path=self.db_path)
        self.db = Database(db_path=self.db_path)

    def answer(self, user_query: str, tracer: Optional[PipelineTracer] = None) -> Dict[str, Any]:
        """
        Thực hiện chu trình hoàn chỉnh kèm 7 Checkpoints theo dõi trực quan:
        1. Init -> 2. Planner -> 3. Retriever -> 4. Validator -> 5. Package -> 6. Synthesizer -> 7. Telemetry.
        """
        tracer = tracer or PipelineTracer(query=user_query)

        # =========================================================================
        # CHECKPOINT 1: Khởi tạo yêu cầu & Snapshot Catalog Metadata
        # =========================================================================
        tracer.start_step_timer()
        try:
            catalog_entries = self.db.list_catalog()
            relationships = self.db.list_context_relationships()
            tables = [c["name"] for c in catalog_entries if c.get("type") == "table"]
            policies = [c["name"] for c in catalog_entries if c.get("type") == "policy"]

            tracer.record_checkpoint(
                step=1,
                id="cp1_init",
                name="Khởi Tạo Yêu Cầu & Snapshot Catalog",
                description="Tiếp nhận câu hỏi người dùng và thu thập snapshot metadata bảng dữ liệu, chính sách, quan hệ ngữ nghĩa.",
                status="success",
                payload={
                    "query": user_query,
                    "available_tables": tables,
                    "available_policies": policies,
                    "relationships_count": len(relationships),
                    "database_path": self.db_path,
                    "context_directory": self.context_dir
                }
            )
        except Exception as e:
            tracer.record_checkpoint(
                step=1,
                id="cp1_init",
                name="Khởi Tạo Yêu Cầu & Snapshot Catalog",
                description="Lỗi khi đọc snapshot catalog",
                status="warning",
                payload={"error": str(e), "query": user_query}
            )

        # =========================================================================
        # CHECKPOINT 2: Context Planner (Gemini)
        # =========================================================================
        tracer.start_step_timer()
        xml_prompt = self.planner.build_prompt_xml(user_query)
        plan_result = self.planner.plan(user_query)

        required_context = plan_result.get("required_context", [])
        intent = plan_result.get("intent", "general_inquiry")
        entities = plan_result.get("entities", {})
        fields = plan_result.get("fields", {})
        reasoning = plan_result.get("reasoning", "")
        planner_error = plan_result.get("error")

        tracer.record_checkpoint(
            step=2,
            id="cp2_planner",
            name="Context Planner (AI Planning)",
            description="Phân tích câu hỏi với Gemini để xác định Intent, trích xuất Thực thể, Context bắt buộc và Section/Field cần lấy.",
            status="error" if planner_error else "success",
            payload={
                "intent": intent,
                "entities": entities,
                "required_context": required_context,
                "fields": fields,
                "reasoning": reasoning,
                "prompt_xml": xml_prompt,
                "raw_plan": plan_result,
                "model_used": plan_result.get("model_used", self.model_name)
            }
        )

        # =========================================================================
        # CHECKPOINT 3: Context Retriever
        # =========================================================================
        tracer.start_step_timer()
        retrieved_context = self.retriever.retrieve(plan_result)

        retrieval_summary = []
        for item in retrieved_context:
            retrieval_summary.append({
                "context": item.get("context"),
                "source_doc": item.get("source_doc"),
                "section": item.get("section"),
                "data_preview": str(item.get("data"))[:150] + "..." if len(str(item.get("data"))) > 150 else item.get("data")
            })

        tracer.record_checkpoint(
            step=3,
            id="cp3_retriever",
            name="Context Retriever (Truy Xuất Tài Nguyên)",
            description="Truy vấn dữ liệu thực tế: chạy SQL trên SQLite DB và cắt lọc section-level từ Markdown policies.",
            status="success" if retrieved_context else "warning",
            payload={
                "items_retrieved_count": len(retrieved_context),
                "items": retrieved_context,
                "summary": retrieval_summary
            }
        )

        # =========================================================================
        # CHECKPOINT 4: Quality & Completeness Validator
        # =========================================================================
        tracer.start_step_timer()
        validation_report = self.validator.audit(
            query=user_query,
            plan=plan_result,
            retrieved_context=retrieved_context
        )

        val_status = "success"
        if validation_report.get("status") in ["INCOMPLETE", "POOR"]:
            val_status = "error"
        elif validation_report.get("warnings") or not validation_report.get("is_complete"):
            val_status = "warning"

        tracer.record_checkpoint(
            step=4,
            id="cp4_validator",
            name="Completeness Validator (Kiểm Định Toàn Vẹn)",
            description="Kiểm tra tính nhất quán ngữ nghĩa, đối soát thực thể, tính điểm Completeness Score và đưa ra khuyến nghị.",
            status=val_status,
            payload=validation_report
        )

        # =========================================================================
        # CHECKPOINT 5: Context Package & Cleaning
        # =========================================================================
        tracer.start_step_timer()
        package = ContextPackage(
            plan=plan_result,
            retrieved_context=retrieved_context,
            query=user_query,
            validator=self.validator
        )
        clean_context_schema = package.get_clean_data()
        formatted_context_text = package.format_for_llm()

        tracer.record_checkpoint(
            step=5,
            id="cp5_package",
            name="Context Package (Đóng Gói & Làm Sạch)",
            description="Làm sạch dữ liệu, loại bỏ trường thừa, chuẩn hóa khóa và sinh Text Blocks chuẩn (=== SECTION ===) cho LLM.",
            status="success",
            payload={
                "clean_schema": clean_context_schema,
                "formatted_text_prompt": formatted_context_text
            }
        )

        # =========================================================================
        # CHECKPOINT 6: Response Synthesizer (Gemini)
        # =========================================================================
        tracer.start_step_timer()
        system_prompt = f"""<synthesis_request>
  <instructions>
    Bạn là trợ lý AI thông minh của hệ thống Context Warehouse.
    Dưới đây là các tài liệu chính sách và dữ liệu database đã được hệ thống tự động truy xuất và đóng gói vào Context Package sạch.
    
    Hãy dựa CHÍNH XÁC vào các thông tin trong <context_package> để trả lời câu hỏi của người dùng một cách đầy đủ, chính xác, lịch sự và chuyên nghiệp.
    Nếu có thông tin khách hàng, đơn hàng cụ thể, hãy đối chiếu chính xác với các điều kiện trong chính sách để giải đáp cho người dùng.
  </instructions>

<context_package>
{formatted_context_text}
</context_package>

  <user_query>
    {user_query}
  </user_query>
</synthesis_request>"""

        candidate_models = [self.model_name] + [m for m in self.fallback_models if m != self.model_name]
        final_answer = ""
        used_model = self.model_name
        synthesis_error = None

        for m_name in candidate_models:
            try:
                model = genai.GenerativeModel(model_name=m_name)
                response = model.generate_content(system_prompt)
                final_answer = response.text
                used_model = m_name
                break
            except Exception as e:
                synthesis_error = str(e)
                continue

        if not final_answer:
            final_answer = f"⚠️ Không thể kết nối với mô hình AI để tổng hợp câu trả lời. Chi tiết lỗi: {synthesis_error}"

        tracer.record_checkpoint(
            step=6,
            id="cp6_synthesizer",
            name="Response Synthesizer (Tổng Hợp Câu Trả Lời)",
            description="Gemini AI tổng hợp câu trả lời cuối cùng dựa trên Context Package sạch và câu hỏi của người dùng.",
            status="error" if synthesis_error and not final_answer else "success",
            payload={
                "system_prompt": system_prompt,
                "answer": final_answer,
                "model_used": used_model
            }
        )

        # =========================================================================
        # CHECKPOINT 7: Pipeline Telemetry & Summary
        # =========================================================================
        summary = tracer.get_summary()
        tracer.record_checkpoint(
            step=7,
            id="cp7_telemetry",
            name="Pipeline Telemetry & Tổng Kết",
            description="Tổng hợp thời gian thực thi, hiệu suất từng chặng và trạng thái tổng quan của toàn bộ chu trình.",
            status=summary["overall_status"],
            payload={
                "total_duration_ms": summary["total_duration_ms"],
                "overall_status": summary["overall_status"],
                "step_timings": [
                    {"step": cp["step"], "name": cp["name"], "duration_ms": cp["duration_ms"]}
                    for cp in summary["checkpoints"]
                ]
            }
        )

        # Cập nhật lại summary sau khi đã ghi checkpoint 7
        final_summary = tracer.get_summary()

        return {
            "query": user_query,
            "intent": intent,
            "entities": entities,
            "required_context": required_context,
            "reasoning": reasoning,
            "retrieved_context": retrieved_context,
            "context_package": clean_context_schema,
            "context_package_text": formatted_context_text,
            "validation_report": validation_report,
            "answer": final_answer,
            "model_used": used_model,
            "checkpoints": final_summary["checkpoints"],
            "total_duration_ms": final_summary["total_duration_ms"],
            "overall_status": final_summary["overall_status"]
        }


def compose(user_query: str, **kwargs) -> Dict[str, Any]:
    """Hàm helper tiện lợi để gọi nhanh ContextComposer."""
    composer = ContextComposer(**kwargs)
    return composer.answer(user_query)
