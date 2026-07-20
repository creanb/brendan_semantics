CREATE OR REFRESH MATERIALIZED VIEW dim_store (
  store_key   STRING NOT NULL COMMENT 'Surrogate key for the store dimension. Join target for fact tables.',
  store_id    STRING COMMENT 'Natural/business key from the source system.',
  store_name  STRING,
  region      STRING COMMENT 'Top level of the store geography hierarchy (e.g. West, Central, East).',
  district    STRING COMMENT 'Second level of the store geography hierarchy, under region.',
  city        STRING,
  state       STRING,
  open_date   DATE COMMENT 'Date the store opened.',
  CONSTRAINT pk_dim_store PRIMARY KEY (store_key),
  CONSTRAINT valid_store_key EXPECT (store_key IS NOT NULL) ON VIOLATION DROP ROW
)
COMMENT 'Store dimension — canonical entity per JD language. One row per physical store, with region/district hierarchy for business context.'
AS SELECT
  sha2(store_id, 256) AS store_key,
  store_id,
  store_name,
  region,
  district,
  city,
  state,
  open_date
FROM ${source_catalog}.${source_schema}.store;
