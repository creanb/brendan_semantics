CREATE OR REFRESH MATERIALIZED VIEW dim_product (
  product_key   STRING NOT NULL COMMENT 'Surrogate key for the product dimension. Join target for fact tables.',
  product_id    STRING COMMENT 'Natural/business key (SKU) from the source system.',
  product_name  STRING,
  category      STRING COMMENT 'Top-level merchandise hierarchy (e.g. Bottoms, Tops, Accessories).',
  subcategory   STRING COMMENT 'Second-level hierarchy under category.',
  brand         STRING,
  unit_cost     DECIMAL(10,2) COMMENT 'Wholesale/manufacturing cost per unit.',
  list_price    DECIMAL(10,2) COMMENT 'Standard retail list price per unit.',
  CONSTRAINT valid_product_key EXPECT (product_key IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT valid_price EXPECT (list_price >= 0 AND unit_cost >= 0),
  CONSTRAINT pk_dim_product PRIMARY KEY (product_key)
)
COMMENT 'Product dimension — canonical entity per JD language. One row per SKU, with category/subcategory hierarchy for business context.'
AS SELECT
  sha2(product_id, 256) AS product_key,
  product_id,
  product_name,
  category,
  subcategory,
  brand,
  TRY_CAST(unit_cost AS DECIMAL(10,2)) AS unit_cost,
  TRY_CAST(list_price AS DECIMAL(10,2)) AS list_price
FROM ${source_catalog}.${source_schema}.product;
