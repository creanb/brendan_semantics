"""Generate synthetic bronze data for the retail semantic layer demo.

Runs as a Databricks Jobs `spark_python_task` on serverless compute (not
Databricks Connect) — `SparkSession.builder.getOrCreate()` attaches to the
session the job runtime already provides.

Two seeded, correlated signals give the gold/metric-view layer something
real to show, instead of flat distributions:
  1. A one-week promo lifts transaction volume for the Bottoms category
     across all stores.
  2. South region stores start the following two-week inventory window
     under-stocked on Bottoms specifically, so post-promo demand drains
     them to a near-zero on-hand stockout by the end of the window —
     visible directly in `inventory_metrics` (Sell-Through Rate,
     Inventory Turnover).
Every other distribution (region mix, category mix, store traffic) is
weighted, not uniform, per standard synthetic-data practice.
"""

import argparse
from datetime import date, timedelta

import pandas as pd
from pyspark.sql import SparkSession, functions as F
from pyspark.sql.types import StringType
from pyspark.sql.window import Window

N_GUESTS = 5_000
N_PRODUCTS = 500
N_STORES = 25

TRANSACTION_WINDOW_DAYS = 90
BASE_TRANSACTION_LINES = 135_000
PROMO_TRANSACTION_LINES = 15_000
PROMO_START_DAY = 35   # offset within the transaction window
PROMO_LENGTH_DAYS = 7

INVENTORY_WINDOW_DAYS = 14
INVENTORY_WINDOW_START_DAY = PROMO_START_DAY + PROMO_LENGTH_DAYS  # snapshot begins right after the promo

CATEGORIES = ["Bottoms", "Tops", "Outerwear", "Accessories", "Footwear"]
CATEGORY_WEIGHTS = [0.30, 0.30, 0.15, 0.15, 0.10]  # never uniform

SUBCATEGORIES = {
    "Bottoms": ["Leggings", "Joggers", "Shorts"],
    "Tops": ["Tanks", "Long Sleeve", "Short Sleeve"],
    "Outerwear": ["Jackets", "Vests"],
    "Accessories": ["Bags", "Headwear", "Socks"],
    "Footwear": ["Trainers", "Sandals"],
}

# Fictitious line names — deliberately not real retailer product lines.
PRODUCT_LINES = ["Ascend", "Motion", "Flexline", "Core", "Summit", "Horizon"]
BRANDS = ["Ascend Athletics", "Horizon Studio", "CoreForm", "Summit & Co", "Flexline"]

PRICE_BANDS = {
    # category -> (list_price_low, list_price_high)
    "Bottoms": (68, 128),
    "Tops": (48, 98),
    "Outerwear": (118, 248),
    "Accessories": (12, 58),
    "Footwear": (78, 148),
}

REGIONS = ["West", "Central", "East", "South"]
GUEST_REGION_WEIGHTS = [0.35, 0.25, 0.25, 0.15]

# 25 stores: West 8, Central 7, East 6, South 4 — regional skew, not uniform.
STORE_REGIONS = (
    ["West"] * 8 + ["Central"] * 7 + ["East"] * 6 + ["South"] * 4
)
STORE_DISTRICTS = (
    (["West-1"] * 4 + ["West-2"] * 4)
    + (["Central-1"] * 4 + ["Central-2"] * 3)
    + (["East-1"] * 3 + ["East-2"] * 3)
    + (["South-1"] * 2 + ["South-2"] * 2)
)
STATE_BY_REGION = {"West": "CA", "Central": "TX", "East": "NY", "South": "GA"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--schema", required=True)
    return parser.parse_args()


def weighted_case(values: list[str], weights: list[float]):
    """Non-uniform F.when/.otherwise chain. One `rand()` draw is reused across all
    branches so the cumulative thresholds are compared against the same per-row value —
    calling F.rand() fresh in each branch would make the branches independent draws
    instead of a single weighted pick."""
    r = F.rand()
    cumulative = 0.0
    expr = None
    for value, weight in zip(values[:-1], weights[:-1]):
        cumulative += weight
        expr = F.when(r < cumulative, value) if expr is None else expr.when(r < cumulative, value)
    return expr.otherwise(values[-1])


@F.pandas_udf(StringType())
def fake_first_name(ids: pd.Series) -> pd.Series:
    from faker import Faker

    fake = Faker()
    return pd.Series([fake.first_name() for _ in range(len(ids))])


@F.pandas_udf(StringType())
def fake_last_name(ids: pd.Series) -> pd.Series:
    from faker import Faker

    fake = Faker()
    return pd.Series([fake.last_name() for _ in range(len(ids))])


@F.pandas_udf(StringType())
def fake_city(ids: pd.Series) -> pd.Series:
    from faker import Faker

    fake = Faker()
    return pd.Series([fake.city() for _ in range(len(ids))])


def generate_guests(spark: SparkSession, window_start: date) -> "pyspark.sql.DataFrame":
    signup_range_days = (window_start - date(2022, 1, 1)).days
    return (
        spark.range(0, N_GUESTS, numPartitions=8)
        .select(
            F.concat(F.lit("G"), F.lpad(F.col("id").cast("string"), 6, "0")).alias("guest_id"),
            fake_first_name(F.col("id")).alias("first_name"),
            fake_last_name(F.col("id")).alias("last_name"),
            weighted_case(REGIONS, GUEST_REGION_WEIGHTS).alias("home_region"),
            F.date_add(
                F.lit(date(2022, 1, 1)), (F.rand() * signup_range_days).cast("int")
            ).alias("signup_date"),
        )
        .withColumn(
            "email",
            F.concat(
                F.lower(F.col("first_name")), F.lit("."), F.lower(F.col("last_name")),
                F.lit("@example.com"),
            ),
        )
        .select("guest_id", "first_name", "last_name", "email", "signup_date", "home_region")
    )


def generate_products(spark: SparkSession) -> "pyspark.sql.DataFrame":
    subcat_lookup = F.create_map(
        *[item for cat, subs in SUBCATEGORIES.items() for item in (F.lit(cat), F.array(*[F.lit(s) for s in subs]))]
    )
    price_low = weighted_case_numeric("category", PRICE_BANDS, index=0)
    price_high = weighted_case_numeric("category", PRICE_BANDS, index=1)

    df = (
        spark.range(0, N_PRODUCTS, numPartitions=8)
        .select(
            F.concat(F.lit("P"), F.lpad(F.col("id").cast("string"), 5, "0")).alias("product_id"),
            weighted_case(CATEGORIES, CATEGORY_WEIGHTS).alias("category"),
            F.element_at(F.array(*[F.lit(b) for b in PRODUCT_LINES]), (F.abs(F.hash(F.col("id"))) % len(PRODUCT_LINES)) + 1).alias("product_line"),
            F.element_at(F.array(*[F.lit(b) for b in BRANDS]), (F.abs(F.hash(F.col("id") + 1)) % len(BRANDS)) + 1).alias("brand"),
            F.col("id").alias("_id"),
        )
        .withColumn("subcategory_options", subcat_lookup[F.col("category")])
        .withColumn(
            "subcategory",
            F.element_at(
                F.col("subcategory_options"),
                (F.abs(F.hash(F.col("_id"))) % F.size(F.col("subcategory_options"))) + 1,
            ),
        )
        .withColumn("_price_low", price_low)
        .withColumn("_price_high", price_high)
        .withColumn(
            "list_price",
            F.round(F.col("_price_low") + F.rand() * (F.col("_price_high") - F.col("_price_low")), 2),
        )
        .withColumn("unit_cost", F.round(F.col("list_price") * (F.lit(0.35) + F.rand() * 0.20), 2))
        .withColumn("product_name", F.concat(F.col("product_line"), F.lit(" "), F.col("subcategory")))
    )
    return df.select(
        "product_id", "product_name", "category", "subcategory", "brand", "unit_cost", "list_price"
    )


def weighted_case_numeric(column: str, bands: dict, index: int):
    expr = None
    for cat, band in bands.items():
        value = float(band[index])
        expr = F.when(F.col(column) == cat, F.lit(value)) if expr is None else expr.when(F.col(column) == cat, F.lit(value))
    return expr


def generate_stores(spark: SparkSession) -> "pyspark.sql.DataFrame":
    return (
        spark.range(0, N_STORES, numPartitions=4)
        .select(
            F.concat(F.lit("S"), F.lpad(F.col("id").cast("string"), 3, "0")).alias("store_id"),
            F.element_at(F.array(*[F.lit(r) for r in STORE_REGIONS]), F.col("id").cast("int") + 1).alias("region"),
            F.element_at(F.array(*[F.lit(d) for d in STORE_DISTRICTS]), F.col("id").cast("int") + 1).alias("district"),
            fake_city(F.col("id")).alias("city"),
            F.date_add(F.lit(date(2015, 1, 1)), (F.rand() * 2900).cast("int")).alias("open_date"),
        )
        .withColumn(
            "state",
            F.element_at(
                F.create_map(*[item for r, s in STATE_BY_REGION.items() for item in (F.lit(r), F.lit(s))]),
                F.col("region"),
            ),
        )
        .withColumn("store_name", F.concat(F.col("city"), F.lit(" Store")))
        .select("store_id", "store_name", "region", "district", "city", "state", "open_date")
    )


def generate_transaction_lines(
    spark: SparkSession, window_start: date, n_guests: int, n_products: int, n_stores: int
) -> "pyspark.sql.DataFrame":
    def base_lines(n: int, day_offset_expr):
        return (
            spark.range(0, n, numPartitions=32)
            .withColumn("transaction_id", F.concat(F.lit("T"), F.lpad((F.col("id") % 60_000).cast("string"), 6, "0")))
            .withColumn("line_number", (F.col("id") % 4) + 1)
            .withColumn("transaction_date", F.date_add(F.lit(window_start), day_offset_expr))
            # store traffic is skewed toward a handful of flagship stores (low store_idx), not uniform
            .withColumn("store_idx", (F.pow(F.rand(), 2) * n_stores).cast("int"))
            .withColumn("guest_idx", (F.abs(F.hash(F.col("id"))) % n_guests).cast("int"))
            .withColumn("product_idx", (F.abs(F.hash(F.col("id") + 7)) % n_products).cast("int"))
        )

    base = base_lines(BASE_TRANSACTION_LINES, (F.rand() * TRANSACTION_WINDOW_DAYS).cast("int"))
    promo = base_lines(
        PROMO_TRANSACTION_LINES,
        (F.lit(PROMO_START_DAY) + (F.rand() * PROMO_LENGTH_DAYS).cast("int")),
    ).withColumn("is_promo", F.lit(True))
    base = base.withColumn("is_promo", F.lit(False))

    lines = base.unionByName(promo).withColumn(
        "quantity", F.when(F.rand() < 0.7, 1).when(F.rand() < 0.93, 2).otherwise(3)
    )
    return lines.select(
        "transaction_id", "line_number", "transaction_date", "store_idx", "guest_idx", "product_idx",
        "quantity", "is_promo",
    )


def generate_inventory_snapshots(
    spark: SparkSession, window_start: date, n_stores: int, n_products: int
) -> "pyspark.sql.DataFrame":
    snapshot_start = window_start + timedelta(days=INVENTORY_WINDOW_START_DAY)
    return (
        spark.range(0, n_stores * n_products * INVENTORY_WINDOW_DAYS, numPartitions=32)
        .withColumn("store_idx", (F.col("id") / (n_products * INVENTORY_WINDOW_DAYS)).cast("int"))
        .withColumn("_rem", F.col("id") % (n_products * INVENTORY_WINDOW_DAYS))
        .withColumn("product_idx", (F.col("_rem") / INVENTORY_WINDOW_DAYS).cast("int"))
        .withColumn("day_idx", (F.col("_rem") % INVENTORY_WINDOW_DAYS).cast("int"))
        .withColumn("snapshot_date", F.date_add(F.lit(snapshot_start), F.col("day_idx")))
        .drop("_rem")
    )


def build(catalog: str, schema: str) -> None:
    spark = SparkSession.builder.getOrCreate()
    window_start = date.today() - timedelta(days=TRANSACTION_WINDOW_DAYS)

    guests = generate_guests(spark, window_start)
    guests.write.mode("overwrite").saveAsTable(f"{catalog}.{schema}.guest")

    products = generate_products(spark)
    products.write.mode("overwrite").saveAsTable(f"{catalog}.{schema}.product")

    stores = generate_stores(spark)
    stores.write.mode("overwrite").saveAsTable(f"{catalog}.{schema}.store")

    # Read masters back, indexed 0..N-1 via row_number, for FK joins against
    # the hash-modulo indices produced in generate_transaction_lines/generate_inventory_snapshots.
    guest_indexed = spark.table(f"{catalog}.{schema}.guest").withColumn(
        "guest_idx", F.row_number().over(Window.orderBy("guest_id")) - 1
    )
    product_indexed = spark.table(f"{catalog}.{schema}.product").withColumn(
        "product_idx", F.row_number().over(Window.orderBy("product_id")) - 1
    )
    store_indexed = spark.table(f"{catalog}.{schema}.store").withColumn(
        "store_idx", F.row_number().over(Window.orderBy("store_id")) - 1
    )

    lines = generate_transaction_lines(spark, window_start, N_GUESTS, N_PRODUCTS, N_STORES)
    # Promo lines are resampled to Bottoms-category products only.
    bottoms_products = product_indexed.filter(F.col("category") == "Bottoms").select("product_idx")
    bottoms_count = bottoms_products.count()
    bottoms_indexed = bottoms_products.withColumn(
        "_bottoms_rank", F.row_number().over(Window.orderBy("product_idx")) - 1
    )

    promo_lines = (
        lines.filter(F.col("is_promo"))
        .withColumn("_bottoms_rank", F.abs(F.hash(F.col("transaction_id"), F.col("line_number"))) % F.lit(bottoms_count))
        .drop("product_idx")
        .join(bottoms_indexed, on="_bottoms_rank")
        .drop("_bottoms_rank")
    )
    non_promo_lines = lines.filter(~F.col("is_promo"))
    lines = non_promo_lines.unionByName(promo_lines)

    transaction_lines = (
        lines
        .join(guest_indexed.select("guest_idx", "guest_id"), on="guest_idx")
        .join(product_indexed.select("product_idx", "product_id", "list_price"), on="product_idx")
        .join(store_indexed.select("store_idx", "store_id"), on="store_idx")
        .withColumn("unit_price", F.col("list_price"))
        .withColumn(
            "discount_amount",
            F.when(F.col("is_promo"), F.round(F.col("unit_price") * 0.20, 2)).otherwise(F.lit(0.0)),
        )
        .withColumn("tax_amount", F.round((F.col("unit_price") * F.col("quantity") - F.col("discount_amount")) * 0.08, 2))
        .select(
            "transaction_id", "line_number", "transaction_date", "guest_id", "store_id", "product_id",
            "quantity", "unit_price", "discount_amount", "tax_amount",
        )
    )
    transaction_lines.write.mode("overwrite").saveAsTable(f"{catalog}.{schema}.transaction_line")

    inventory = generate_inventory_snapshots(spark, window_start, N_STORES, N_PRODUCTS)
    inventory_with_fk = (
        inventory
        .join(store_indexed.select("store_idx", "store_id", "region"), on="store_idx")
        .join(product_indexed.select("product_idx", "product_id", "category"), on="product_idx")
    )

    # South + Bottoms starts the window under-stocked and decays toward a
    # stockout by the last snapshot day — everything else holds roughly flat.
    is_depleting = (F.col("region") == "South") & (F.col("category") == "Bottoms")
    baseline_stock = F.when(F.col("category") == "Bottoms", F.lit(60)).otherwise(F.lit(120))
    depleting_stock = F.greatest(F.lit(0), F.lit(18) - F.col("day_idx") * 2)
    noise = (F.rand() * 10 - 5).cast("int")

    inventory_final = inventory_with_fk.withColumn(
        "quantity_on_hand",
        F.when(is_depleting, depleting_stock).otherwise(F.greatest(F.lit(0), baseline_stock + noise)),
    ).select("snapshot_date", "store_id", "product_id", "quantity_on_hand")

    inventory_final.write.mode("overwrite").saveAsTable(f"{catalog}.{schema}.inventory_snapshot")


if __name__ == "__main__":
    args = parse_args()
    build(args.catalog, args.schema)
