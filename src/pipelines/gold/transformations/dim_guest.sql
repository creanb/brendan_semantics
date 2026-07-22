CREATE OR REFRESH MATERIALIZED VIEW dim_guest (
  guest_key     STRING NOT NULL COMMENT 'Surrogate key for the guest dimension. Join target for fact_transaction.guest_key.',
  guest_id      STRING COMMENT 'Natural/business key from the source system.',
  first_name    STRING,
  last_name     STRING,
  email         STRING,
  signup_date   DATE COMMENT 'Date the guest first registered.',
  home_region   STRING COMMENT 'Guest home region — top level of the guest geography hierarchy.',
  CONSTRAINT valid_guest_key EXPECT (guest_key IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT valid_email EXPECT (email LIKE '%@%'),
  CONSTRAINT pk_dim_guest PRIMARY KEY (guest_key)
)
COMMENT 'Guest dimension — canonical entity per JD language ("customer/guest"). One row per guest.'
AS SELECT
  sha2(guest_id, 256) AS guest_key,
  guest_id,
  first_name,
  last_name,
  email,
  signup_date,
  home_region
FROM ${source_catalog}.${source_schema}.guest;
