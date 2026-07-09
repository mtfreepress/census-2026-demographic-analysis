#!/usr/bin/env python3
"""Generate county age demographic change outputs from Census age/sex data."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = ROOT / "input" / "census-2025-estimate-agesex.csv"
DEFINITION_PATH = ROOT / "definitions" / "agesex-definition.txt"
OUTPUT_DIR = ROOT / "output"
LARGEST_COUNTY_LIMIT = 10
STATEWIDE_KEY = ("30", "000")
STATEWIDE_NAME = "Montana"

CHILD_TOTAL_COLUMNS = ("UNDER5_TOT", "AGE513_TOT", "AGE1417_TOT")
CHILD_MALE_COLUMNS = ("UNDER5_MALE", "AGE513_MALE", "AGE1417_MALE")
CHILD_FEMALE_COLUMNS = ("UNDER5_FEM", "AGE513_FEM", "AGE1417_FEM")

SENIOR_TOTAL_COLUMNS = ("AGE65PLUS_TOT",)
SENIOR_MALE_COLUMNS = ("AGE65PLUS_MALE",)
SENIOR_FEMALE_COLUMNS = ("AGE65PLUS_FEM",)

START_YEAR = "2"
END_YEAR = "7"
INDEX_YEARS = {
    "2": "2020",
    "3": "2021",
    "4": "2022",
    "5": "2023",
    "6": "2024",
    "7": "2025",
}

CHANGE_COLUMNS = (
    "county",
    "totalAbsoluteChange",
    "totalPctChange",
    "maleAbsoluteChange",
    "malePctChange",
    "femaleAbsoluteChange",
    "femalePctChange",
)

AGING_INDEX_COLUMNS = (
    "county",
    "agingIndex2020",
    "agingIndex2021",
    "agingIndex2022",
    "agingIndex2023",
    "agingIndex2024",
    "agingIndex2025",
    "agingIndexPointChange20to25",
    "agingIndexPctChange20to25",
    "seniorAbsoluteChange",
    "childrenAbsoluteChange",
)


def population(row: dict[str, str], columns: tuple[str, ...]) -> int:
    return sum(int(row[column]) for column in columns)


def aging_index(children: int, seniors: int) -> float | None:
    if children == 0:
        return None
    return (seniors / children) * 100


def pct_change(start: int | float | None, end: int | float | None) -> float | None:
    if start in (None, 0) or end is None:
        return None
    return ((end - start) / start) * 100


def format_number(value: int | float | None, places: int = 2) -> str:
    if value is None:
        return ""
    if isinstance(value, int):
        return str(value)

    text = f"{value:.{places}f}"
    return text.rstrip("0").rstrip(".")


def required_columns() -> set[str]:
    return {
        "STATE",
        "COUNTY",
        "CTYNAME",
        "YEAR",
        "POPESTIMATE",
        *CHILD_TOTAL_COLUMNS,
        *CHILD_MALE_COLUMNS,
        *CHILD_FEMALE_COLUMNS,
        *SENIOR_TOTAL_COLUMNS,
        *SENIOR_MALE_COLUMNS,
        *SENIOR_FEMALE_COLUMNS,
    }


def validate_definition_file() -> None:
    definition = DEFINITION_PATH.read_text(encoding="utf-8")
    expected_terms = [
        "2 = 7/1/2020 population estimate",
        "7 = 7/1/2025 population estimate",
        "UNDER5_TOT",
        "AGE513_TOT",
        "AGE1417_TOT",
        "AGE65PLUS_TOT",
    ]
    missing_terms = [term for term in expected_terms if term not in definition]
    if missing_terms:
        missing = ", ".join(missing_terms)
        raise ValueError(f"Definition file is missing expected terms: {missing}")


def load_rows() -> dict[tuple[str, str], dict[str, dict[str, str]]]:
    with INPUT_PATH.open(newline="", encoding="utf-8") as input_file:
        reader = csv.DictReader(input_file)
        missing_columns = sorted(required_columns() - set(reader.fieldnames or ()))
        if missing_columns:
            missing = ", ".join(missing_columns)
            raise ValueError(f"Input file is missing required columns: {missing}")

        rows_by_county: dict[tuple[str, str], dict[str, dict[str, str]]] = {}
        for row in reader:
            key = (row["STATE"], row["COUNTY"])
            rows_by_county.setdefault(key, {})[row["YEAR"]] = row

    needed_years = {START_YEAR, END_YEAR, *INDEX_YEARS}
    missing_years = {
        rows[START_YEAR]["CTYNAME"] if START_YEAR in rows else f"{state}-{county}": sorted(
            needed_years - set(rows)
        )
        for (state, county), rows in rows_by_county.items()
        if needed_years - set(rows)
    }
    if missing_years:
        raise ValueError(f"Missing required years by county: {missing_years}")

    return rows_by_county


def build_statewide_rows(
    rows_by_county: dict[tuple[str, str], dict[str, dict[str, str]]],
) -> dict[str, dict[str, str]]:
    numeric_columns = required_columns() - {"STATE", "COUNTY", "CTYNAME", "YEAR"}
    statewide_rows: dict[str, dict[str, str]] = {}

    for year in INDEX_YEARS:
        statewide_row = {
            "STATE": STATEWIDE_KEY[0],
            "COUNTY": STATEWIDE_KEY[1],
            "CTYNAME": STATEWIDE_NAME,
            "YEAR": year,
        }
        for column in numeric_columns:
            statewide_row[column] = str(
                sum(int(county_rows[year][column]) for county_rows in rows_by_county.values())
            )
        statewide_rows[year] = statewide_row

    return statewide_rows


def largest_county_keys(
    rows_by_county: dict[tuple[str, str], dict[str, dict[str, str]]],
    limit: int,
) -> list[tuple[str, str]]:
    return [
        key
        for key, rows in sorted(
            rows_by_county.items(),
            key=lambda item: int(item[1][START_YEAR]["POPESTIMATE"]),
            reverse=True,
        )[:limit]
    ]


def build_change_rows(
    rows_by_county: dict[tuple[str, str], dict[str, dict[str, str]]],
    total_columns: tuple[str, ...],
    male_columns: tuple[str, ...],
    female_columns: tuple[str, ...],
    county_keys: list[tuple[str, str]] | None = None,
) -> list[dict[str, str]]:
    output_rows = []

    for key in county_keys if county_keys is not None else sorted(rows_by_county):
        county_rows = rows_by_county[key]
        start = county_rows[START_YEAR]
        end = county_rows[END_YEAR]

        total_start = population(start, total_columns)
        total_end = population(end, total_columns)
        male_start = population(start, male_columns)
        male_end = population(end, male_columns)
        female_start = population(start, female_columns)
        female_end = population(end, female_columns)

        total_change = total_end - total_start
        male_change = male_end - male_start
        female_change = female_end - female_start

        output_rows.append(
            {
                "county": start["CTYNAME"],
                "totalAbsoluteChange": format_number(total_change),
                "totalPctChange": format_number(pct_change(total_start, total_end)),
                "maleAbsoluteChange": format_number(male_change),
                "malePctChange": format_number(pct_change(male_start, male_end)),
                "femaleAbsoluteChange": format_number(female_change),
                "femalePctChange": format_number(pct_change(female_start, female_end)),
            }
        )

    return output_rows


def build_aging_index_rows(
    rows_by_county: dict[tuple[str, str], dict[str, dict[str, str]]],
    county_keys: list[tuple[str, str]] | None = None,
) -> list[dict[str, str]]:
    output_rows = []

    for key in county_keys if county_keys is not None else sorted(rows_by_county):
        county_rows = rows_by_county[key]
        indexes: dict[str, float | None] = {}
        for year, label in INDEX_YEARS.items():
            row = county_rows[year]
            children = population(row, CHILD_TOTAL_COLUMNS)
            seniors = population(row, SENIOR_TOTAL_COLUMNS)
            indexes[label] = aging_index(children, seniors)

        children_2020 = population(county_rows[START_YEAR], CHILD_TOTAL_COLUMNS)
        children_2025 = population(county_rows[END_YEAR], CHILD_TOTAL_COLUMNS)
        seniors_2020 = population(county_rows[START_YEAR], SENIOR_TOTAL_COLUMNS)
        seniors_2025 = population(county_rows[END_YEAR], SENIOR_TOTAL_COLUMNS)

        index_point_change = (
            None
            if indexes["2020"] is None or indexes["2025"] is None
            else indexes["2025"] - indexes["2020"]
        )

        output_rows.append(
            {
                "county": county_rows[START_YEAR]["CTYNAME"],
                "agingIndex2020": format_number(indexes["2020"], places=1),
                "agingIndex2021": format_number(indexes["2021"], places=1),
                "agingIndex2022": format_number(indexes["2022"], places=1),
                "agingIndex2023": format_number(indexes["2023"], places=1),
                "agingIndex2024": format_number(indexes["2024"], places=1),
                "agingIndex2025": format_number(indexes["2025"], places=1),
                "agingIndexPointChange20to25": format_number(index_point_change, places=1),
                "agingIndexPctChange20to25": format_number(
                    pct_change(indexes["2020"], indexes["2025"])
                ),
                "seniorAbsoluteChange": format_number(seniors_2025 - seniors_2020),
                "childrenAbsoluteChange": format_number(children_2025 - children_2020),
            }
        )

    return output_rows


def write_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    validate_definition_file()
    rows_by_county = load_rows()
    largest_keys = largest_county_keys(rows_by_county, LARGEST_COUNTY_LIMIT)
    rows_with_statewide = {
        **rows_by_county,
        STATEWIDE_KEY: build_statewide_rows(rows_by_county),
    }
    largest_keys_with_statewide = [STATEWIDE_KEY, *largest_keys]
    OUTPUT_DIR.mkdir(exist_ok=True)

    write_csv(
        OUTPUT_DIR / "children-demographic-change-2020-2025.csv",
        CHANGE_COLUMNS,
        build_change_rows(
            rows_by_county,
            CHILD_TOTAL_COLUMNS,
            CHILD_MALE_COLUMNS,
            CHILD_FEMALE_COLUMNS,
        ),
    )
    write_csv(
        OUTPUT_DIR / "senior-demographic-change-2020-2025.csv",
        CHANGE_COLUMNS,
        build_change_rows(
            rows_by_county,
            SENIOR_TOTAL_COLUMNS,
            SENIOR_MALE_COLUMNS,
            SENIOR_FEMALE_COLUMNS,
        ),
    )
    write_csv(
        OUTPUT_DIR / "aging-index-2020-2025.csv",
        AGING_INDEX_COLUMNS,
        build_aging_index_rows(rows_by_county),
    )

    write_csv(
        OUTPUT_DIR / "10-largest-children-demographic-change-2020-2025.csv",
        CHANGE_COLUMNS,
        build_change_rows(
            rows_with_statewide,
            CHILD_TOTAL_COLUMNS,
            CHILD_MALE_COLUMNS,
            CHILD_FEMALE_COLUMNS,
            largest_keys_with_statewide,
        ),
    )
    write_csv(
        OUTPUT_DIR / "10-largest-senior-demographic-change-2020-2025.csv",
        CHANGE_COLUMNS,
        build_change_rows(
            rows_with_statewide,
            SENIOR_TOTAL_COLUMNS,
            SENIOR_MALE_COLUMNS,
            SENIOR_FEMALE_COLUMNS,
            largest_keys_with_statewide,
        ),
    )
    write_csv(
        OUTPUT_DIR / "10-largest-aging-index-2020-2025.csv",
        AGING_INDEX_COLUMNS,
        build_aging_index_rows(rows_with_statewide, largest_keys_with_statewide),
    )


if __name__ == "__main__":
    main()
