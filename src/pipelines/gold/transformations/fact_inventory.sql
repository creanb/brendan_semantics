CREATE OR REFRESH MATERIALIZED VIEW fact_inventory (
  inventory_key      STRING NOT NULL COMMENT 'Surrogate key. Grain: one row per store, product, and snapshot date.',
  snapshot_date       DATE,
  store_key            STRING COMMENT 'FK to dim_store.',
  product_key          STRING COMMENT 'FK to dim_product.',
  quantity_on_hand     INT,
  CONSTRAINT valid_inventory_key EXPECT (inventory_key IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT valid_keys EXPECT (store_key IS NOT NULL AND product_key IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT non_negative_quantity EXPECT (quantity_on_hand >= 0) ON VIOLATION DROP ROW,
  CONSTRAINT pk_fact_inventory PRIMARY KEY (inventory_key),
  CONSTRAINT fk_fact_inventory_store FOREIGN KEY (store_key) REFERENCES dim_store,
  CONSTRAINT fk_fact_inventory_product FOREIGN KEY (product_key) REFERENCES dim_product
)
COMMENT 'Inventory fact — canonical entity per JD language. Daily on-hand snapshot grain per store/product.'
AS SELECT
  sha2(concat(i.snapshot_date, '-', i.store_id, '-', i.product_id), 256) AS inventory_key,
  i.snapshot_date,
  sha2(i.store_id, 256) AS store_key,
  sha2(i.product_id, 256) AS product_key,
  TRY_CAST(i.quantity_on_hand AS INT) AS quantity_on_hand
FROM ${source_catalog}.${source_schema}.inventory_snapshot i;
