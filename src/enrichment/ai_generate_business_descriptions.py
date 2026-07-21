"""Optional, non-critical-path job: fill in any missing table/column business
descriptions in the gold schema using ai_gen(), Databricks' built-in
generative-AI SQL function.

This is gap-filling, not overwriting: the gold pipeline SQL already hand-writes
COMMENT text for every table and column (that's the deliberately curated
definition of the semantic layer). This script only drafts a description for
objects that still have no comment — e.g. if the pipeline is extended with a
new table/column later and documentation lags behind. It demonstrates the
JD's "use generative AI methods to help build the semantic layer" without
undermining hand-curated definitions.

Small object count (a handful of tables/columns), so a driver-side Python
loop issuing one ai_gen() call per object is appropriate here — this is
one-time metadata enrichment, not row-level data processing.
"""

import argparse

from pyspark.sql import SparkSession


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--schema", required=True)
    return parser.parse_args()


def escape_sql_literal(text: str) -> str:
    return text.replace("'", "''")


def ai_gen_description(spark: SparkSession, prompt: str) -> str:
    prompt_escaped = escape_sql_literal(prompt)
    row = spark.sql(f"SELECT ai_gen('{prompt_escaped}') AS description").first()
    return row["description"].strip()


def fill_table_comments(spark: SparkSession, catalog: str, schema: str) -> None:
    tables = spark.sql(
        f"""
        SELECT table_name, comment
        FROM {catalog}.information_schema.tables
        WHERE table_schema = '{schema}'
        """
    ).collect()

    for row in tables:
        table = row["table_name"]
        if row["comment"]:
            continue
        columns = spark.sql(
            f"""
            SELECT column_name FROM {catalog}.information_schema.columns
            WHERE table_schema = '{schema}' AND table_name = '{table}'
            ORDER BY ordinal_position
            """
        ).collect()
        column_list = ", ".join(c["column_name"] for c in columns)
        prompt = (
            f"In one sentence, describe the business purpose of a retail data table "
            f"named '{table}' with columns: {column_list}. No preamble, just the sentence."
        )
        description = escape_sql_literal(ai_gen_description(spark, prompt))
        spark.sql(f"COMMENT ON TABLE {catalog}.{schema}.{table} IS '{description}'")


def fill_column_comments(spark: SparkSession, catalog: str, schema: str) -> None:
    columns = spark.sql(
        f"""
        SELECT table_name, column_name, data_type, comment
        FROM {catalog}.information_schema.columns
        WHERE table_schema = '{schema}'
        ORDER BY table_name, ordinal_position
        """
    ).collect()

    for row in columns:
        if row["comment"]:
            continue
        table, column, data_type = row["table_name"], row["column_name"], row["data_type"]
        prompt = (
            f"In one short sentence, describe the business meaning of column '{column}' "
            f"({data_type}) in a retail data table named '{table}'. No preamble, just the sentence."
        )
        description = escape_sql_literal(ai_gen_description(spark, prompt))
        spark.sql(
            f"ALTER TABLE {catalog}.{schema}.{table} ALTER COLUMN {column} COMMENT '{description}'"
        )


def run(catalog: str, schema: str) -> None:
    spark = SparkSession.builder.getOrCreate()
    fill_table_comments(spark, catalog, schema)
    fill_column_comments(spark, catalog, schema)


if __name__ == "__main__":
    args = parse_args()
    run(args.catalog, args.schema)
