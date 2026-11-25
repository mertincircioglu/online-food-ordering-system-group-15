-- ============================================================================
-- CMPE341 Database Design & Management - Group 15
-- Project: BiteFlow - Online Food Ordering System
-- Logical Schema Implementation: 15 Normalized Tables (PostgreSQL 16)
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ----------------------------------------------------------------------------
-- 1. MEMBER (Superclass for Admin, Customer, Restaurant Manager)
-- ----------------------------------------------------------------------------
CREATE TABLE member (
    member_id     SERIAL PRIMARY KEY,
    email         VARCHAR(120) NOT NULL UNIQUE,
    first_name    VARCHAR(60)  NOT NULL,
    middle_name   VARCHAR(60),
    last_name     VARCHAR(60)  NOT NULL,
    password_hash TEXT         NOT NULL,
    phone_number  VARCHAR(25)  NOT NULL
);

-- ----------------------------------------------------------------------------
-- 2. ADMIN (Subclass of Member)
-- ----------------------------------------------------------------------------
CREATE TABLE admin (
    admin_id  SERIAL PRIMARY KEY,
    member_id INT NOT NULL UNIQUE REFERENCES member(member_id) ON DELETE CASCADE
);

-- ----------------------------------------------------------------------------
-- 3. CUSTOMER (Subclass of Member)
-- ----------------------------------------------------------------------------
CREATE TABLE customer (
    customer_id SERIAL PRIMARY KEY,
    member_id   INT         NOT NULL UNIQUE REFERENCES member(member_id) ON DELETE CASCADE,
    gender      VARCHAR(25) NOT NULL
                CHECK (gender IN ('Male', 'Female', 'Other', 'Prefer not to say'))
);

-- ----------------------------------------------------------------------------
-- 4. ADDRESS
-- ----------------------------------------------------------------------------
CREATE TABLE address (
    address_id    SERIAL PRIMARY KEY,
    address_title VARCHAR(60),
    province      VARCHAR(60)   NOT NULL,
    district      VARCHAR(60)   NOT NULL,
    subdistrict   VARCHAR(60)   NOT NULL,
    neighborhood  VARCHAR(80)   NOT NULL,
    street        VARCHAR(120)  NOT NULL,
    floor         VARCHAR(20),
    building_no   VARCHAR(20),
    latitude      NUMERIC(9, 6) NOT NULL,
    longitude     NUMERIC(9, 6) NOT NULL,
    details       TEXT
);

-- ----------------------------------------------------------------------------
-- 5. CUSTOMER_ADDRESS (M:N between Customer and Address)
-- ----------------------------------------------------------------------------
CREATE TABLE customer_address (
    customer_id INT NOT NULL REFERENCES customer(customer_id) ON DELETE CASCADE,
    address_id  INT NOT NULL REFERENCES address(address_id)   ON DELETE CASCADE,
    PRIMARY KEY (customer_id, address_id)
);

-- ----------------------------------------------------------------------------
-- 6. CUSTOMER_PAYMENT_INFO (Multi-valued saved payment methods for Customer)
-- ----------------------------------------------------------------------------
CREATE TABLE customer_payment_info (
    payment_info_id    SERIAL PRIMARY KEY,
    customer_id        INT          NOT NULL REFERENCES customer(customer_id) ON DELETE CASCADE,
    saved_payment_info VARCHAR(120) NOT NULL
);

-- ----------------------------------------------------------------------------
-- 7. RESTAURANT (1:1 with Address; Rating is derived from restaurant_review)
-- ----------------------------------------------------------------------------
CREATE TABLE restaurant (
    restaurant_id    SERIAL PRIMARY KEY,
    address_id       INT            NOT NULL UNIQUE REFERENCES address(address_id) ON DELETE RESTRICT,
    name             VARCHAR(100)   NOT NULL,
    phone_number     VARCHAR(25)    NOT NULL,
    email            VARCHAR(120)   NOT NULL,
    min_order_amount NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (min_order_amount >= 0)
);

-- ----------------------------------------------------------------------------
-- 8. RESTAURANT_MANAGER (Subclass of Member, manages a Restaurant)
-- ----------------------------------------------------------------------------
CREATE TABLE restaurant_manager (
    manager_id    SERIAL PRIMARY KEY,
    member_id     INT NOT NULL UNIQUE REFERENCES member(member_id)         ON DELETE CASCADE,
    restaurant_id INT NOT NULL        REFERENCES restaurant(restaurant_id) ON DELETE CASCADE
);

-- ----------------------------------------------------------------------------
-- 9. RESTAURANT_WORKING_HOURS (Multi-valued composite attribute of Restaurant)
-- ----------------------------------------------------------------------------
CREATE TABLE restaurant_working_hours (
    restaurant_id INT         NOT NULL REFERENCES restaurant(restaurant_id) ON DELETE CASCADE,
    day           VARCHAR(15) NOT NULL
                  CHECK (day IN ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')),
    opening_time  TIME        NOT NULL,
    closing_time  TIME        NOT NULL,
    PRIMARY KEY (restaurant_id, day)
);

-- ----------------------------------------------------------------------------
-- 10. RESTAURANT_DELIVERY_TYPE (Multi-valued delivery types of Restaurant)
-- ----------------------------------------------------------------------------
CREATE TABLE restaurant_delivery_type (
    restaurant_id INT         NOT NULL REFERENCES restaurant(restaurant_id) ON DELETE CASCADE,
    delivery_type VARCHAR(30) NOT NULL
                  CHECK (delivery_type IN ('Platform_carrier', 'Restaurant_carrier', 'Pick_up')),
    PRIMARY KEY (restaurant_id, delivery_type)
);

-- ----------------------------------------------------------------------------
-- 11. RESTAURANT_CUISINE (Multi-valued cuisine types of Restaurant)
-- ----------------------------------------------------------------------------
CREATE TABLE restaurant_cuisine (
    restaurant_id INT         NOT NULL REFERENCES restaurant(restaurant_id) ON DELETE CASCADE,
    cuisine_type  VARCHAR(50) NOT NULL,
    PRIMARY KEY (restaurant_id, cuisine_type)
);

-- ----------------------------------------------------------------------------
-- 12. PRODUCT (Menu items offered by a Restaurant)
-- ----------------------------------------------------------------------------
CREATE TABLE product (
    product_id          SERIAL PRIMARY KEY,
    restaurant_id       INT            NOT NULL REFERENCES restaurant(restaurant_id) ON DELETE CASCADE,
    product_name        VARCHAR(100)   NOT NULL,
    description         TEXT,
    category            VARCHAR(30)    NOT NULL
                        CHECK (category IN ('Main Course', 'Drinks', 'Sweets', 'Other')),
    price               NUMERIC(10, 2) NOT NULL CHECK (price > 0),
    is_available        BOOLEAN        NOT NULL DEFAULT TRUE,
    discount_available  BOOLEAN        NOT NULL DEFAULT FALSE,
    discount_percentage NUMERIC(5, 2)
                        CHECK (
                            (discount_available = FALSE AND discount_percentage IS NULL)
                            OR (discount_available = TRUE AND discount_percentage > 0 AND discount_percentage <= 90)
                        )
);

-- ----------------------------------------------------------------------------
-- 13. ORDERS (Mapped from Order entity; pluralized to avoid SQL keyword ORDER)
-- ----------------------------------------------------------------------------
CREATE TABLE orders (
    order_id                SERIAL PRIMARY KEY,
    restaurant_id           INT            NOT NULL REFERENCES restaurant(restaurant_id) ON DELETE CASCADE,
    customer_id             INT            NOT NULL REFERENCES customer(customer_id)     ON DELETE CASCADE,
    delivery_address_id     INT                     REFERENCES address(address_id)       ON DELETE SET NULL,
    delivery_type           VARCHAR(30)    NOT NULL
                            CHECK (delivery_type IN ('Platform_carrier', 'Restaurant_carrier', 'Pick_up')),
    payment_method          VARCHAR(30)    NOT NULL
                            CHECK (payment_method IN ('Online', 'Card at the door', 'Cash at the door')),
    order_date              TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    order_status            VARCHAR(30)    NOT NULL DEFAULT 'Order Confirmed'
                            CHECK (order_status IN ('Order Confirmed', 'Preparing', 'On the way', 'Delivered', 'Cancelled')),
    estimated_delivery_time INT            NOT NULL CHECK (estimated_delivery_time > 0),
    total_price             NUMERIC(10, 2) NOT NULL CHECK (total_price >= 0)
);

-- ----------------------------------------------------------------------------
-- 14. ORDER_ITEMS (Weak/Associative entity resolving Order M:N Product)
-- ----------------------------------------------------------------------------
CREATE TABLE order_items (
    order_id   INT            NOT NULL REFERENCES orders(order_id)    ON DELETE CASCADE,
    product_id INT            NOT NULL REFERENCES product(product_id) ON DELETE CASCADE,
    unit_price NUMERIC(10, 2) NOT NULL CHECK (unit_price > 0),
    quantity   INT            NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, product_id)
);

-- ----------------------------------------------------------------------------
-- 15. RESTAURANT_REVIEW (1:1 per Order; drives derived Restaurant.Rating)
-- ----------------------------------------------------------------------------
CREATE TABLE restaurant_review (
    restaurant_review_id SERIAL PRIMARY KEY,
    customer_id          INT       NOT NULL        REFERENCES customer(customer_id)     ON DELETE CASCADE,
    restaurant_id        INT       NOT NULL        REFERENCES restaurant(restaurant_id) ON DELETE CASCADE,
    order_id             INT       NOT NULL UNIQUE REFERENCES orders(order_id)          ON DELETE CASCADE,
    rating               INT       NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment              TEXT,
    date                 TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Helpful Indexes
CREATE INDEX idx_product_restaurant ON product(restaurant_id);
CREATE INDEX idx_orders_customer    ON orders(customer_id);
CREATE INDEX idx_orders_restaurant  ON orders(restaurant_id);
CREATE INDEX idx_review_restaurant  ON restaurant_review(restaurant_id);

-- ============================================================================
-- SEED DATA (Minimum 3+ realistic records in EVERY ONE of the 15 tables)
-- Passwords hashed with bcrypt (cost 12) via pgcrypto
-- ============================================================================

-- 1. Members (11 total: 3 Admins, 4 Restaurant Managers, 4 Customers)
INSERT INTO member (email, first_name, middle_name, last_name, password_hash, phone_number) VALUES
('admin@biteflow.com',       'System',  NULL,   'Admin',        crypt('admin123',    gen_salt('bf', 12)), '+90 532 100 0001'),
('ops@biteflow.com',         'Deniz',   'Alp',  'Kaya',         crypt('admin123',    gen_salt('bf', 12)), '+90 532 100 0002'),
('support@biteflow.com',     'Elif',    NULL,   'Aydin',        crypt('admin123',    gen_salt('bf', 12)), '+90 532 100 0003'),
('manager1@biteflow.com',    'Kerem',   NULL,   'Ozturk',       crypt('manager123',  gen_salt('bf', 12)), '+90 532 300 0001'),
('manager2@biteflow.com',    'Marco',   'Luca', 'Rossi',        crypt('manager123',  gen_salt('bf', 12)), '+90 532 300 0002'),
('manager3@biteflow.com',    'Burak',   NULL,   'Arslan',       crypt('manager123',  gen_salt('bf', 12)), '+90 532 300 0003'),
('manager4@biteflow.com',    'Kenji',   NULL,   'Tanaka',       crypt('manager123',  gen_salt('bf', 12)), '+90 532 300 0004'),
('customer1@atilim.edu.tr',  'Mert',    NULL,   'Incircioglu',  crypt('customer123', gen_salt('bf', 12)), '+90 533 200 1001'),
('ayse@atilim.edu.tr',       'Ayse',    'Nur',  'Demir',        crypt('customer123', gen_salt('bf', 12)), '+90 533 200 1002'),
('can@atilim.edu.tr',        'Can',     NULL,   'Yilmaz',       crypt('customer123', gen_salt('bf', 12)), '+90 533 200 1003'),
('zeynep@atilim.edu.tr',     'Zeynep',  NULL,   'Celik',        crypt('customer123', gen_salt('bf', 12)), '+90 533 200 1004');

-- 2. Admins (3 records)
INSERT INTO admin (member_id) VALUES (1), (2), (3);

-- 3. Customers (4 records)
INSERT INTO customer (member_id, gender) VALUES
(8,  'Male'),
(9,  'Female'),
(10, 'Male'),
(11, 'Female');

-- 4. Addresses (10 records: 5 for restaurants, 5 for customers)
INSERT INTO address (address_title, province, district, subdistrict, neighborhood, street, floor, building_no, latitude, longitude, details) VALUES
('Anatolia Grill HQ',  'Ankara', 'Golbasi',     'Incek',        'Kizilcasar',    'Incek Bulvari',         '1',  '112', 39.814200, 32.724500, 'Main entrance next to park'),
('Napoli Kitchen',     'Ankara', 'Cankaya',     'Kavaklidere',  'Barbaros',      'Tunalihilmi Caddesi',   'G',  '54',  39.904100, 32.860200, 'Corner storefront'),
('Smash & Craft Shop', 'Ankara', 'Cankaya',     'Bahcelievler', 'Yukari Bahceli','3. Cadde',              'G',  '19',  39.921500, 32.822400, 'Opposite metro exit'),
('Sakura Bar',         'Ankara', 'Cankaya',     'GOP',          'Kazim Ozalp',   'Filistin Sokak',        '2',  '8',   39.893800, 32.871900, 'Terrace floor'),
('Green Bowl Studio',  'Ankara', 'Cankaya',     'Cayyolu',      'Alacaatli',     'Park Caddesi',          '1',  '31',  39.882400, 32.688100, 'Plaza courtyard'),
('Home - Incek Vista', 'Ankara', 'Golbasi',     'Incek',        'Kizilcasar',    '1182. Cadde',           '4',  'B-12',39.819500, 32.731000, 'Ring intercom #12'),
('Campus Library',     'Ankara', 'Golbasi',     'Incek',        'Kizilcasar',    'Atilim University Rd',  '1',  'A-1', 39.812800, 32.722100, 'Leave at main security gate'),
('Home - Turan Gunes', 'Ankara', 'Cankaya',     'Yildiz',       'Hilal',         'Turan Gunes Bulvari',   '6',  '88',  39.878900, 32.866500, 'Ring bell twice'),
('Home - Bahceli',     'Ankara', 'Cankaya',     'Bahcelievler', 'Bahcelievler',  '7. Cadde',              '3',  '24',  39.918900, 32.825800, 'Call upon arrival'),
('Home - Umitkoy',     'Ankara', 'Yenimahalle', 'Umitkoy',      'Umit',          '2494. Sokak',           '2',  '14',  39.899200, 32.700500, 'Next to Galleria');

-- 5. Customer_Address (6 records)
INSERT INTO customer_address (customer_id, address_id) VALUES
(1, 6),
(1, 7),
(2, 8),
(3, 9),
(4, 10),
(2, 7);

-- 6. Customer_Payment_Info (5 records)
INSERT INTO customer_payment_info (customer_id, saved_payment_info) VALUES
(1, 'Visa ending in 4242 (Personal)'),
(1, 'BiteFlow Online Wallet'),
(2, 'Mastercard ending in 8819'),
(3, 'Troy Card ending in 1104'),
(4, 'Visa ending in 5590');

-- 7. Restaurants (5 records)
INSERT INTO restaurant (address_id, name, phone_number, email, min_order_amount) VALUES
(1, 'Anatolia Grill House',     '+90 312 460 1100', 'contact@anatoliagrill.com', 150.00),
(2, 'Napoli Woodfire Pizzeria', '+90 312 428 2200', 'hello@napoliwoodfire.com',  180.00),
(3, 'Smash & Craft Burgers',    '+90 312 215 3300', 'order@smashcraft.com',      160.00),
(4, 'Sakura Sushi Bar',         '+90 312 446 4400', 'info@sakurasushi.com',      250.00),
(5, 'Green Bowl Kitchen',       '+90 312 240 5500', 'fresh@greenbowl.com',       120.00);

-- 8. Restaurant Managers (4 records)
INSERT INTO restaurant_manager (member_id, restaurant_id) VALUES
(4, 1),
(5, 2),
(6, 3),
(7, 4);

-- 9. Restaurant Working Hours (35 records: Mon-Sun for all 5 restaurants)
INSERT INTO restaurant_working_hours (restaurant_id, day, opening_time, closing_time)
SELECT r.restaurant_id, d.day, '10:00'::TIME, '23:00'::TIME
FROM restaurant r
CROSS JOIN (
    VALUES ('Monday'), ('Tuesday'), ('Wednesday'), ('Thursday'), ('Friday'), ('Saturday'), ('Sunday')
) AS d(day);

-- 10. Restaurant Delivery Types (12 records)
INSERT INTO restaurant_delivery_type (restaurant_id, delivery_type) VALUES
(1, 'Platform_carrier'), (1, 'Restaurant_carrier'), (1, 'Pick_up'),
(2, 'Platform_carrier'), (2, 'Restaurant_carrier'), (2, 'Pick_up'),
(3, 'Platform_carrier'), (3, 'Pick_up'),
(4, 'Platform_carrier'), (4, 'Restaurant_carrier'),
(5, 'Restaurant_carrier'), (5, 'Pick_up');

-- 11. Restaurant Cuisines (10 records)
INSERT INTO restaurant_cuisine (restaurant_id, cuisine_type) VALUES
(1, 'Turkish Kebab'), (1, 'Grill & BBQ'),
(2, 'Italian'),       (2, 'Woodfire Pizza'),
(3, 'American'),      (3, 'Burgers'),
(4, 'Japanese'),      (4, 'Sushi'),
(5, 'Healthy'),       (5, 'Salads & Bowls');

-- 12. Products (18 records across 5 restaurants & all 4 categories)
INSERT INTO product (restaurant_id, product_name, description, category, price, is_available, discount_available, discount_percentage) VALUES
(1, 'Adana Kebab',                 'Charcoal-grilled spicy minced lamb with lavash and roasted peppers', 'Main Course', 280.00, TRUE, FALSE, NULL),
(1, 'Iskender Kebab',              'Sliced doner over pita bread with tomato sauce and melted butter',   'Main Course', 350.00, TRUE, TRUE,  10.00),
(1, 'Traditional Ayran',           'Chilled frothy yogurt drink lightly salted',                         'Drinks',       45.00, TRUE, FALSE, NULL),
(1, 'Gaziantep Baklava (4 pcs)',   'Crispy phyllo layered with Antep pistachios and light syrup',        'Sweets',      160.00, TRUE, FALSE, NULL),
(2, 'Margherita Classica',         'San Marzano tomato sauce, fresh buffalo mozzarella, and basil',      'Main Course', 250.00, TRUE, TRUE,  10.00),
(2, 'Pepperoni Diavola',           'Crispy beef pepperoni, mozzarella, oregano, and chili oil',          'Main Course', 300.00, TRUE, FALSE, NULL),
(2, 'Classic Tiramisu',            'Espresso-soaked ladyfingers layered with mascarpone cream',          'Sweets',      140.00, TRUE, FALSE, NULL),
(2, 'Italian Blood Orange Soda',   'Chilled sparkling Sicilian blood orange soda',                       'Drinks',       65.00, TRUE, FALSE, NULL),
(3, 'Double Smash Burger',         'Two seared beef patties, aged cheddar, pickles, brioche bun',        'Main Course', 280.00, TRUE, TRUE,  15.00),
(3, 'Truffle Mushroom Burger',     'Beef patty, sauteed cremini mushrooms, Swiss cheese, truffle aioli', 'Main Course', 310.00, TRUE, FALSE, NULL),
(3, 'Craft Mint Lemonade',         'House-pressed lemon juice infused with fresh mint leaves',           'Drinks',       75.00, TRUE, FALSE, NULL),
(3, 'Loaded Cheese Fries',         'Crispy skin-on fries topped with cheddar sauce and jalapenos',       'Other',       110.00, TRUE, FALSE, NULL),
(4, 'Salmon Nigiri Set (8 pcs)',   'Fresh Atlantic salmon over seasoned sushi rice with wasabi',         'Main Course', 360.00, TRUE, FALSE, NULL),
(4, 'California Roll (8 pcs)',     'Crab stick, avocado, and cucumber rolled in toasted sesame',         'Main Course', 280.00, TRUE, TRUE,  10.00),
(4, 'Matcha Iced Tea',             'Ceremonial grade Japanese green tea served cold over ice',           'Drinks',       95.00, TRUE, FALSE, NULL),
(5, 'Grilled Chicken Caesar Bowl', 'Herb-grilled chicken breast, romaine, parmesan, sourdough croutons', 'Main Course', 240.00, TRUE, FALSE, NULL),
(5, 'Cold-Pressed Green Detox',    'Spinach, green apple, cucumber, celery, and fresh ginger',           'Drinks',      110.00, TRUE, FALSE, NULL),
(5, 'Chia Berry Parfait',          'Organic chia pudding topped with fresh berries and honey granola',   'Sweets',      125.00, TRUE, TRUE,  20.00);

-- 13. Orders (6 records, including Pick_up with NULL delivery_address_id)
INSERT INTO orders (restaurant_id, customer_id, delivery_address_id, delivery_type, payment_method, order_date, order_status, estimated_delivery_time, total_price) VALUES
(1, 1, 6,    'Platform_carrier',   'Online',           NOW() - INTERVAL '4 days',  'Delivered',          28, 650.00),
(2, 2, 8,    'Restaurant_carrier', 'Card at the door', NOW() - INTERVAL '3 days',  'Delivered',          24, 580.00),
(3, 3, 9,    'Platform_carrier',   'Online',           NOW() - INTERVAL '2 days',  'Delivered',          22, 736.00),
(4, 1, 6,    'Platform_carrier',   'Online',           NOW() - INTERVAL '4 hours', 'Preparing',          38, 612.00),
(2, 1, NULL, 'Pick_up',            'Cash at the door', NOW() - INTERVAL '1 hour',  'Order Confirmed', 15, 365.00),
(5, 4, 10,   'Restaurant_carrier', 'Online',           NOW() - INTERVAL '1 day',   'Delivered',          26, 450.00);

-- 14. Order Items (14 records matching exact total_price of each order)
INSERT INTO order_items (order_id, product_id, unit_price, quantity) VALUES
(1,  1, 280.00, 2),
(1,  3,  45.00, 2),
(2,  6, 300.00, 1),
(2,  7, 140.00, 2),
(3,  9, 238.00, 2),
(3, 11,  75.00, 2),
(3, 12, 110.00, 1),
(4, 13, 360.00, 1),
(4, 14, 252.00, 1),
(5,  5, 225.00, 1),
(5,  7, 140.00, 1),
(6, 16, 240.00, 1),
(6, 17, 110.00, 1),
(6, 18, 100.00, 1);

-- 15. Restaurant Reviews (4 records, 1-to-1 with Delivered orders)
INSERT INTO restaurant_review (customer_id, restaurant_id, order_id, rating, comment, date) VALUES
(1, 1, 1, 5, 'Adana kebab arrived piping hot and super flavorful. Fast delivery to Incek!', NOW() - INTERVAL '3 days'),
(2, 2, 2, 5, 'Authentic woodfire crust and the tiramisu is incredible.',                  NOW() - INTERVAL '2 days'),
(3, 3, 3, 4, 'Crispy double smash patty and generous cheese fries.',                      NOW() - INTERVAL '1 day'),
(4, 5, 6, 5, 'Super fresh ingredients and quick restaurant courier delivery.',            NOW() - INTERVAL '18 hours');
