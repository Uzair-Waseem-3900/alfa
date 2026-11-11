# Inventory

- `quantity` is the total units of a product across all shelves.
- Low stock = 1 to 5 units. Out of stock = 0 units (or less). These are fixed thresholds in the software.
- `avg_unit_cost` is the average cost per unit of stock on hand. Stock value = quantity x avg_unit_cost; the software's own "inventory value" (used in business_worth) is valued from purchase batches (FIFO), so it can differ slightly from this simple multiplication.
- Shelf locations and purchase history are not available through tools yet.
