-- ============================================================================
-- CMPE341 Database Design & Management - Group 15
-- Project: BiteFlow - Online Food Ordering System
-- Database: PostgreSQL 16
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ----------------------------------------------------------------------------
-- 1. USERS
-- ----------------------------------------------------------------------------
CREATE TABLE users (
    user_id       SERIAL PRIMARY KEY,
    username      VARCHAR(50)  NOT NULL UNIQUE,
    email         VARCHAR(120) NOT NULL UNIQUE,
    password_hash TEXT         NOT NULL,
    role          VARCHAR(20)  NOT NULL DEFAULT 'customer'
                  CHECK (role IN ('admin', 'customer')),
    full_name     VARCHAR(100) NOT NULL,
    phone         VARCHAR(25)  NOT NULL,
    address       TEXT         NOT NULL,
    created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- 2. RESTAURANTS
-- ----------------------------------------------------------------------------
CREATE TABLE restaurants (
    restaurant_id    SERIAL PRIMARY KEY,
    name             VARCHAR(100)   NOT NULL,
    cuisine_type     VARCHAR(50)    NOT NULL,
    address          TEXT           NOT NULL,
    phone            VARCHAR(25)    NOT NULL,
    delivery_time_min INT           NOT NULL DEFAULT 30 CHECK (delivery_time_min > 0),
    min_order_amount NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (min_order_amount >= 0),
    is_active        BOOLEAN        NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- 3. CATEGORIES
-- ----------------------------------------------------------------------------
CREATE TABLE categories (
    category_id SERIAL PRIMARY KEY,
    name        VARCHAR(60)  NOT NULL UNIQUE,
    description VARCHAR(255)
);

-- ----------------------------------------------------------------------------
-- 4. MENU_ITEMS
-- ----------------------------------------------------------------------------
CREATE TABLE menu_items (
    item_id       SERIAL PRIMARY KEY,
    restaurant_id INT            NOT NULL REFERENCES restaurants(restaurant_id) ON DELETE CASCADE,
    category_id   INT            NOT NULL REFERENCES categories(category_id)    ON DELETE RESTRICT,
    name          VARCHAR(100)   NOT NULL,
    description   TEXT,
    price         NUMERIC(10, 2) NOT NULL CHECK (price > 0),
    is_available  BOOLEAN        NOT NULL DEFAULT TRUE
);

-- ----------------------------------------------------------------------------
-- 5. ORDERS
-- ----------------------------------------------------------------------------
CREATE TABLE orders (
    order_id         SERIAL PRIMARY KEY,
    user_id          INT            NOT NULL REFERENCES users(user_id)             ON DELETE CASCADE,
    restaurant_id    INT            NOT NULL REFERENCES restaurants(restaurant_id) ON DELETE CASCADE,
    order_date       TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status           VARCHAR(20)    NOT NULL DEFAULT 'Pending'
                     CHECK (status IN ('Pending', 'Preparing', 'On The Way', 'Delivered', 'Cancelled')),
    total_amount     NUMERIC(10, 2) NOT NULL CHECK (total_amount >= 0),
    delivery_address TEXT           NOT NULL,
    notes            VARCHAR(255)
);

-- ----------------------------------------------------------------------------
-- 6. ORDER_ITEMS
-- ----------------------------------------------------------------------------
CREATE TABLE order_items (
    order_item_id SERIAL PRIMARY KEY,
    order_id      INT            NOT NULL REFERENCES orders(order_id)    ON DELETE CASCADE,
    item_id       INT            NOT NULL REFERENCES menu_items(item_id) ON DELETE CASCADE,
    quantity      INT            NOT NULL CHECK (quantity > 0),
    unit_price    NUMERIC(10, 2) NOT NULL CHECK (unit_price > 0),
    UNIQUE (order_id, item_id)
);

-- ----------------------------------------------------------------------------
-- 7. PAYMENTS
-- ----------------------------------------------------------------------------
CREATE TABLE payments (
    payment_id     SERIAL PRIMARY KEY,
    order_id       INT            NOT NULL UNIQUE REFERENCES orders(order_id) ON DELETE CASCADE,
    payment_method VARCHAR(30)    NOT NULL
                   CHECK (payment_method IN ('Credit Card', 'Cash on Delivery', 'Online Wallet')),
    payment_status VARCHAR(20)    NOT NULL DEFAULT 'Pending'
                   CHECK (payment_status IN ('Pending', 'Completed', 'Refunded')),
    amount         NUMERIC(10, 2) NOT NULL CHECK (amount >= 0),
    paid_at        TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- 8. REVIEWS
-- ----------------------------------------------------------------------------
CREATE TABLE reviews (
    review_id     SERIAL PRIMARY KEY,
    user_id       INT       NOT NULL REFERENCES users(user_id)             ON DELETE CASCADE,
    restaurant_id INT       NOT NULL REFERENCES restaurants(restaurant_id) ON DELETE CASCADE,
    rating        INT       NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment       TEXT      NOT NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Helpful Indexes for Query Performance
CREATE INDEX idx_menu_items_restaurant ON menu_items(restaurant_id);
CREATE INDEX idx_menu_items_category   ON menu_items(category_id);
CREATE INDEX idx_orders_user           ON orders(user_id);
CREATE INDEX idx_orders_restaurant     ON orders(restaurant_id);
CREATE INDEX idx_reviews_restaurant    ON reviews(restaurant_id);

-- ============================================================================
-- SEED DATA (Minimum 3+ realistic records per table)
-- Passwords hashed with bcrypt (cost 12) via pgcrypto
-- ============================================================================

-- Users (Test accounts: admin/admin123, customer1/customer123)
INSERT INTO users (username, email, password_hash, role, full_name, phone, address) VALUES
('admin',     'admin@biteflow.com',     crypt('admin123',    gen_salt('bf', 12)), 'admin',    'System Administrator', '+90 532 100 0001', 'Kizilcasar Mah. Incek, Golbasi, Ankara'),
('manager',   'manager@biteflow.com',   crypt('manager123',  gen_salt('bf', 12)), 'admin',    'Operations Manager',   '+90 532 100 0002', 'Cankaya Cad. No:45, Ankara'),
('customer1', 'mert@atilim.edu.tr',     crypt('customer123', gen_salt('bf', 12)), 'customer', 'Mert Incircioglu',     '+90 533 200 1001', 'Incek Vista Sitesi B Blok D:12, Golbasi, Ankara'),
('ayse',      'ayse@atilim.edu.tr',     crypt('customer123', gen_salt('bf', 12)), 'customer', 'Ayse Demir',           '+90 533 200 1002', 'Turan Gunes Bulvari No:88, Cankaya, Ankara'),
('can',       'can@atilim.edu.tr',      crypt('customer123', gen_salt('bf', 12)), 'customer', 'Can Yilmaz',           '+90 533 200 1003', 'Bahcelievler 7. Cadde No:24, Ankara'),
('zeynep',    'zeynep@atilim.edu.tr',   crypt('customer123', gen_salt('bf', 12)), 'customer', 'Zeynep Kaya',          '+90 533 200 1004', 'Umitkoy Galleria Yani No:14, Yenimahalle, Ankara');

-- Restaurants
INSERT INTO restaurants (name, cuisine_type, address, phone, delivery_time_min, min_order_amount, is_active) VALUES
('Anatolia Grill House',    'Turkish Kebab',    'Incek Bulvari No:112, Golbasi, Ankara',     '+90 312 460 1100', 30, 150.00, TRUE),
('Napoli Woodfire Pizzeria','Italian Pizza',    'Tunalihilmi Cad. No:54, Cankaya, Ankara',   '+90 312 428 2200', 25, 180.00, TRUE),
('Smash & Craft Burgers',   'American Burgers', 'Bahcelievler 3. Cadde No:19, Ankara',       '+90 312 215 3300', 20, 160.00, TRUE),
('Sakura Sushi Bar',        'Japanese Sushi',   'Gaziosmanpasa Filistin Sok. No:8, Ankara',  '+90 312 446 4400', 40, 250.00, TRUE),
('Green Bowl Kitchen',      'Healthy & Salads', 'Cayyolu Park Cad. No:31, Ankara',           '+90 312 240 5500', 25, 120.00, TRUE);

-- Categories
INSERT INTO categories (name, description) VALUES
('Main Courses',         'Hearty traditional grilled and oven-baked entrees'),
('Pizzas',               'Artisanal wood-fired thin crust pizzas'),
('Burgers',              'Hand-smashed brioche burgers with signature sauces'),
('Sushi & Rolls',        'Freshly prepared nigiri, sashimi, and maki rolls'),
('Salads & Bowls',       'Nutrient-rich fresh salads and warm grain bowls'),
('Beverages & Desserts', 'Refreshing drinks and handcrafted sweet treats');

-- Menu Items
INSERT INTO menu_items (restaurant_id, category_id, name, description, price, is_available) VALUES
(1, 1, 'Adana Kebab',                'Charcoal-grilled spicy minced lamb served with lavash and roasted peppers', 280.00, TRUE),
(1, 1, 'Iskender Kebab',             'Sliced doner over pita bread topped with tomato sauce and melted butter',    320.00, TRUE),
(1, 6, 'Traditional Ayran',          'Chilled frothy yogurt drink lightly salted',                                  45.00, TRUE),
(2, 2, 'Margherita Classica',        'San Marzano tomato sauce, fresh buffalo mozzarella, and sweet basil',       240.00, TRUE),
(2, 2, 'Pepperoni Diavola',          'Crispy beef pepperoni, mozzarella, oregano, and chili oil drizzle',         295.00, TRUE),
(2, 6, 'Classic Tiramisu',           'Espresso-soaked ladyfingers layered with mascarpone cream',                 130.00, TRUE),
(3, 3, 'Double Smash Burger',        'Two seared beef patties, aged cheddar, pickles, caramelized onion, brioche',265.00, TRUE),
(3, 3, 'Truffle Mushroom Burger',    'Juicy beef patty, sauteed cremini mushrooms, Swiss cheese, truffle aioli',  290.00, TRUE),
(3, 6, 'Craft Mint Lemonade',        'House-pressed lemon juice infused with fresh mint leaves',                    75.00, TRUE),
(4, 4, 'Salmon Nigiri Set (8 pcs)',  'Fresh Atlantic salmon over seasoned sushi rice with wasabi and ginger',     360.00, TRUE),
(4, 4, 'California Roll (8 pcs)',    'Crab stick, ripe avocado, crisp cucumber rolled in toasted sesame',         270.00, TRUE),
(4, 6, 'Matcha Iced Tea',            'Ceremonial grade Japanese green tea served cold over ice',                    95.00, TRUE),
(5, 5, 'Grilled Chicken Caesar Bowl','Herb-grilled chicken breast, romaine, shaved parmesan, sourdough croutons', 230.00, TRUE),
(5, 5, 'Quinoa Avocado Power Bowl',  'Tri-color quinoa, Hass avocado, roasted chickpeas, tahini dressing',        250.00, TRUE),
(5, 6, 'Cold-Pressed Green Detox',   'Spinach, green apple, cucumber, celery, and fresh ginger',                  110.00, TRUE);

-- Orders
INSERT INTO orders (user_id, restaurant_id, order_date, status, total_amount, delivery_address, notes) VALUES
(3, 1, NOW() - INTERVAL '4 days',  'Delivered', 650.00, 'Incek Vista Sitesi B Blok D:12, Golbasi, Ankara', 'Extra sumac onions please'),
(4, 2, NOW() - INTERVAL '3 days',  'Delivered', 555.00, 'Turan Gunes Bulvari No:88, Cankaya, Ankara',      'Ring the bell twice'),
(5, 3, NOW() - INTERVAL '2 days',  'Delivered', 680.00, 'Bahcelievler 7. Cadde No:24, Ankara',             'No pickles on the second burger'),
(3, 4, NOW() - INTERVAL '5 hours', 'Preparing', 630.00, 'Incek Vista Sitesi B Blok D:12, Golbasi, Ankara', 'Include extra soy sauce and chopsticks'),
(3, 2, NOW() - INTERVAL '1 hour',  'Pending',   370.00, 'Incek Vista Sitesi B Blok D:12, Golbasi, Ankara', 'Leave at security gate if unavailable'),
(6, 5, NOW() - INTERVAL '1 day',   'Delivered', 340.00, 'Umitkoy Galleria Yani No:14, Yenimahalle, Ankara','Dressing on the side please');

-- Order Items
INSERT INTO order_items (order_id, item_id, quantity, unit_price) VALUES
(1,  1, 2, 280.00),
(1,  3, 2,  45.00),
(2,  5, 1, 295.00),
(2,  6, 2, 130.00),
(3,  7, 2, 265.00),
(3,  9, 2,  75.00),
(4, 10, 1, 360.00),
(4, 11, 1, 270.00),
(5,  4, 1, 240.00),
(5,  6, 1, 130.00),
(6, 13, 1, 230.00),
(6, 15, 1, 110.00);

-- Payments
INSERT INTO payments (order_id, payment_method, payment_status, amount, paid_at) VALUES
(1, 'Credit Card',      'Completed', 650.00, NOW() - INTERVAL '4 days'),
(2, 'Online Wallet',    'Completed', 555.00, NOW() - INTERVAL '3 days'),
(3, 'Credit Card',      'Completed', 680.00, NOW() - INTERVAL '2 days'),
(4, 'Credit Card',      'Completed', 630.00, NOW() - INTERVAL '5 hours'),
(5, 'Cash on Delivery', 'Pending',   370.00, NULL),
(6, 'Online Wallet',    'Completed', 340.00, NOW() - INTERVAL '1 day');

-- Reviews
INSERT INTO reviews (user_id, restaurant_id, rating, comment, created_at) VALUES
(3, 1, 5, 'Adana kebab arrived piping hot and super flavorful. Fast delivery to Incek!', NOW() - INTERVAL '3 days'),
(4, 2, 5, 'Authentic wood-fired crust and the tiramisu is incredible.',                 NOW() - INTERVAL '2 days'),
(5, 3, 4, 'Crispy edges on the double smash patty, lemonade was very refreshing.',      NOW() - INTERVAL '1 day'),
(3, 4, 5, 'Very fresh salmon nigiri and neat packaging.',                               NOW() - INTERVAL '4 hours'),
(6, 5, 4, 'Portion size was generous and ingredients tasted super fresh.',              NOW() - INTERVAL '18 hours'),
(4, 1, 4, 'Great Iskender kebab, arrived slightly earlier than estimated.',             NOW() - INTERVAL '12 hours');
