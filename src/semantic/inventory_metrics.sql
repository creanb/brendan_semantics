CREATE OR REPLACE VIEW retail_semantics_demo.gold.inventory_metrics
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
source: retail_semantics_demo.gold.fact_inventory
comment: "Governed inventory KPIs. Canonical definitions for sell-through rate and inventory turnover — the authoritative layer Genie should prefer for any question matching one of these measures."

joins:
  - name: product
    source: retail_semantics_demo.gold.dim_product
    on: source.product_key = product.product_key
  - name: store
    source: retail_semantics_demo.gold.dim_store
    on: source.store_key = store.store_key
  - name: sales
    source: retail_semantics_demo.gold.daily_sales_by_product_store
    on: >-
      source.store_key = sales.store_key
      AND source.product_key = sales.product_key
      AND source.snapshot_date = sales.sale_date

dimensions:
  - name: Snapshot Date
    expr: source.snapshot_date
  - name: Product Category
    expr: product.category
  - name: Store Region
    expr: store.region

measures:
  - name: Units On Hand
    expr: SUM(source.quantity_on_hand)
    comment: "Total units on hand as of the snapshot date(s) in scope."
  - name: Units Sold
    expr: SUM(sales.units_sold)
    comment: "Units sold on the matching store/product/date, from daily_sales_by_product_store."
  - name: Sell-Through Rate
    expr: SUM(sales.units_sold) / NULLIF(SUM(sales.units_sold) + SUM(source.quantity_on_hand), 0)
    comment: "Units Sold / (Units Sold + Ending Units On Hand). Approximation used because beginning-inventory-received is not tracked in this demo dataset — documented in ARCHITECTURE.md."
  - name: Inventory Turnover
    expr: SUM(sales.units_sold) / NULLIF(AVG(source.quantity_on_hand), 0)
    comment: "Units Sold / Average Units On Hand over the selected period — a simple turnover proxy."
$$;
