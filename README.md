# Retail Semantic Layer

A self-contained Databricks Asset Bundle (DAB) that stands up a governed retail semantic layer from nothing: synthetic data → a curated dimensional model with informational PK/FK constraints → governed Unity Catalog Metric Views → a Genie space that queries them in natural language.

Built as a portfolio artifact for a "Senior Manager, Data Semantics and Context Modeling" application — see [ARCHITECTURE.md](ARCHITECTURE.md) for the business-context layer (entity glossary, business rules, hierarchies, and the reasoning behind the design), which is the part most directly aimed at that role. The five canonical entities — **guest, product, store, transaction, inventory** — and the "consistent definitions, metrics, and meaning across all consumption patterns" goal both come directly from that JD's own language.

You should be able to `git clone` this and deploy it into your own Databricks workspace — it creates its own catalog, schemas, pipeline, and jobs, and looks up an existing SQL warehouse to run against (see below for why it doesn't create its own).

**Catalog and schemas are created by a SQL task at the start of the job run, not as declarative bundle resources.** On the workspace this was built against, the Unity Catalog REST API that Terraform/DABs uses for a declarative `resources.catalogs` resource (`POST /api/2.1/unity-catalog/catalogs`) failed to resolve the metastore's default managed storage ("Metastore storage root URL does not exist"), even though the exact same metastore resolves default storage correctly for a plain `CREATE CATALOG ...` SQL statement. So catalog/schema creation runs as the first task in the `semantic_layer` job, via the SQL path that's known to work — see `src/bootstrap/create_catalog_and_schemas.sql`. This is a platform-level inconsistency on the workspace this was tested against, not a DAB or SQL syntax issue — worth knowing about if you hit the same error on `bundle deploy`.

**One consequence of that workaround**: `resources.pipelines.gold_star_schema` is still a declarative bundle resource, and Databricks validates that its target `catalog` already exists *at `bundle deploy` time* — before the job (and its catalog-creating SQL task) has ever run. On a workspace with the platform quirk above, that's a chicken-and-egg problem the bundle can't resolve on its own: Terraform can't create the catalog, and the job that could create it doesn't exist until after `bundle deploy` succeeds. The one-time fix is to create the catalog by hand, once, before the very first deploy on a fresh workspace:

```bash
databricks experimental aitools tools query --warehouse <any-existing-warehouse-id> --profile <your-profile> "CREATE CATALOG IF NOT EXISTS retail_semantics_demo"
```

If your workspace doesn't hit the REST API bug in the first place, you can skip this — `bundle deploy` will create the catalog fine on its own via the normal path and this step is a no-op safety net at most.

**No bundle-owned SQL warehouse, by design.** The original design had the bundle create and own a small serverless warehouse — better in the abstract for zero-dependency portability. That broke immediately on a Databricks Free Edition workspace, which is hard-capped at one SQL warehouse: `bundle deploy` failed with `RESOURCE_EXHAUSTED` trying to create a second one. So instead, `warehouse_id` (used by every SQL task, the metric views, and the Genie space) is resolved via a `lookup:` against an *existing* warehouse by name — see the `warehouse_name` variable in `databricks.yml`, defaulting to `"Serverless Starter Warehouse"` (Free Edition's default). **If your workspace's default warehouse has a different name, override `warehouse_name` before deploying**, e.g. `databricks bundle deploy --var="warehouse_name=Your Warehouse Name"`.

## Prerequisites

- Databricks CLI installed and authenticated (`databricks auth profiles` should show a valid profile)
- A Unity Catalog-enabled workspace with permission to create catalogs, and at least one existing SQL warehouse

No local Python setup is required — job tasks run entirely on Databricks serverless compute, with dependencies declared in the job config and resolved at run time.

## Quickstart

```bash
databricks bundle deploy --profile <your-profile> -t dev
databricks bundle run semantic_layer --profile <your-profile> -t dev
```

**Keep the default `catalog` / `gold_schema` variable values** (`retail_semantics_demo` / `gold`) unless you're prepared to also hand-edit `src/semantic/*.sql` and `src/retail_semantics.geniespace.json` — those two reference the catalog/schema as literal text rather than bundle variables (explained in [ARCHITECTURE.md](ARCHITECTURE.md#design-trade-offs)).

The first command provisions everything declarative: a Lakeflow Declarative Pipeline, two jobs, and a Genie space, all pointed at the looked-up warehouse. The second command runs the job end to end: creates the catalog/schemas via SQL → generates synthetic bronze data → builds the curated gold star schema → creates the two governed metric views.

## What gets deployed

| Resource | What it does |
|---|---|
| `resources/gold_pipeline.pipeline.yml` | Lakeflow Declarative Pipeline: bronze → gold star schema, with data-quality expectations and informational PK/FK constraints |
| `resources/semantic_layer.job.yml` | The critical-path job: bootstrap catalog/schemas via SQL → generate data → refresh the gold pipeline → create both metric views |
| `resources/retail_semantics.genie_space.yml` | The Genie space resource, fully built and checked in — see below for how it was built |
| `resources/ai_enrichment.job.yml` | Optional, not on the critical path — see [Optional: AI-assisted glossary](#optional-ai-assisted-glossary) |

## How the Genie space was built

`src/retail_semantics.geniespace.json` is already built and checked in — cloning this repo and running the Quickstart gets you the fully-curated Genie space with no manual step. It was built as a one-time, two-pass process, documented here in case it ever needs to be rebuilt (e.g. after editing the space's instructions or trusted assets in the UI):

1. Deploy and run everything else first (the Quickstart above).
2. In the workspace UI, create a Genie space by hand against the real deployed tables and metric views:
   - Add `gold.sales_metrics` and `gold.inventory_metrics` as trusted assets (the authoritative layer).
   - Add `gold.dim_guest`, `gold.dim_product`, `gold.dim_store`, `gold.fact_transaction`, `gold.fact_inventory` as trusted assets (the exploratory fallback layer).
   - Add an instruction along the lines of: *"Prefer the metric views for any question matching a defined measure (Net Sales, Units Sold, Transaction Count, Average Order Value, Guest Count, Sell-Through Rate, Inventory Turnover). Use the underlying tables only for questions the metric views don't cover."*
   - Add a few curated sample questions, e.g. *"What were net sales by store region last month?"*, *"Which products have the lowest sell-through rate?"*, *"Which region has the highest sell-through on Bottoms this period, and what does that mean for its stock level?"*
3. Snapshot it: `databricks bundle generate genie-space --existing-id <space-id> --key retail_semantics --profile <your-profile> -t dev` (find `<space-id>` via `databricks genie list-spaces`).
4. Delete the manually-created space: `databricks genie trash-space <space-id>`.
5. `databricks bundle deploy --profile <your-profile> -t dev` again — the bundle now owns the Genie space declaratively.
6. Commit `resources/retail_semantics.genie_space.yml` and `src/retail_semantics.geniespace.json`. Every future clone gets the fully-curated space from `bundle deploy` alone — no manual step required downstream.

One nice side effect worth noting: the generated JSON includes `join_specs` that Genie auto-inferred from the informational PK/FK constraints declared in the gold pipeline SQL — direct evidence the two-tier tables/metric-views design (see [ARCHITECTURE.md](ARCHITECTURE.md)) is doing its job for discoverability, not just decoration.

## Verifying it worked

1. `databricks bundle deploy` — pipeline, jobs, and Genie space all stand up from nothing, pointed at your existing warehouse.
2. `databricks bundle run semantic_layer` — catalog/schema bootstrap → bronze generation → gold curation (constraints, comments, expectations) → metric views, end to end.
3. Query a metric view directly:
   ```sql
   SELECT `Product Category`, MEASURE(`Net Sales`)
   FROM retail_semantics_demo.gold.sales_metrics
   GROUP BY ALL
   ```
4. Open the deployed Genie space and ask something like *"What were net sales by store region last month?"* — confirms natural-language querying over governed metrics, and that Genie prefers the metric view over the raw tables.
5. Read [ARCHITECTURE.md](ARCHITECTURE.md) for the written business-context-layer artifact — entity glossary, business rules, hierarchies, metric definitions, and the reasoning behind the two-tier tables/metric-views design.

## Optional: AI-assisted glossary

`resources/ai_enrichment.job.yml` is a separate job, not wired into `semantic_layer`, that uses `ai_gen()` to draft business descriptions for any gold table/column that's still missing one (gap-filling, not overwriting the hand-curated comments already in the pipeline SQL). It's kept off the critical path because Foundation Model API availability isn't guaranteed in every workspace. Run it manually if you want to see it:

```bash
databricks bundle run ai_enrichment --profile <your-profile> -t dev
```

## Repository layout

```
databricks.yml                 Bundle root config, including the warehouse_id lookup variable
resources/                     Declarative resource definitions (pipeline, jobs, Genie space)
src/bootstrap/                 Catalog/schema creation SQL (runs as the job's first task, not a bundle resource)
src/bronze/                    Synthetic data generator (PySpark + Faker)
src/pipelines/gold/            Gold star schema transformations (Lakeflow Declarative Pipeline SQL)
src/semantic/                  Metric view definitions (governed KPIs)
src/enrichment/                Optional ai_gen-based glossary drafting
src/retail_semantics.geniespace.json  Genie space definition (paired with resources/retail_semantics.genie_space.yml)
ARCHITECTURE.md                Business-context layer: glossary, business rules, hierarchies, design trade-offs
reference/                     Reference material (a full databricks bundle schema dump, kept for lookups)
```
