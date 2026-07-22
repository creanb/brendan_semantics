CREATE OR REFRESH MATERIALIZED VIEW fact_transaction (
  transaction_line_key STRING NOT NULL COMMENT 'Surrogate key. Grain: one row per product per basket (transaction line item).',
  transaction_id        STRING COMMENT 'Natural key identifying the basket/order.',
  line_number            INT COMMENT 'Line number within the transaction.',
  transaction_date       DATE,
  guest_key               STRING COMMENT 'FK to dim_guest.',
  product_key             STRING COMMENT 'FK to dim_product.',
  store_key                STRING COMMENT 'FK to dim_store.',
  quantity                  INT,
  unit_price                DECIMAL(10,2),
  discount_amount          DECIMAL(10,2) COMMENT 'Discount applied to this line, e.g. from a promotion.',
  tax_amount                DECIMAL(10,2),
  net_amount                DECIMAL(10,2) COMMENT 'Business rule: quantity * unit_price - discount_amount. Excludes tax and is the basis for all Net Sales measures.',
  CONSTRAINT valid_line_key EXPECT (transaction_line_key IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT valid_keys EXPECT (guest_key IS NOT NULL AND product_key IS NOT NULL AND store_key IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT non_negative_quantity EXPECT (quantity > 0) ON VIOLATION DROP ROW,
  CONSTRAINT pk_fact_transaction PRIMARY KEY (transaction_line_key),
  CONSTRAINT fk_fact_transaction_guest FOREIGN KEY (guest_key) REFERENCES dim_guest,
  CONSTRAINT fk_fact_transaction_product FOREIGN KEY (product_key) REFERENCES dim_product,
  CONSTRAINT fk_fact_transaction_store FOREIGN KEY (store_key) REFERENCES dim_store
)
COMMENT 'Transaction fact — canonical entity per JD language. Line-item grain: one row per product per basket.'
AS SELECT
  sha2(concat(t.transaction_id, '-', t.line_number), 256) AS transaction_line_key,
  t.transaction_id,
  TRY_CAST(t.line_number AS INT) AS line_number,
  t.transaction_date,
  sha2(t.guest_id, 256) AS guest_key,
  sha2(t.product_id, 256) AS product_key,
  sha2(t.store_id, 256) AS store_key,
  TRY_CAST(t.quantity AS INT) AS quantity,
  TRY_CAST(t.unit_price AS DECIMAL(10,2)) AS unit_price,
  TRY_CAST(t.discount_amount AS DECIMAL(10,2)) AS discount_amount,
  TRY_CAST(t.tax_amount AS DECIMAL(10,2)) AS tax_amount,
  TRY_CAST(t.quantity * t.unit_price - t.discount_amount AS DECIMAL(10,2)) AS net_amount
FROM ${source_catalog}.${source_schema}.transaction_line t;
