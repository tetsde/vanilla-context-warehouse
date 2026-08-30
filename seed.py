"""
Mock Database Seeder Script.
Populates warehouse.db with realistic, diverse mock data across all 6 tables:
- users
- customers
- products
- orders
- catalog
- context_relationships
"""

import sys
from database import Database


def main():
    print("==================================================================")
    print("              SEEDING MOCK DATABASE: warehouse.db                 ")
    print("==================================================================")

    db = Database(db_path="warehouse.db")
    db.init_db()

    print("[1/5] Khởi tạo bảng và nạp Catalog, Semantic Context Relationships...")
    db.seed_mock_data(reset=False)

    users = db.list_users()
    customers = db.list_customers()
    products = db.list_products()
    orders = db.list_orders_detailed()
    catalog_items = db.list_catalog()
    relationships = db.list_context_relationships()

    print(f"\n✅ ĐÃ NẠP MOCK DATA THÀNH CÔNG VÀO 'warehouse.db':")
    print(f"  - Users:                 {len(users)} tài khoản")
    print(f"  - Customers:             {len(customers)} khách hàng")
    print(f"  - Products:              {len(products)} sản phẩm")
    print(f"  - Orders:                {len(orders)} đơn hàng")
    print(f"  - Catalog:               {len(catalog_items)} mục tài nguyên & context")
    print(f"  - Context Relationships: {len(relationships)} liên kết quan hệ ngữ nghĩa\n")

    print("------------------------------------------------------------------")
    print("MẪU DANH SÁCH ĐƠN HÀNG VỪA NẠP:")
    print("------------------------------------------------------------------")
    for o in orders[:5]:
        print(f"• [Đơn #{o['order_id']} | {o['order_status'].upper()}] {o['customer_name']} (Hạng: {o['customer_tier'].upper()})")
        print(f"  Mua: {o['quantity']}x {o['product_name']} | Tổng: ${o['total_price']:,.2f}")
    print("  ... và các đơn hàng khác.")

    print("\n------------------------------------------------------------------")
    print("MẪU BẢNG CATALOG VÀ QUAN HỆ NGỮ NGHĨA:")
    print("------------------------------------------------------------------")
    for r in relationships:
        print(f"• ({r['source_name']}) --[{r['relation']}]--> ({r['target_name']}) : {r['description']}")
    print("==================================================================\n")


if __name__ == "__main__":
    main()
