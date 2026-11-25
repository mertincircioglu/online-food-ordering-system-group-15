# BiteFlow — Online Food Ordering System (Group 15)

**Course:** CMPE341 — Database Design & Management (Atılım University, 2026–2027 Fall)  
**Group:** Group 15  
**Topic:** Online Food Ordering System  

A fully Dockerized, 3-role web application backed by **PostgreSQL 16** and **FastAPI** implementing our **10-entity EER Diagram** mapped to **15 Normalized Relational Tables**, with bcrypt password authentication, strict role-based access control (RBAC), full CRUD (`INSERT`, `UPDATE`, `DELETE`) operations, coordinate-based delivery time estimation, and complex SQL analytical queries.

---

## Quick Start (Single Command)

Make sure [Docker](https://www.docker.com/) and Docker Compose are installed, then run:

```bash
git clone https://github.com/mertincircioglu/online-food-ordering-system-group-15.git
cd online-food-ordering-system-group-15
docker compose up --build
```

Once the containers are running, open the application in your browser at:

- **Storefront URL:** `http://localhost:8000`
- **Login URL:** `http://localhost:8000/login`
- **Admin Panel URL:** `http://localhost:8000/admin`
- **Restaurant Manager Portal URL:** `http://localhost:8000/manager`

> PostgreSQL automatically executes [`db/init.sql`](db/init.sql) on first startup, creating all **15 normalized tables** with constraints and seeding at least 3+ realistic records in every table.

---

## Test Accounts (Roles & Credentials)

All passwords are stored securely using **bcrypt** (cost factor 12). Sign in using the **Email** as username:

| Role | Email (Username) | Password | Permissions |
| :--- | :--- | :--- | :--- |
| **Admin** | `admin@biteflow.com` | `admin123` | System-wide CRUD on restaurants (address, cuisines, delivery types, working hours), products, orders, reviews moderation, members & restaurant managers, plus live SQL analytics (`7-table JOIN`, `GROUP BY + ORDER BY`, `Subquery`). |
| **Restaurant Manager** | `manager1@biteflow.com` | `manager123` | Dedicated Manager Portal for **Anatolia Grill House**: update restaurant profile/cuisines/delivery types, Insert/Update/Delete own menu products & discounts, update incoming order statuses, view customer reviews. |
| **Customer** | `customer1@atilim.edu.tr` | `customer123` | Search/filter restaurants by cuisine & delivery type, place orders (delivery or self pick-up), update/cancel own `Order Confirmation` orders, submit/edit/delete 1:1 reviews on `Delivered` orders, manage saved delivery addresses & payment methods. Blocked (`403 Forbidden`) from `/admin/*` and `/manager/*`. |

Additional seeded accounts:
- Admins: `ops@biteflow.com`, `support@biteflow.com` (`admin123`)
- Restaurant Managers: `manager2@biteflow.com` (Napoli), `manager3@biteflow.com` (Smash & Craft), `manager4@biteflow.com` (Sakura) (`manager123`)
- Customers: `ayse@atilim.edu.tr`, `can@atilim.edu.tr`, `zeynep@atilim.edu.tr` (`customer123`)

---

## Database Schema (15 Normalized Tables from 10-Entity EER Model)

1. **`member`** — Superclass holding email, name (`first_name`, `middle_name`, `last_name`), `password_hash`, `phone_number`
2. **`admin`** — Disjoint subclass of `member`
3. **`customer`** — Disjoint subclass of `member` (`gender`)
4. **`restaurant_manager`** — Disjoint subclass of `member`, linked to `restaurant`
5. **`address`** — Full structured address (`province`, `district`, `subdistrict`, `neighborhood`, `street`, `floor`, `building_no`, `latitude`, `longitude`, `details`)
6. **`customer_address`** — M:N saved delivery addresses per customer
7. **`customer_payment_info`** — Multi-valued saved payment methods per customer
8. **`restaurant`** — Partner restaurants (1:1 `address_id`, `min_order_amount`; rating dynamically derived from `restaurant_review`)
9. **`restaurant_working_hours`** — Weekly schedule (`day`, `opening_time`, `closing_time`)
10. **`restaurant_delivery_type`** — Supported delivery options (`Platform_carrier`, `Restaurant_carrier`, `Pick_up`)
11. **`restaurant_cuisine`** — Multi-valued cuisine tags per restaurant
12. **`product`** — Menu items (`category`, `price`, `is_available`, `discount_available`, `discount_percentage`)
13. **`orders`** — Customer orders (optional `delivery_address_id` for `Pick_up`, `delivery_type`, `payment_method`, `order_status`, `estimated_delivery_time`, `total_price`)
14. **`order_items`** — Composite PK `(order_id, product_id)` with snapshot `unit_price` and `quantity`
15. **`restaurant_review`** — 1:1 verified review per order (`order_id UNIQUE`, `rating` 1–5, optional `comment`)

SQL & Design files:
- Schema & Seed Data: [`db/init.sql`](db/init.sql)
- Required Complex SQL Queries: [`db/queries.sql`](db/queries.sql) (also executed live in `/admin`)
- Logical Schema DBML Source: [`docs/er-diagram.dbml`](docs/er-diagram.dbml)

---

## Cloud Deployment (Linux VM — Port 80)

```bash
git clone https://github.com/mertincircioglu/online-food-ordering-system-group-15.git
cd online-food-ordering-system-group-15
APP_PORT=80 docker compose up -d --build
```

Ensure inbound TCP port **80** is open in your cloud firewall (NSG / Security Group) and VM firewall (`sudo ufw allow 80/tcp`).

---

## Resetting the Database Volume

```bash
docker compose down -v
docker compose up --build
```
