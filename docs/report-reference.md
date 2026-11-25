# CMPE341 Report Technical Reference (Group 15 — Updated 15-Table Model)

All PostgreSQL tables, queries, and web app features are synchronized 1-to-1 with your Chapter 3 EER Diagram (10 entities) and Chapter 4 Logical Data Model (15 normalized tables).

---

## Relational Schema Mapping (15 Normalized Tables)

1. **member**(**member_id**, email [UNIQUE], first_name, middle_name, last_name, password_hash, phone_number, is_banned)
2. **admin**(**admin_id**, member_id [UNIQUE, FK → member.member_id])
3. **customer**(**customer_id**, member_id [UNIQUE, FK → member.member_id], gender)
4. **restaurant_manager**(**manager_id**, member_id [UNIQUE, FK → member.member_id], restaurant_id [FK → restaurant.restaurant_id])
5. **address**(**address_id**, address_title, province, district, subdistrict, neighborhood, street, floor, building_no, latitude, longitude, details)
6. **customer_address**(**customer_id** [FK → customer.customer_id], **address_id** [FK → address.address_id])
7. **customer_payment_info**(**payment_info_id**, customer_id [FK → customer.customer_id], saved_payment_info)
8. **restaurant**(**restaurant_id**, address_id [UNIQUE, FK → address.address_id], name, phone_number, email, min_order_amount)
9. **restaurant_working_hours**(**restaurant_id** [FK → restaurant.restaurant_id], **day**, opening_time, closing_time)
10. **restaurant_delivery_type**(**restaurant_id** [FK → restaurant.restaurant_id], **delivery_type**)
11. **restaurant_cuisine**(**restaurant_id** [FK → restaurant.restaurant_id], **cuisine_type**)
12. **product**(**product_id**, restaurant_id [FK → restaurant.restaurant_id], product_name, description, category, price, is_available, discount_available, discount_percentage)
13. **orders**(**order_id**, restaurant_id [FK → restaurant.restaurant_id], customer_id [FK → customer.customer_id], delivery_address_id [FK → address.address_id, NULL for Pick_up], delivery_type, payment_method, order_date, order_status, estimated_delivery_time, total_price)
14. **order_items**(**order_id** [FK → orders.order_id], **product_id** [FK → product.product_id], unit_price, quantity)
15. **restaurant_review**(**restaurant_review_id**, customer_id [FK → customer.customer_id], restaurant_id [FK → restaurant.restaurant_id], order_id [UNIQUE, FK → orders.order_id], rating, comment, date)

> Note: The conceptual `Order` entity is implemented as `orders` in PostgreSQL because `ORDER` is a reserved SQL keyword. `Restaurant.Rating` is dynamically derived from `AVG(restaurant_review.rating)` rather than redundantly stored.

---

## Chapter 5: Complex Queries ([`db/queries.sql`](../db/queries.sql))

1. **Multi-table JOIN (7 tables):** Joins `orders`, `customer`, `member`, `restaurant`, `order_items`, `product`, and `address` to produce a complete order ledger with product summaries and delivery locations (handling `Self Pick-up` when `delivery_address_id IS NULL`).
2. **GROUP BY + ORDER BY:** Aggregates order count, total revenue, average order value, cuisine list, and derived average rating per restaurant, sorted by revenue descending.
3. **Subquery:** Finds customers whose total non-cancelled order spending exceeds the platform-wide average customer spending.
