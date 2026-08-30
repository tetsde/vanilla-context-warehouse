"""
Database Module for SQLite
Manages connections, schema initialization, and CRUD operations for:
- users
- customers
- products
- orders
"""

import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple, Union


class Database:
    """Quản lý kết nối và thao tác với SQLite Database."""

    def __init__(
        self,
        db_path: str = "warehouse.db",
        schema_path: Optional[str] = None
    ) -> None:
        self.db_path = db_path
        if schema_path is None:
            # Mặc định lấy schema.sql cùng thư mục với file database.py
            current_dir = os.path.dirname(os.path.abspath(__file__))
            self.schema_path = os.path.join(current_dir, "schema.sql")
        else:
            self.schema_path = schema_path

    @contextmanager
    def get_connection(self):
        """
        Context manager cung cấp kết nối SQLite.
        - Tự động bật PRAGMA foreign_keys = ON;
        - Row factory trả về sqlite3.Row để truy cập cột như dictionary.
        - Tự động commit khi thành công và rollback khi gặp lỗi.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        """Khởi tạo database bằng cách chạy file schema.sql."""
        if not os.path.exists(self.schema_path):
            raise FileNotFoundError(f"Không tìm thấy file schema tại: {self.schema_path}")

        with open(self.schema_path, "r", encoding="utf-8") as f:
            schema_sql = f.read()

        with self.get_connection() as conn:
            conn.executescript(schema_sql)

    # --------------------------------------------------------------------------
    # Generic Query Helpers
    # --------------------------------------------------------------------------
    def execute(self, query: str, params: Union[Tuple, List, Dict] = ()) -> int:
        """Thực thi câu lệnh INSERT / UPDATE / DELETE và trả về lastrowid."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.lastrowid

    def fetch_all(self, query: str, params: Union[Tuple, List, Dict] = ()) -> List[Dict[str, Any]]:
        """Thực thi SELECT và trả về danh sách dict."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def fetch_one(self, query: str, params: Union[Tuple, List, Dict] = ()) -> Optional[Dict[str, Any]]:
        """Thực thi SELECT và trả về 1 dòng dạng dict hoặc None."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            row = cursor.fetchone()
            return dict(row) if row else None

    # --------------------------------------------------------------------------
    # 1. USER OPERATIONS
    # --------------------------------------------------------------------------
    def create_user(
        self,
        username: str,
        email: str,
        password_hash: str,
        role: str = "customer",
        is_active: int = 1
    ) -> int:
        """Tạo một tài khoản người dùng mới trong bảng users."""
        query = """
            INSERT INTO users (username, email, password_hash, role, is_active)
            VALUES (?, ?, ?, ?, ?)
        """
        return self.execute(query, (username, email, password_hash, role, is_active))

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Lấy thông tin người dùng theo user_id."""
        return self.fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin người dùng theo username."""
        return self.fetch_one("SELECT * FROM users WHERE username = ?", (username,))

    def list_users(self) -> List[Dict[str, Any]]:
        """Lấy danh sách tất cả users."""
        return self.fetch_all("SELECT * FROM users ORDER BY id ASC")

    # --------------------------------------------------------------------------
    # 2. CUSTOMER OPERATIONS
    # --------------------------------------------------------------------------
    def create_customer(
        self,
        name: str,
        user_id: Optional[int] = None,
        phone: Optional[str] = None,
        tier: str = "standard",
        address: Optional[str] = None
    ) -> int:
        """Tạo thông tin khách hàng mới trong bảng customers."""
        query = """
            INSERT INTO customers (user_id, name, phone, tier, address)
            VALUES (?, ?, ?, ?, ?)
        """
        return self.execute(query, (user_id, name, phone, tier, address))

    def get_customer_by_id(self, customer_id: int) -> Optional[Dict[str, Any]]:
        """Lấy thông tin khách hàng theo customer_id."""
        return self.fetch_one("SELECT * FROM customers WHERE id = ?", (customer_id,))

    def list_customers(self) -> List[Dict[str, Any]]:
        """Lấy danh sách khách hàng kèm theo thông tin tài khoản user nếu có."""
        query = """
            SELECT 
                c.id AS customer_id,
                c.name AS customer_name,
                c.tier,
                c.phone,
                c.address,
                u.id AS user_id,
                u.username,
                u.email,
                u.role,
                c.created_at
            FROM customers c
            LEFT JOIN users u ON c.user_id = u.id
            ORDER BY c.id ASC
        """
        return self.fetch_all(query)

    # --------------------------------------------------------------------------
    # 3. PRODUCT OPERATIONS
    # --------------------------------------------------------------------------
    def create_product(
        self,
        name: str,
        price: float,
        category: Optional[str] = None,
        stock: int = 0,
        description: Optional[str] = None
    ) -> int:
        """Thêm sản phẩm mới vào bảng products."""
        query = """
            INSERT INTO products (name, category, price, stock, description)
            VALUES (?, ?, ?, ?, ?)
        """
        return self.execute(query, (name, category, price, stock, description))

    def get_product_by_id(self, product_id: int) -> Optional[Dict[str, Any]]:
        """Lấy thông tin sản phẩm theo product_id."""
        return self.fetch_one("SELECT * FROM products WHERE id = ?", (product_id,))

    def update_stock(self, product_id: int, quantity_diff: int) -> bool:
        """Cập nhật số lượng tồn kho (tăng/giảm)."""
        product = self.get_product_by_id(product_id)
        if not product:
            raise ValueError(f"Sản phẩm ID {product_id} không tồn tại.")
        
        new_stock = product["stock"] + quantity_diff
        if new_stock < 0:
            raise ValueError(f"Không đủ tồn kho cho sản phẩm {product['name']} (Hiện có: {product['stock']}).")

        with self.get_connection() as conn:
            conn.execute(
                "UPDATE products SET stock = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_stock, product_id)
            )
        return True

    def list_products(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lấy danh sách sản phẩm, có thể lọc theo category."""
        if category:
            query = "SELECT * FROM products WHERE category = ? ORDER BY id ASC"
            return self.fetch_all(query, (category,))
        return self.fetch_all("SELECT * FROM products ORDER BY id ASC")

    # --------------------------------------------------------------------------
    # 4. ORDER OPERATIONS
    # --------------------------------------------------------------------------
    def create_order(
        self,
        customer_id: int,
        product_id: int,
        quantity: int = 1,
        unit_price: Optional[float] = None,
        status: str = "pending"
    ) -> int:
        """
        Tạo đơn hàng mới:
        - Kiểm tra và trừ tồn kho tự động trong 1 transaction an toàn.
        - Nếu unit_price không truyền vào, tự động lấy giá hiện tại của sản phẩm.
        - Tính toán total_price = unit_price * quantity.
        """
        if quantity <= 0:
            raise ValueError("Số lượng (quantity) phải lớn hơn 0.")

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Lấy thông tin sản phẩm
            cursor.execute("SELECT name, price, stock FROM products WHERE id = ?", (product_id,))
            product = cursor.fetchone()
            if not product:
                raise ValueError(f"Sản phẩm với ID {product_id} không tồn tại.")

            # Kiểm tra tồn kho
            if product["stock"] < quantity:
                raise ValueError(
                    f"Sản phẩm '{product['name']}' không đủ tồn kho (Còn {product['stock']}, yêu cầu {quantity})."
                )

            # Xác định đơn giá & tổng tiền
            final_unit_price = unit_price if unit_price is not None else product["price"]
            total_price = round(final_unit_price * quantity, 2)

            # Trừ tồn kho
            new_stock = product["stock"] - quantity
            cursor.execute(
                "UPDATE products SET stock = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_stock, product_id)
            )

            # Tạo đơn hàng
            cursor.execute(
                """
                INSERT INTO orders (customer_id, product_id, quantity, unit_price, total_price, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (customer_id, product_id, quantity, final_unit_price, total_price, status)
            )
            order_id = cursor.lastrowid
            return order_id

    def get_order_by_id(self, order_id: int) -> Optional[Dict[str, Any]]:
        """Lấy chi tiết 1 đơn hàng theo order_id."""
        return self.fetch_one("SELECT * FROM orders WHERE id = ?", (order_id,))

    def list_orders_detailed(self) -> List[Dict[str, Any]]:
        """
        Truy vấn danh sách đơn hàng chi tiết:
        JOIN 4 bảng: orders -> customers -> users (nếu có) và orders -> products.
        """
        query = """
            SELECT 
                o.id AS order_id,
                o.order_date,
                o.status AS order_status,
                o.quantity,
                o.unit_price,
                o.total_price,
                c.id AS customer_id,
                c.name AS customer_name,
                c.tier AS customer_tier,
                u.email AS user_email,
                p.id AS product_id,
                p.name AS product_name,
                p.category AS product_category
            FROM orders o
            JOIN customers c ON o.customer_id = c.id
            LEFT JOIN users u ON c.user_id = u.id
            JOIN products p ON o.product_id = p.id
            ORDER BY o.order_date DESC, o.id DESC
        """
        return self.fetch_all(query)

    # --------------------------------------------------------------------------
    # 5. CATALOG OPERATIONS (Metadata & Context Management)
    # --------------------------------------------------------------------------
    def upsert_catalog_entry(
        self,
        name: str,
        type: str,
        description: Optional[str] = None,
        source: Optional[str] = None
    ) -> int:
        """Thêm mới hoặc cập nhật một mục trong catalog."""
        query = """
            INSERT INTO catalog (name, type, description, source, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(name) DO UPDATE SET
                type = excluded.type,
                description = excluded.description,
                source = excluded.source,
                updated_at = CURRENT_TIMESTAMP
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (name, type, description, source))
            return cursor.lastrowid

    def list_catalog(self, type_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lấy danh sách các mục trong catalog, có thể lọc theo type (ví dụ: 'table', 'policy')."""
        if type_filter:
            query = "SELECT * FROM catalog WHERE type = ? ORDER BY id ASC"
            return self.fetch_all(query, (type_filter,))
        return self.fetch_all("SELECT * FROM catalog ORDER BY id ASC")

    def get_catalog_entry(self, name_or_id: Union[str, int]) -> Optional[Dict[str, Any]]:
        """Lấy 1 mục catalog theo id hoặc name."""
        if isinstance(name_or_id, int):
            return self.fetch_one("SELECT * FROM catalog WHERE id = ?", (name_or_id,))
        return self.fetch_one("SELECT * FROM catalog WHERE name = ?", (name_or_id,))

    def seed_default_catalog(self) -> None:
        """Tự động chèn danh mục mặc định cho các bảng và chính sách ngữ cảnh."""
        default_items = [
            ("users", "table", "Tài khoản người dùng và phân quyền hệ thống", "SQLite/Warehouse"),
            ("customers", "table", "Thông tin khách hàng và phân hạng thành viên", "SQLite/Warehouse"),
            ("products", "table", "Danh mục sản phẩm, giá bán và tồn kho", "SQLite/Warehouse"),
            ("orders", "table", "Thông tin đơn hàng và chi tiết thanh toán", "SQLite/Warehouse"),
            ("refund_policy", "policy", "Quy định đổi trả và hoàn tiền", "refund_policy.md"),
            ("vip_policy", "policy", "Chính sách khách hàng thân thiết & hội viên VIP", "vip_policy.md"),
            ("delivery_policy", "policy", "Chính sách vận chuyển & giao hàng", "delivery_policy.md"),
        ]
        for name, item_type, desc, src in default_items:
            self.upsert_catalog_entry(name, item_type, desc, src)

    # --------------------------------------------------------------------------
    # 6. CONTEXT RELATIONSHIPS (Semantic Context Graph)
    # --------------------------------------------------------------------------
    def add_context_relationship(
        self,
        source: Union[str, int],
        relation: str,
        target: Union[str, int],
        description: Optional[str] = None
    ) -> int:
        """
        Thêm một liên kết ngữ nghĩa giữa 2 context/bảng trong catalog.
        - Chấp nhận tên (name) hoặc ID của source và target.
        """
        # Resolve source_id
        if isinstance(source, str):
            src_entry = self.get_catalog_entry(source)
            if not src_entry:
                raise ValueError(f"Không tìm thấy context source: '{source}' trong catalog.")
            source_id = src_entry["id"]
        else:
            source_id = source

        # Resolve target_id
        if isinstance(target, str):
            tgt_entry = self.get_catalog_entry(target)
            if not tgt_entry:
                raise ValueError(f"Không tìm thấy context target: '{target}' trong catalog.")
            target_id = tgt_entry["id"]
        else:
            target_id = target

        query = """
            INSERT INTO context_relationships (source_id, relation, target_id, description, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(source_id, relation, target_id) DO UPDATE SET
                description = excluded.description,
                updated_at = CURRENT_TIMESTAMP
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (source_id, relation, target_id, description))
            return cursor.lastrowid

    def list_context_relationships(
        self,
        source_name: Optional[str] = None,
        relation: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Truy vấn danh sách các quan hệ ngữ nghĩa đã JOIN với bảng catalog.
        """
        query = """
            SELECT 
                r.id AS relationship_id,
                src.name AS source_name,
                src.type AS source_type,
                src.source AS source_origin,
                r.relation,
                tgt.name AS target_name,
                tgt.type AS target_type,
                tgt.source AS target_origin,
                r.description,
                r.created_at
            FROM context_relationships r
            JOIN catalog src ON r.source_id = src.id
            JOIN catalog tgt ON r.target_id = tgt.id
            WHERE 1=1
        """
        params = []
        if source_name:
            query += " AND src.name = ?"
            params.append(source_name)
        if relation:
            query += " AND r.relation = ?"
            params.append(relation)

        query += " ORDER BY r.id ASC"
        return self.fetch_all(query, params)

    def seed_default_context_relationships(self) -> None:
        """
        Tự động thiết lập các quan hệ ngữ nghĩa mặc định giữa các context:
        - customers --[has]--> orders
        - orders --[governed_by]--> refund_policy
        - customers --[governed_by]--> vip_policy
        - orders --[governed_by]--> delivery_policy
        - orders --[contains]--> products
        - users --[owns]--> customers
        """
        self.seed_default_catalog()
        default_relations = [
            ("customers", "has", "orders", "Khách hàng sở hữu các đơn hàng"),
            ("orders", "governed_by", "refund_policy", "Đơn hàng chịu sự chi phối của chính sách đổi trả/hoàn tiền"),
            ("customers", "governed_by", "vip_policy", "Khách hàng được áp dụng chính sách ưu đãi thành viên VIP"),
            ("orders", "governed_by", "delivery_policy", "Đơn hàng áp dụng chính sách vận chuyển và giao nhận"),
            ("orders", "contains", "products", "Đơn hàng chứa các sản phẩm"),
            ("users", "owns", "customers", "Tài khoản hệ thống liên kết hồ sơ khách hàng"),
        ]
        for src, rel, tgt, desc in default_relations:
            self.add_context_relationship(src, rel, tgt, desc)

    # --------------------------------------------------------------------------
    # 7. MOCK DATA SEEDER
    # --------------------------------------------------------------------------
    def seed_mock_data(self, reset: bool = False) -> None:
        """
        Nạp toàn bộ dữ liệu mẫu phong phú (Users, Customers, Products, Orders, Catalog, Context Relationships).
        Nếu reset=True, sẽ xóa toàn bộ dữ liệu cũ và khởi tạo lại bảng từ schema.sql.
        """
        if reset:
            self.init_db()

        # 1. Seed Catalog & Semantic Graph
        self.seed_default_catalog()
        self.seed_default_context_relationships()

        # Bổ sung metadata cho các bảng còn lại vào catalog
        self.upsert_catalog_entry("catalog", "table", "Danh mục siêu dữ liệu quản lý các tài nguyên và context", "SQLite/Warehouse")
        self.upsert_catalog_entry("context_relationships", "table", "Mô hình quan hệ ngữ nghĩa Semantic Graph giữa các context", "SQLite/Warehouse")

        # 2. Seed Users
        mock_users = [
            ("admin_root", "admin@warehouse.com", "argon2_hash_admin_01", "admin"),
            ("manager_tech", "tech.manager@warehouse.com", "argon2_hash_tech_02", "admin"),
            ("staff_support01", "support1@warehouse.com", "argon2_hash_staff_03", "staff"),
            ("staff_warehouse", "warehouse.ops@warehouse.com", "argon2_hash_staff_04", "staff"),
            ("nguyen_van_an", "an.nguyen@gmail.com", "argon2_hash_user_05", "customer"),
            ("tran_thi_bich", "bich.tran@gmail.com", "argon2_hash_user_06", "customer"),
            ("le_hoang_cuong", "cuong.le@yahoo.com", "argon2_hash_user_07", "customer"),
            ("pham_minh_dung", "dung.pham@outlook.com", "argon2_hash_user_08", "customer"),
            ("hoang_lan_emily", "emily.hoang@gmail.com", "argon2_hash_user_09", "customer"),
            ("vu_quoc_phong", "phong.vu@gmail.com", "argon2_hash_user_10", "customer"),
        ]
        user_ids = {}
        for username, email, pwd_hash, role in mock_users:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT id FROM users WHERE username = ? OR email = ?", (username, email))
                row = cur.fetchone()
                if row:
                    user_ids[username] = row["id"]
                else:
                    uid = self.create_user(username, email, pwd_hash, role)
                    user_ids[username] = uid


        # 3. Seed Customers
        mock_customers = [
            ("Nguyễn Văn An", user_ids.get("nguyen_van_an"), "0901112233", "platinum", "Tòa Landmark 81, P.22, Bình Thạnh, TP.HCM"),
            ("Trần Thị Bích", user_ids.get("tran_thi_bich"), "0912223344", "gold", "Khu đô thị Starlake, Tây Hồ, Hà Nội"),
            ("Lê Hoàng Cường", user_ids.get("le_hoang_cuong"), "0983334455", "gold", "Tòa nhà Vincom Center, 72 Lê Thánh Tôn, Q.1, TP.HCM"),
            ("Phạm Minh Dũng", user_ids.get("pham_minh_dung"), "0974445566", "silver", "120 Nguyễn Văn Linh, Q. Hải Châu, Đà Nẵng"),
            ("Hoàng Lan Emily", user_ids.get("hoang_lan_emily"), "0935556677", "silver", "88 Phố Huế, Q. Hai Bà Trưng, Hà Nội"),
            ("Vũ Quốc Phong", user_ids.get("vu_quoc_phong"), "0946667788", "bronze", "45 Đường 30/4, P. An Phú, Ninh Kiều, Cần Thơ"),
            ("Đoàn Thu Hằng (Khách Vãng Lai)", None, "0967778899", "standard", "15 Lê Duẩn, TP. Huế"),
            ("Ngô Quốc Bảo (Khách Vãng Lai)", None, "0928889900", "standard", "78 Trần Phú, Lộc Thọ, Nha Trang"),
        ]
        customer_ids = []
        for name, uid, phone, tier, addr in mock_customers:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT id FROM customers WHERE name = ?", (name,))
                row = cur.fetchone()
                if row:
                    customer_ids.append(row["id"])
                else:
                    cid = self.create_customer(name, uid, phone, tier, addr)
                    customer_ids.append(cid)

        # 4. Seed Products
        mock_products = [
            ("MacBook Pro 16\" M3 Max", 3499.0, "Laptops", 15, "Apple M3 Max 16-core CPU, 40-core GPU, 48GB RAM, 1TB SSD"),
            ("Dell XPS 15 OLED Touch", 1899.0, "Laptops", 25, "Intel Core i7-13700H, 32GB RAM, 1TB SSD, 3.5K OLED"),
            ("iPhone 16 Pro Max 256GB", 1199.0, "Smartphones", 40, "Titanium tự nhiên, Chip A18 Pro, Camera 48MP Zoom 5x"),
            ("Samsung Galaxy S24 Ultra", 1099.0, "Smartphones", 30, "Snapdragon 8 Gen 3 for Galaxy, 12GB RAM, S-Pen tích hợp"),
            ("iPad Pro M4 11-inch", 999.0, "Tablets", 35, "Ultra Retina XDR OLED, Chip Apple M4, Wi-Fi 256GB"),
            ("Sony WH-1000XM5 Wireless", 399.0, "Audio", 50, "Tai nghe chống ồn chủ động cao cấp, pin 30 giờ, Hi-Res Audio"),
            ("AirPods Pro 2 USB-C", 249.0, "Audio", 80, "Khử tiếng ồn chủ động gấp 2 lần, Cổng sạc USB-C, chuẩn MagSafe"),
            ("Keychron Q1 Pro Custom", 199.0, "Accessories", 45, "Bàn phím cơ không dây vỏ nhôm CNC, Hot-swap, QMK/VIA"),
            ("Logitech MX Master 3S", 99.0, "Accessories", 100, "Chuột không dây công thái học, cảm biến 8000 DPI, cuộn MagSpeed"),
            ("LG UltraFine 27\" 4K Monitor", 499.0, "Monitors", 20, "Màn hình IPS 4K UHD, HDR400, USB Type-C 90W Power Delivery"),
            ("Ghế Công Thái Học Herman Miller Aeron", 1495.0, "Furniture", 10, "Ghế công thái học cao cấp xuất xứ USA, bảo hành 12 năm"),
            ("Củ Sạc Anker Prime 100W GaN", 79.0, "Accessories", 120, "Công nghệ GaN III, 2 cổng USB-C, 1 cổng USB-A, siêu nhỏ gọn"),
        ]
        product_ids = []
        for name, price, cat, stock, desc in mock_products:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT id FROM products WHERE name = ?", (name,))
                row = cur.fetchone()
                if row:
                    product_ids.append(row["id"])
                else:
                    pid = self.create_product(name, price, cat, stock, desc)
                    product_ids.append(pid)

        # 5. Seed Orders
        mock_orders = [
            (customer_ids[0], product_ids[0], 1, "completed"),   # An mua MacBook Pro 16
            (customer_ids[0], product_ids[8], 1, "completed"),   # An mua Logitech MX Master 3S
            (customer_ids[0], product_ids[10], 1, "completed"),  # An mua Herman Miller Aeron
            (customer_ids[1], product_ids[2], 1, "completed"),   # Bích mua iPhone 16 Pro Max
            (customer_ids[1], product_ids[6], 1, "completed"),   # Bích mua AirPods Pro 2
            (customer_ids[2], product_ids[1], 1, "completed"),   # Cường mua Dell XPS 15
            (customer_ids[2], product_ids[7], 1, "completed"),   # Cường mua Keychron Q1 Pro
            (customer_ids[3], product_ids[3], 1, "processing"),  # Dũng mua Galaxy S24 Ultra
            (customer_ids[4], product_ids[5], 1, "processing"),  # Emily mua Sony WH-1000XM5
            (customer_ids[4], product_ids[11], 2, "completed"),  # Emily mua 2 Củ sạc Anker
            (customer_ids[5], product_ids[9], 1, "pending"),     # Phong mua Màn hình LG 4K
            (customer_ids[6], product_ids[8], 1, "pending"),     # Hằng (Vãng lai) mua Chuột Logitech
            (customer_ids[7], product_ids[6], 1, "cancelled"),   # Bảo (Vãng lai) mua AirPods nhưng đã hủy
        ]
        with self.get_connection() as conn:
            cur = conn.cursor()
            for cid, pid, qty, status in mock_orders:
                # Kiểm tra nếu đơn hàng với khách hàng và sản phẩm này chưa có thì tạo
                cur.execute("SELECT id FROM orders WHERE customer_id = ? AND product_id = ?", (cid, pid))
                if not cur.fetchone():
                    self.create_order(customer_id=cid, product_id=pid, quantity=qty, status=status)




