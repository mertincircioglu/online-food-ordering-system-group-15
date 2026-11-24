# BiteFlow — Online Food Ordering System (Group 15)

**Course:** CMPE341 — Database Design & Management (Atılım University, 2026–2027 Fall)  
**Group:** Group 15  
**Topic:** Online Food Ordering System  

A fully Dockerized, role-based web application backed by **PostgreSQL 16** and **FastAPI** demonstrating normalized relational database design (8 entities), bcrypt password authentication, role-based access control (RBAC), full CRUD (`INSERT`, `UPDATE`, `DELETE`) operations, and complex SQL analytical queries.

---

## Quick Start (Single Command)

Make sure [Docker](https://www.docker.com/) and Docker Compose are installed, then run:

```bash
git clone https://github.com/mertincircioglu/online-food-ordering-system-group-15.git
cd online-food-ordering-system-group-15
docker compose up --build
```

Once the containers are running, open the application in your browser at:

- **Web Application URL:** `http://localhost:8000`
- **Admin Dashboard URL:** `http://localhost:8000/admin`

> PostgreSQL automatically executes [`db/init.sql`](db/init.sql) on first startup, creating all 8 tables with constraints and seeding realistic sample records (at least 5+ rows per table).

---

## Test Accounts (Roles & Credentials)

All passwords are stored securely using **bcrypt** (cost factor 12).

| Role | Username | Password | Permissions |
| :--- | :--- | :--- | :--- |
| **Admin** | `admin` | `admin123` | Full Admin Panel access: Insert/Update/Delete restaurants, categories, menu items; update/delete orders & payment statuses; manage user roles; view live SQL analytics (`JOIN`, `GROUP BY + ORDER BY`, `Subquery`). |
| **Customer** | `customer1` | `customer123` | Browse active restaurants & menus, place orders (transactional insert across `orders`, `order_items`, `payments`), update/cancel own `Pending` orders, insert/update/delete own reviews, update profile. Blocked (`403 Forbidden`) from `/admin/*`. |

Additional seeded accounts:
- Admin: `manager` / `manager123`
- Customers: `ayse`, `can`, `zeynep` (password: `customer123`)

---

## Database Schema (8 Entities)

1. **`users`** — Accounts, bcrypt password hashes, roles (`admin`, `customer`), contact & delivery address
2. **`restaurants`** — Partner kitchens, cuisine type, delivery time, minimum order, active status
3. **`categories`** — Menu categories (Main Courses, Pizzas, Burgers, Sushi & Rolls, Salads & Bowls, Beverages & Desserts)
4. **`menu_items`** — Dishes linked to a restaurant and category with price and availability
5. **`orders`** — Customer orders with lifecycle status (`Pending`, `Preparing`, `On The Way`, `Delivered`, `Cancelled`)
6. **`order_items`** — Line items resolving the M:N relationship between `orders` and `menu_items`
7. **`payments`** — 1:1 payment record per order (`Credit Card`, `Cash on Delivery`, `Online Wallet`)
8. **`reviews`** — Customer ratings (1–5) and comments per restaurant

SQL files:
- Schema & Seed Data: [`db/init.sql`](db/init.sql)
- Required Complex SQL Queries: [`db/queries.sql`](db/queries.sql) (also viewable live in `/admin`)
- ER / Logical Diagram Source (dbdiagram.io): [`docs/er-diagram.dbml`](docs/er-diagram.dbml)

---

## Cloud Deployment (Linux VM — Port 80)

To expose the web application directly on HTTP port 80 on a Linux VM:

```bash
git clone https://github.com/mertincircioglu/online-food-ordering-system-group-15.git
cd online-food-ordering-system-group-15
APP_PORT=80 docker compose up -d --build
```

Ensure inbound TCP port **80** is allowed in both your cloud firewall (NSG / Security Group) and the VM firewall (`sudo ufw allow 80/tcp`).

---

## Resetting the Database

To wipe the database volume and re-run `db/init.sql` cleanly from scratch:

```bash
docker compose down -v
docker compose up --build
```
