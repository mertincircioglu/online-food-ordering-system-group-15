# BiteFlow — Online Food Ordering System (Group 15)

**Course:** CMPE341 — Database Design & Management (Atilim University, 2026–2027 Fall)
**Group:** Group 15  
**Topic:** Online Food Ordering System  

A fully Dockerized, 3-role web application backed by **PostgreSQL 16** and **FastAPI** implementing our **10-entity EER Diagram** mapped to **15 Normalized Relational Tables**, with bcrypt password authentication, strict role-based access control (RBAC), full CRUD (`INSERT`, `UPDATE`, `DELETE`) operations, coordinate-based delivery time estimation, Light/Dark mode, and complex SQL analytical queries.

---

## Live Deployment (AWS EC2 + Custom Domain)

- **Custom Domain (HTTPS):** https://biteflow.online
- **AWS EC2 Public IP (HTTP):** http://16.171.26.54

---

## Quick Start (Local — Single Command)

Make sure [Docker](https://www.docker.com/) and Docker Compose are installed, then run:

```bash
git clone https://github.com/mertincircioglu/online-food-ordering-system-group-15.git
cd online-food-ordering-system-group-15
docker compose up
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
| **Admin** | `admin@biteflow.com` | `admin123` | System-wide CRUD on restaurants (address, cuisines, delivery types, working hours), products, orders, reviews moderation, members & restaurant managers (**Ban / Unban** separate from **Delete**), plus live SQL analytics (`7-table JOIN`, `GROUP BY + ORDER BY`, `Subquery`) and 15-table database health summary. |
| **Restaurant Manager** | `manager1@biteflow.com` | `manager123` | Dedicated Manager Portal for **Anatolia Grill House**: update restaurant details/cuisines/delivery types and 7-day working hours, Insert/Update/Delete own menu products & discounts, manage active **Incoming Orders** (Delivered/Cancelled orders automatically move to **Past Orders**), view customer reviews. |
| **Customer** | `customer1@atilim.edu.tr` | `customer123` | Search/filter restaurants by cuisine & delivery type, filter menus by category or active discounts, place orders (delivery or self pick-up), update/cancel own `Order Confirmed` orders (or cancel delayed orders >1 hour), submit/edit/delete 1:1 reviews on `Delivered` orders, update profile/password and manage saved delivery addresses & payment methods. Blocked (`403 Forbidden`) from `/admin/*` and `/manager/*`. |

Additional seeded accounts:
- Admins: `ops@biteflow.com`, `support@biteflow.com` (`admin123`)
- Restaurant Managers: `manager2@biteflow.com` (Napoli Woodfire Pizzeria), `manager3@biteflow.com` (Smash & Craft Burgers), `manager4@biteflow.com` (Sakura Sushi Bar) (`manager123`)
- Customers: `ayse@atilim.edu.tr`, `can@atilim.edu.tr`, `zeynep@atilim.edu.tr` (`customer123`)

---

## Key Features & Security Highlights

- **3-Layer Input Validation:** Strict digits-only phone numbers (`10–15` digits) and valid email format enforced across HTML5 frontend, FastAPI backend, and PostgreSQL regex `CHECK` constraints.
- **Authentication & Authorization:** `bcrypt` password hashing, signed `HttpOnly` session cookies (`SameSite=Lax`, 12-hour expiry), strict server-side RBAC (`403 Forbidden`), and Admin **Ban / Unban** support (`member.is_banned`).
- **Hardened Web & Database Layer:** Login brute-force rate limiting (10 attempts / 5 min per IP), HTTP security headers (`X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`), parameterized SQL queries everywhere, and localhost-only PostgreSQL port binding (`127.0.0.1:5432`).
- **Modern UX:** Responsive food-tech UI with persistent **Light / Dark Mode** toggle.

---

## Database Schema (15 Normalized Tables from 10-Entity EER Model)

1. **`member`** — Superclass holding email, name (`first_name`, `middle_name`, `last_name`), `password_hash`, `phone_number`, `is_banned`
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

## Cloud Deployment (AWS EC2 Ubuntu + Caddy HTTPS)

Deployed on an AWS EC2 (`eu-north-1`, Ubuntu) Linux instance behind **Caddy** for automatic Let's Encrypt HTTPS on `https://biteflow.online` while also serving `http://16.171.26.54`:

```bash
git clone https://github.com/mertincircioglu/online-food-ordering-system-group-15.git
cd online-food-ordering-system-group-15
printf "SECRET_KEY=%s\nPOSTGRES_PASSWORD=%s\n" "$(openssl rand -hex 32)" "$(openssl rand -hex 16)" > .env
sudo docker compose up -d --build
```

---

## Resetting the Database Volume

```bash
docker compose down -v
docker compose up --build
```
