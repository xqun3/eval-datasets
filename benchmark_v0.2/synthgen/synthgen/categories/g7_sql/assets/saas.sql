-- fixture: SaaS 用量域 (saas)
CREATE TABLE accounts (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    region        TEXT NOT NULL,
    plan          TEXT NOT NULL,
    contact_phone TEXT
);

CREATE TABLE features (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    module     TEXT NOT NULL,
    unit_price REAL NOT NULL
);

CREATE TABLE usage_events (
    id         INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    feature_id INTEGER NOT NULL REFERENCES features(id),
    calls      INTEGER NOT NULL,
    cost       REAL    NOT NULL,
    status     TEXT    NOT NULL,
    source     TEXT    NOT NULL,
    event_date TEXT    NOT NULL
);

INSERT INTO accounts (id, name, region, plan, contact_phone) VALUES
 (1, '星海科技',   '华东', 'enterprise', '13800000001'),
 (2, '云图信息',   '华北', 'growth',     '13800000002'),
 (3, '博远数据',   '华南', 'starter',    '13800000003'),
 (4, '长风智能',   '华东', 'growth',     '13800000004'),
 (5, '锐思网络',   '西南', 'enterprise', '13800000005'),
 (6, '和光软件',   '华中', 'starter',    '13800000006'),
 (7, '青柠云',     '华北', 'growth',     '13800000007'),
 (8, '万象互联',   '华南', 'enterprise', '13800000008'),
 (9, '恒星数科',   '西北', 'starter',    '13800000009'),
 (10,'明德云服',   '华东', 'growth',     '13800000010');

INSERT INTO features (id, name, module, unit_price) VALUES
 (1, '文本生成',   '模型服务', 0.012),
 (2, '向量检索',   '检索服务', 0.004),
 (3, '语音转写',   '多模态',   0.030),
 (4, '图像理解',   '多模态',   0.045),
 (5, '批量导出',   '数据平台', 0.002),
 (6, '实时同步',   '数据平台', 0.008),
 (7, '权限审计',   '管理后台', 0.001),
 (8, '工单机器人', '模型服务', 0.020);

INSERT INTO usage_events (id, account_id, feature_id, calls, cost, status, source, event_date) VALUES
 (1, 1, 1, 12000, 144.00, 'success',   'api',     '2024-01-07'),
 (2, 2, 3,   800,  24.00, 'failed',    'sdk',     '2024-01-22'),
 (3, 3, 2, 45000, 180.00, 'success',   'api',     '2024-02-11'),
 (4, 4, 5,  9000,  18.00, 'throttled', 'batch',   '2024-02-26'),
 (5, 5, 4,  1500,  67.50, 'success',   'console', '2024-03-14'),
 (6, 6, 8,   600,  12.00, 'pending',   'sdk',     '2024-03-30');
