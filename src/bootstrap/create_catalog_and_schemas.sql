-- Runs as the first task in resources/semantic_layer.job.yml, not as a
-- declarative `resources.catalogs` / `resources.schemas` bundle resource.
-- On this workspace, `POST /api/2.1/unity-catalog/catalogs` (the REST call
-- Databricks Asset Bundles/Terraform use for a declarative catalog resource)
-- fails with "Metastore storage root URL does not exist", even though the
-- metastore's default storage works fine — proven by running plain
-- `CREATE CATALOG ...` SQL directly, which resolves default storage
-- correctly. So catalog/schema creation is done here, via the same SQL path
-- that's known to work, using named parameters supplied by the job's
-- sql_task.parameters (bundle variables substitute normally there, since
-- it's a structured YAML field, not templated file content).
CREATE CATALOG IF NOT EXISTS IDENTIFIER(:catalog_name);
CREATE SCHEMA IF NOT EXISTS IDENTIFIER(:catalog_name || '.' || :bronze_schema_name);
CREATE SCHEMA IF NOT EXISTS IDENTIFIER(:catalog_name || '.' || :gold_schema_name);
