-- fixture: 物流履约域 (logistics)
CREATE TABLE warehouses (
    id       INTEGER PRIMARY KEY,
    name     TEXT NOT NULL,
    province TEXT NOT NULL,
    grade    TEXT NOT NULL,
    hotline  TEXT
);

CREATE TABLE couriers (
    id       INTEGER PRIMARY KEY,
    name     TEXT NOT NULL,
    company  TEXT NOT NULL,
    base_fee REAL NOT NULL
);

CREATE TABLE shipments (
    id           INTEGER PRIMARY KEY,
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
    courier_id   INTEGER NOT NULL REFERENCES couriers(id),
    packages     INTEGER NOT NULL,
    freight      REAL    NOT NULL,
    status       TEXT    NOT NULL,
    route_type   TEXT    NOT NULL,
    ship_date    TEXT    NOT NULL
);

INSERT INTO warehouses (id, name, province, grade, hotline) VALUES
 (1, '华东一仓', '江苏', 'A', '02150000001'),
 (2, '华北一仓', '北京', 'A', '01050000002'),
 (3, '华南一仓', '广东', 'B', '02050000003'),
 (4, '西南一仓', '四川', 'B', '02850000004'),
 (5, '华中一仓', '湖北', 'C', '02750000005'),
 (6, '华东二仓', '浙江', 'A', '05710000006'),
 (7, '西北一仓', '陕西', 'C', '02950000007'),
 (8, '华南二仓', '福建', 'B', '05910000008'),
 (9, '东北一仓', '辽宁', 'C', '02450000009'),
 (10,'华北二仓', '天津', 'B', '02250000010');

INSERT INTO couriers (id, name, company, base_fee) VALUES
 (1, '张伟', '顺捷', 12.00),
 (2, '刘洋', '通达', 8.50),
 (3, '陈静', '顺捷', 12.00),
 (4, '黄磊', '极兔风', 7.00),
 (5, '林岚', '通达', 8.50),
 (6, '徐睿', '邮政速运', 10.00),
 (7, '何苗', '极兔风', 7.00),
 (8, '高扬', '邮政速运', 10.00);

INSERT INTO shipments (id, warehouse_id, courier_id, packages, freight, status, route_type, ship_date) VALUES
 (1, 1, 1, 120, 1440.00, 'delivered',  'land',    '2024-01-09'),
 (2, 2, 2,  80,  680.00, 'in_transit', 'air',     '2024-01-25'),
 (3, 3, 4, 200, 1400.00, 'delivered',  'express', '2024-02-06'),
 (4, 4, 5,  45,  382.50, 'returned',   'land',    '2024-02-19'),
 (5, 5, 6,  60,  600.00, 'pending',    'sea',     '2024-03-12'),
 (6, 6, 3, 150, 1800.00, 'delivered',  'express', '2024-03-29');
