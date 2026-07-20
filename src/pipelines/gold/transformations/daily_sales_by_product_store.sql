CREATE OR REFRESH MATERIALIZED VIEW daily_sales_by_product_store (
  sale_date     DATE,
  store_key      STRING COMMENT 'FK to dim_store.',
  product_key    STRING COMMENT 'FK to dim_product.',
  units_sold      INT,
  net_sales        DECIMAL(12,2),
  CONSTRAINT fk_daily_sales_store FOREIGN KEY (store_key) REFERENCES dim_store,
  CONSTRAINT fk_daily_sales_product FOREIGN KEY (product_key) REFERENCES dim_product
)
COMMENT 'Daily units/net sales aggregated to (date, store, product) grain — same grain as fact_inventory snapshots. Exists specifically so gold.inventory_metrics can join sales to inventory without a fact-to-fact fan-out (joining fact_transaction line-item grain directly to fact_inventory would double count).'
AS SELECT
  transaction_date AS sale_date,
  store_key,
  product_key,
  SUM(quantity) AS units_sold,
  SUM(net_amount) AS net_sales
FROM fact_transaction
GROUP BY ALL;
