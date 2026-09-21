-- fixture: 电商订单域 (ecommerce)
-- 维表数据固定, 事实表(orders)的绝大部分行由 generator 按 seed 追加生成。
CREATE TABLE customers (
    id       INTEGER PRIMARY KEY,
    name     TEXT    NOT NULL,
    city     TEXT    NOT NULL,
    level    TEXT    NOT NULL,
    phone    TEXT
);

CREATE TABLE products (
    id       INTEGER PRIMARY KEY,
    name     TEXT    NOT NULL,
    category TEXT    NOT NULL,
    price    REAL    NOT NULL
);

CREATE TABLE orders (
    id          INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    product_id  INTEGER NOT NULL REFERENCES products(id),
    qty         INTEGER NOT NULL,
    amount      REAL    NOT NULL,
    status      TEXT    NOT NULL,
    channel     TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
);

INSERT INTO customers (id, name, city, level, phone) VALUES
 (1, '陈嘉禾', '上海', 'gold',     '13900000001'),
 (2, '王思远', '北京', 'silver',   '13900000002'),
 (3, '李沐',   '深圳', 'gold',     '13900000003'),
 (4, '赵一帆', '杭州', 'bronze',   '13900000004'),
 (5, '孙悦',   '成都', 'silver',   '13900000005'),
 (6, '周子墨', '上海', 'platinum', '13900000006'),
 (7, '吴清源', '广州', 'bronze',   '13900000007'),
 (8, '郑欣然', '北京', 'gold',     '13900000008'),
 (9, '冯磊',   '武汉', 'silver',   '13900000009'),
 (10,'许知远', '深圳', 'platinum', '13900000010');

INSERT INTO products (id, name, category, price) VALUES
 (1, '轻薄笔记本',   '数码', 6499.00),
 (2, '降噪耳机',     '数码', 1299.00),
 (3, '智能手环',     '数码',  399.00),
 (4, '精品咖啡豆',   '食品',   98.50),
 (5, '有机茶叶礼盒', '食品',  268.00),
 (6, '空气炸锅',     '家电',  599.00),
 (7, '扫地机器人',   '家电', 2799.00),
 (8, '纯棉四件套',   '家居',  459.00);

INSERT INTO orders (id, customer_id, product_id, qty, amount, status, channel, created_at) VALUES
 (1, 1, 1, 1, 6499.00, 'paid',      'app',     '2024-01-05'),
 (2, 2, 4, 3,  295.50, 'paid',      'web',     '2024-01-18'),
 (3, 3, 7, 1, 2799.00, 'refunded',  'mini',    '2024-02-02'),
 (4, 4, 3, 2,  798.00, 'paid',      'offline', '2024-02-21'),
 (5, 5, 6, 1,  599.00, 'cancelled', 'app',     '2024-03-09'),
 (6, 6, 2, 2, 2598.00, 'paid',      'app',     '2024-03-27');
