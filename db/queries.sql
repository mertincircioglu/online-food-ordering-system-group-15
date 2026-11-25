-- ============================================================================
-- CMPE341 - Chapter 5: Complex SQL Queries (Group 15)
-- Online Food Ordering System (PostgreSQL 16 - 15 Normalized Tables)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- QUERY 1: Multi-table JOIN
-- Joins orders, customer, member, restaurant, address, order_items, and product
-- to display a comprehensive order summary ledger with delivery location.
-- ----------------------------------------------------------------------------
SELECT
    o.order_id,
    m.first_name || ' ' || m.last_name AS customer_name,
    r.name                              AS restaurant_name,
    COALESCE(a.district || ', ' || a.neighborhood, 'Self Pick-up') AS delivery_location,
    o.delivery_type,
    o.payment_method,
    o.order_status,
    STRING_AGG(p.product_name || ' (x' || oi.quantity || ')', ', ' ORDER BY p.product_name) AS ordered_products,
    o.total_price
FROM orders o
INNER JOIN customer c     ON o.customer_id         = c.customer_id
INNER JOIN member m       ON c.member_id           = m.member_id
INNER JOIN restaurant r   ON o.restaurant_id       = r.restaurant_id
INNER JOIN order_items oi ON o.order_id            = oi.order_id
INNER JOIN product p      ON oi.product_id         = p.product_id
LEFT  JOIN address a      ON o.delivery_address_id = a.address_id
GROUP BY o.order_id, m.first_name, m.last_name, r.name, a.district, a.neighborhood,
         o.delivery_type, o.payment_method, o.order_status, o.total_price
ORDER BY o.order_date DESC;


-- ----------------------------------------------------------------------------
-- QUERY 2: GROUP BY + ORDER BY
-- Aggregates total non-cancelled orders, revenue, average order value,
-- cuisine list, and dynamically derived average rating per restaurant.
-- ----------------------------------------------------------------------------
SELECT
    r.restaurant_id,
    r.name                                          AS restaurant_name,
    COALESCE(cuisines.cuisine_list, 'General')      AS cuisines,
    COUNT(o.order_id)                               AS total_orders,
    COALESCE(SUM(o.total_price), 0.00)              AS total_revenue,
    COALESCE(ROUND(AVG(o.total_price), 2), 0.00)    AS avg_order_value,
    COALESCE(rev_stats.derived_rating, 0.00)        AS derived_rating
FROM restaurant r
LEFT JOIN orders o
       ON r.restaurant_id = o.restaurant_id AND o.order_status <> 'Cancelled'
LEFT JOIN (
    SELECT restaurant_id, ROUND(AVG(rating), 2) AS derived_rating
    FROM restaurant_review
    GROUP BY restaurant_id
) rev_stats
       ON r.restaurant_id = rev_stats.restaurant_id
LEFT JOIN (
    SELECT restaurant_id, STRING_AGG(cuisine_type, ', ' ORDER BY cuisine_type) AS cuisine_list
    FROM restaurant_cuisine
    GROUP BY restaurant_id
) cuisines
       ON r.restaurant_id = cuisines.restaurant_id
GROUP BY r.restaurant_id, r.name, cuisines.cuisine_list, rev_stats.derived_rating
ORDER BY total_revenue DESC, derived_rating DESC;


-- ----------------------------------------------------------------------------
-- QUERY 3: Subquery
-- Finds customers whose total non-cancelled order spending exceeds the overall
-- average spending across all customers who have placed orders.
-- ----------------------------------------------------------------------------
SELECT
    c.customer_id,
    m.email,
    m.first_name || ' ' || m.last_name AS customer_name,
    COUNT(o.order_id)                   AS order_count,
    SUM(o.total_price)                  AS total_spent,
    ROUND((
        SELECT AVG(customer_total)
        FROM (
            SELECT SUM(total_price) AS customer_total
            FROM orders
            WHERE order_status <> 'Cancelled'
            GROUP BY customer_id
        ) AS sub_avg
    ), 2)                               AS platform_avg_spending
FROM customer c
INNER JOIN member m ON c.member_id   = m.member_id
INNER JOIN orders o ON c.customer_id = o.customer_id
WHERE o.order_status <> 'Cancelled'
GROUP BY c.customer_id, m.email, m.first_name, m.last_name
HAVING SUM(o.total_price) > (
    SELECT AVG(customer_total)
    FROM (
        SELECT SUM(total_price) AS customer_total
        FROM orders
        WHERE order_status <> 'Cancelled'
        GROUP BY customer_id
    ) AS avg_calc
)
ORDER BY total_spent DESC;
