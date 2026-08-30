-- ==============================================================================
-- SQLITE DATABASE SCHEMA
-- Tables: users, customers, products, orders
-- ==============================================================================

-- Bật tính năng kiểm tra ràng buộc khóa ngoại
PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------------------------
-- 1. BẢNG USERS (Tài khoản người dùng hệ thống)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'customer' CHECK(role IN ('admin', 'staff', 'customer')),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------------------------
-- 2. BẢNG CUSTOMERS (Thông tin khách hàng)
-- Liên kết 1:1 hoặc 1:N với bảng USERS thông qua user_id
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE,
    name TEXT NOT NULL,
    phone TEXT,
    tier TEXT NOT NULL DEFAULT 'standard' CHECK(tier IN ('standard', 'bronze', 'silver', 'gold', 'platinum')),
    address TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL ON UPDATE CASCADE
);

-- ------------------------------------------------------------------------------
-- 3. BẢNG PRODUCTS (Danh mục sản phẩm)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT,
    price REAL NOT NULL CHECK(price >= 0),
    stock INTEGER NOT NULL DEFAULT 0 CHECK(stock >= 0),
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------------------------
-- 4. BẢNG ORDERS (Đơn hàng)
-- Liên kết N:1 với CUSTOMERS (customer_id) và N:1 với PRODUCTS (product_id)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1 CHECK(quantity > 0),
    unit_price REAL NOT NULL CHECK(unit_price >= 0),
    total_price REAL NOT NULL CHECK(total_price >= 0),
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'processing', 'completed', 'cancelled')),
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE RESTRICT ON UPDATE CASCADE
);

-- ------------------------------------------------------------------------------
-- 5. BẢNG CATALOG (Danh mục siêu dữ liệu - Metadata & Context Catalog)
-- Lưu trữ danh sách các bảng dữ liệu, chính sách ngữ cảnh, tài liệu,...
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS catalog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    type TEXT NOT NULL,
    description TEXT,
    source TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------------------------
-- 6. BẢNG CONTEXT_RELATIONSHIPS (Mô hình hóa quan hệ ngữ nghĩa giữa các Context)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS context_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    relation TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES catalog (id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (target_id) REFERENCES catalog (id) ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE(source_id, relation, target_id)
);

-- ------------------------------------------------------------------------------
-- INDEXES (Tối ưu hiệu năng truy vấn cho các cột khóa ngoại & tìm kiếm)
-- ------------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_customers_user_id ON customers(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_product_id ON orders(product_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
CREATE INDEX IF NOT EXISTS idx_catalog_type ON catalog(type);
CREATE INDEX IF NOT EXISTS idx_context_rel_source ON context_relationships(source_id);
CREATE INDEX IF NOT EXISTS idx_context_rel_target ON context_relationships(target_id);
CREATE INDEX IF NOT EXISTS idx_context_rel_relation ON context_relationships(relation);


