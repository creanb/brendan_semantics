CREATE OR REPLACE VIEW retail_semantics_demo.gold.sales_metrics
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
source: retail_semantics_demo.gold.fact_transaction
comment: "Governed retail sales KPIs. Canonical definitions for net sales, average order value, and guest counts — the authoritative layer Genie should prefer for any question matching one of these measures."

joins:
  - name: guest
    source: retail_semantics_demo.gold.dim_guest
    on: source.guest_key = guest.guest_key
  - name: product
    source: retail_semantics_demo.gold.dim_product
    on: source.product_key = product.product_key
  - name: store
    source: retail_semantics_demo.gold.dim_store
    on: source.store_key = store.store_key

dimensions:
  - name: Transaction Date
    expr: source.transaction_date
    comment: "Calendar date of the transaction."
  - name: Product Category
    expr: product.category
    comment: "Top-level merchandise hierarchy."
  - name: Product Subcategory
    expr: product.subcategory
  - name: Store Region
    expr: store.region
    comment: "Top-level store geography hierarchy."
  - name: Store District
    expr: store.district

measures:
  - name: Net Sales
    expr: SUM(source.net_amount)
    comment: "Gross sales minus discounts. Excludes tax. Business rule: quantity * unit_price - discount_amount."
  - name: Units Sold
    expr: SUM(source.quantity)
  - name: Transaction Count
    expr: COUNT(DISTINCT source.transaction_id)
    comment: "Distinct baskets/orders — not line items."
  - name: Average Order Value
    expr: SUM(source.net_amount) / COUNT(DISTINCT source.transaction_id)
    comment: "Net Sales divided by Transaction Count."
  - name: Guest Count
    expr: COUNT(DISTINCT source.guest_key)
    comment: "Distinct guests who transacted in the selected slice."
$$;
