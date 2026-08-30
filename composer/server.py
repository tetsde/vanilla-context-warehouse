"""
FastAPI Server for Context Warehouse Composer & Interactive Frontend.
Provides REST APIs for:
- Pipeline execution with full 7-step Checkpoint logging
- Catalog inspection (tables, policies, semantic graph)
- Health and configuration status
- Static file serving for modern interactive web UI
"""

import os
import sys
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Thêm thư mục gốc vào sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from database import Database
from composer.composer import ContextComposer
from composer.catalog import CatalogContextLoader

app = FastAPI(
    title="Context Warehouse Composer API",
    description="Interactive Context Warehouse Pipeline with Checkpoint Telemetry",
    version="1.0.0"
)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Khởi tạo các module
db_path = os.path.join(parent_dir, "warehouse.db")
context_dir = os.path.join(parent_dir, "context")
static_dir = os.path.join(current_dir, "static")

os.makedirs(static_dir, exist_ok=True)

# Khởi tạo composer & database
composer_instance: Optional[ContextComposer] = None
try:
    composer_instance = ContextComposer(db_path=db_path, context_dir=context_dir)
except Exception as e:
    print(f"[WARNING] Không thể khởi tạo ContextComposer ngay lập tức: {e}")

db_instance = Database(db_path=db_path)
catalog_loader = CatalogContextLoader(db_path=db_path, context_dir=context_dir)


class PipelineRequest(BaseModel):
    query: str
    model_name: Optional[str] = None


@app.get("/api/health")
def get_health() -> Dict[str, Any]:
    """Kiểm tra tình trạng hoạt động của hệ thống."""
    has_api_key = bool(os.getenv("GEMINI_API_KEY"))
    db_exists = os.path.exists(db_path)
    
    table_counts = {}
    if db_exists:
        try:
            for tbl in ["customers", "orders", "products", "users", "catalog", "context_relationships"]:
                res = db_instance.fetch_all(f"SELECT COUNT(*) as cnt FROM {tbl}")
                table_counts[tbl] = res[0]["cnt"] if res else 0
        except Exception:
            pass

    policy_files = []
    if os.path.exists(context_dir):
        policy_files = [f for f in os.listdir(context_dir) if f.endswith(".md")]

    return {
        "status": "healthy",
        "gemini_configured": has_api_key,
        "database_connected": db_exists,
        "table_row_counts": table_counts,
        "policy_files_count": len(policy_files),
        "policy_files": policy_files
    }


@app.get("/api/catalog")
def get_catalog() -> Dict[str, Any]:
    """Trả về chi tiết toàn bộ kho ngữ cảnh (Tables, Policies, Semantic Relationships)."""
    try:
        catalog_entries = db_instance.list_catalog()
        relationships = db_instance.list_context_relationships()

        # Chi tiết các bảng dữ liệu kèm mẫu bản ghi
        tables_data = []
        for entry in catalog_entries:
            if entry.get("type") == "table":
                tbl_name = entry["name"]
                schema_cols = db_instance.fetch_all(f"PRAGMA table_info({tbl_name})")
                sample_rows = db_instance.fetch_all(f"SELECT * FROM {tbl_name} LIMIT 5")
                tables_data.append({
                    "name": tbl_name,
                    "description": entry.get("description", ""),
                    "columns": [c["name"] for c in schema_cols],
                    "sample_records": sample_rows
                })

        # Chi tiết các chính sách Markdown
        policies_data = []
        if os.path.exists(context_dir):
            for fname in os.listdir(context_dir):
                if fname.endswith(".md"):
                    p_path = os.path.join(context_dir, fname)
                    with open(p_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    
                    policies_data.append({
                        "filename": fname,
                        "name": fname.replace(".md", ""),
                        "raw_content": content,
                        "char_count": len(content),
                        "lines_count": len(content.splitlines())
                    })

        return {
            "tables": tables_data,
            "policies": policies_data,
            "relationships": relationships
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/pipeline/run")
def run_pipeline(req: PipelineRequest) -> Dict[str, Any]:
    """Thực thi chu trình Context Warehouse và trả về kết quả kèm 7 Checkpoint logs."""
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Câu hỏi (query) không được để trống.")

    global composer_instance
    if composer_instance is None:
        try:
            composer_instance = ContextComposer(
                model_name=req.model_name or "gemini-2.5-flash",
                db_path=db_path,
                context_dir=context_dir
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Không thể khởi tạo Composer: {str(e)}")

    if req.model_name and req.model_name != composer_instance.model_name:
        composer_instance.model_name = req.model_name

    try:
        result = composer_instance.answer(query)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi thực thi pipeline: {str(e)}")


# Serve frontend static assets
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def serve_index() -> FileResponse:
    """Trả về file index.html của frontend."""
    index_path = os.path.join(static_dir, "index.html")
    if not os.path.exists(index_path):
        return JSONResponse({"message": "Frontend chưa được khởi tạo. Đang tải static files..."})
    return FileResponse(index_path)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("composer.server:app", host="127.0.0.1", port=8000, reload=True)
