# CMPE341 Report Technical Reference (Group 15)

Use this reference while writing your Word report manually in English.

---

## Chapter 3: ER/EER Model Summary (8 Entities)

**Entities (strictly within the 5–10 limit):**
1. **USERS** — Stores registered customers and system administrators (`user_id`, `username`, `email`, `password_hash`, `role`, `full_name`, `phone`, `address`, `created_at`).
2. **RESTAURANTS** — Stores partner restaurants (`restaurant_id`, `name`, `cuisine_type`, `address`, `phone`, `delivery_time_min`, `min_order_amount`, `is_active`, `created_at`).
3. **CATEGORIES** — Groups dishes into menu categories (`category_id`, `name`, `description`).
4. **MENU_ITEMS** — Individual dishes offered by a restaurant (`item_id`, `restaurant_id`, `category_id`, `name`, `description`, `price`, `is_available`).
5. **ORDERS** — Customer food orders (`order_id`, `user_id`, `restaurant_id`, `order_date`, `status`, `total_amount`, `delivery_address`, `notes`).
6. **ORDER_ITEMS** — Associative entity resolving the M:N relationship between `ORDERS` and `MENU_ITEMS` (`order_item_id`, `order_id`, `item_id`, `quantity`, `unit_price`).
7. **PAYMENTS** — Payment record linked 1:1 to each order (`payment_id`, `order_id`, `payment_method`, `payment_status`, `amount`, `paid_at`).
8. **REVIEWS** — Customer ratings and textual reviews for restaurants (`review_id`, `user_id`, `restaurant_id`, `rating`, `comment`, `created_at`).

**Key Relationships & Cardinalities:**
- `USERS` (1) — (0..N) `ORDERS` (*places*)
- `RESTAURANTS` (1) — (0..N) `ORDERS` (*receives*)
- `RESTAURANTS` (1) — (0..N) `MENU_ITEMS` (*offers*)
- `CATEGORIES` (1) — (0..N) `MENU_ITEMS` (*classifies*)
- `ORDERS` (1) — (1..N) `ORDER_ITEMS` — (N..1) `MENU_ITEMS` (*contains*)
- `ORDERS` (1) — (1) `PAYMENTS` (*paid via*)
- `USERS` (1) — (0..N) `REVIEWS` (*writes*)
- `RESTAURANTS` (1) — (0..N) `REVIEWS` (*receives*)

> Tip: Paste [`docs/er-diagram.dbml`](er-diagram.dbml) into [dbdiagram.io](https://dbdiagram.io/d) to export a high-resolution diagram for your report.

---

## Chapter 4: Logical Design (Relational Schema Mapping)

Primary keys are **bolded**; foreign keys are marked with `(FK)`.

- **users**(**user_id**, username [UNIQUE], email [UNIQUE], password_hash, role, full_name, phone, address, created_at)
- **restaurants**(**restaurant_id**, name, cuisine_type, address, phone, delivery_time_min, min_order_amount, is_active, created_at)
- **categories**(**category_id**, name [UNIQUE], description)
- **menu_items**(**item_id**, restaurant_id *(FK → restaurants.restaurant_id)*, category_id *(FK → categories.category_id)*, name, description, price, is_available)
- **orders**(**order_id**, user_id *(FK → users.user_id)*, restaurant_id *(FK → restaurants.restaurant_id)*, order_date, status, total_amount, delivery_address, notes)
- **order_items**(**order_item_id**, order_id *(FK → orders.order_id)*, item_id *(FK → menu_items.item_id)*, quantity, unit_price) — `UNIQUE(order_id, item_id)`
- **payments**(**payment_id**, order_id [UNIQUE] *(FK → orders.order_id)*, payment_method, payment_status, amount, paid_at)
- **reviews**(**review_id**, user_id *(FK → users.user_id)*, restaurant_id *(FK → restaurants.restaurant_id)*, rating, comment, created_at)

All tables satisfy **Third Normal Form (3NF)**: atomic attributes (1NF), no partial dependencies on composite keys (2NF), and no transitive non-key dependencies (3NF). Historical `unit_price` is intentionally snapshot-stored in `order_items` so future menu price updates do not corrupt past order invoices.

---

## Chapter 5: Physical Design & Complex Queries

- **DBMS:** PostgreSQL 16 (`postgres:16-alpine`)
- **DDL & Seed Data:** [`db/init.sql`](../db/init.sql) — includes `PRIMARY KEY`, `FOREIGN KEY` (`ON DELETE CASCADE` / `ON DELETE RESTRICT`), `UNIQUE`, `NOT NULL`, `CHECK` constraints, and 5–15 rows per table.
- **3 Complex Queries:** [`db/queries.sql`](../db/queries.sql)
  1. **Multi-table JOIN:** Joins 6 tables (`orders`, `users`, `restaurants`, `order_items`, `menu_items`, `payments`) to build a complete order ledger.
  2. **GROUP BY + ORDER BY:** Calculates per-restaurant order count, total revenue, average order value, and average rating, ranked by revenue descending.
  3. **Subquery:** Finds customers whose total non-cancelled order spending exceeds the platform-wide average customer spending.
