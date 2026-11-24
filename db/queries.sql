-- ============================================================================
-- CMPE341 - Chapter 5: Complex SQL Queries (Group 15)
-- Online Food Ordering System (PostgreSQL)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- QUERY 1: Multi-table JOIN
-- Displays detailed order summaries by joining orders, users, restaurants,
-- order_items, menu_items, and payments.
-- ----------------------------------------------------------------------------
SELECT
    o.order_id,
    u.full_name          AS customer_name,
    r.name               AS restaurant_name,
    STRING_AGG(m.name || ' (x' || oi.quantity || ')', ', ' ORDER BY m.name) AS ordered_items,
    o.status             AS order_status,
    p.payment_method,
    p.payment_status,
    o.total_amount
FROM orders o
INNER JOIN users u        ON o.user_id       = u.user_id
INNER JOIN restaurants r  ON o.restaurant_id = r.restaurant_id
INNER JOIN order_items oi ON o.order_id      = oi.order_id
INNER JOIN menu_items m   ON oi.item_id      = m.item_id
LEFT  JOIN payments p     ON o.order_id      = p.order_id
GROUP BY o.order_id, u.full_name, r.name, o.status, p.payment_method, p.payment_status, o.total_amount
ORDER BY o.order_date DESC;


-- ----------------------------------------------------------------------------
-- QUERY 2: GROUP BY + ORDER BY
-- Aggregates total orders, total revenue, average order value, and average
-- customer rating per restaurant, sorted by total revenue descending.
-- ----------------------------------------------------------------------------
SELECT
    r.restaurant_id,
    r.name                                                      AS restaurant_name,
    r.cuisine_type,
    COUNT(o.order_id)                                           AS total_orders,
    COALESCE(SUM(o.total_amount), 0.00)                         AS total_revenue,
    COALESCE(ROUND(AVG(o.total_amount), 2), 0.00)               AS avg_order_value,
    COALESCE(rev_stats.avg_rating, 0.00)                        AS avg_rating
FROM restaurants r
LEFT JOIN orders o
       ON r.restaurant_id = o.restaurant_id AND o.status <> 'Cancelled'
LEFT JOIN (
    SELECT restaurant_id, ROUND(AVG(rating), 2) AS avg_rating
    FROM reviews
    GROUP BY restaurant_id
) rev_stats
       ON r.restaurant_id = rev_stats.restaurant_id
GROUP BY r.restaurant_id, r.name, r.cuisine_type, rev_stats.avg_rating
ORDER BY total_revenue DESC, avg_rating DESC;


-- ----------------------------------------------------------------------------
-- QUERY 3: Subquery
-- Finds customers whose total non-cancelled spending exceeds the overall
-- average customer spending across all customers who have placed orders.
-- ----------------------------------------------------------------------------
SELECT
    u.user_id,
    u.username,
    u.full_name,
    COUNT(o.order_id)             AS order_count,
    SUM(o.total_amount)           AS total_spent,
    ROUND((
        SELECT AVG(customer_total)
        FROM (
            SELECT SUM(total_amount) AS customer_total
            FROM orders
            WHERE status <> 'Cancelled'
            GROUP BY user_id
        ) AS sub_avg
    ), 2)                         AS avg_customer_spending
FROM users u
INNER JOIN orders o ON u.user_id = o.user_id
WHERE o.status <> 'Cancelled'
GROUP BY u.user_id, u.username, u.full_name
HAVING SUM(o.total_amount) > (
    SELECT AVG(customer_total)
    FROM (
        SELECT SUM(total_amount) AS customer_total
        FROM orders
        WHERE status <> 'Cancelled'
        GROUP BY user_id
    ) AS avg_calc
)
ORDER BY total_spent DESC;
