#!/usr/bin/env python3
"""Generate county age index outputs from Census all-demographic data."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = ROOT / "input" / "census-2025-estimate-all-demographic.csv"
DEFINITION_PATH = ROOT / "definitions" / "all-demographic-definition.txt"
OUTPUT_DIR = ROOT / "output" / "age-index"
LARGEST_COUNTY_LIMIT = 10
STATEWIDE_KEY = ("30", "000")
STATEWIDE_NAME = "Montana"

CHILD_AGE_GROUPS = ("1", "2", "3")
SENIOR_AGE_GROUPS = ("14", "15", "16", "17", "18")
TOTAL_AGE_GROUP = "0"

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

AGE_INDEX_COLUMNS = (
    "county",
    "ageIndex2020",
    "ageIndex2021",
    "ageIndex2022",
    "ageIndex2023",
    "ageIndex2024",
    "ageIndex2025",
    "ageIndexPointChange20to25",
    "ageIndexPctChange20to25",
    "seniorAbsoluteChange",
    "children014AbsoluteChange",
)


def population(row: dict[str, str]) -> int:
    return int(row["TOT_POP"])


def age_index(children: int, seniors: int) -> float | None:
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
        "AGEGRP",
        "TOT_POP",
    }


def validate_definition_file() -> None:
    definition = DEFINITION_PATH.read_text(encoding="utf-8")
    expected_terms = [
        "2 = 7/1/2020 population estimate",
        "7 = 7/1/2025 population estimate",
        "1 = Age 0 to 4 years",
        "2 = Age 5 to 9 years",
        "3 = Age 10 to 14 years",
        "14 = Age 65 to 69 years",
        "18 = Age 85 years or older",
    ]
    missing_terms = [term for term in expected_terms if term not in definition]
    if missing_terms:
        missing = ", ".join(missing_terms)
        raise ValueError(f"Definition file is missing expected terms: {missing}")


def load_rows() -> dict[tuple[str, str], dict[str, dict[str, dict[str, str]]]]:
    with INPUT_PATH.open(newline="", encoding="utf-8") as input_file:
        reader = csv.DictReader(input_file)
        missing_columns = sorted(required_columns() - set(reader.fieldnames or ()))
        if missing_columns:
            missing = ", ".join(missing_columns)
            raise ValueError(f"Input file is missing required columns: {missing}")

        rows_by_county: dict[tuple[str, str], dict[str, dict[str, dict[str, str]]]] = {}
        for row in reader:
            key = (row["STATE"], row["COUNTY"])
            rows_by_year = rows_by_county.setdefault(key, {})
            rows_by_year.setdefault(row["YEAR"], {})[row["AGEGRP"]] = row

    needed_years = {START_YEAR, END_YEAR, *INDEX_YEARS}
    needed_age_groups = {TOTAL_AGE_GROUP, *CHILD_AGE_GROUPS, *SENIOR_AGE_GROUPS}
    missing: dict[str, dict[str, list[str]]] = {}

    for (state, county), rows_by_year in rows_by_county.items():
        county_name = next(
            (
                age_rows[TOTAL_AGE_GROUP]["CTYNAME"]
                for age_rows in rows_by_year.values()
                if TOTAL_AGE_GROUP in age_rows
            ),
            f"{state}-{county}",
        )

        missing_years = sorted(needed_years - set(rows_by_year))
        missing_age_groups = {
            year: sorted(needed_age_groups - set(rows_by_year[year]))
            for year in needed_years & set(rows_by_year)
            if needed_age_groups - set(rows_by_year[year])
        }

        if missing_years or missing_age_groups:
            missing[county_name] = {}
            if missing_years:
                missing[county_name]["years"] = missing_years
            missing[county_name].update(missing_age_groups)

    if missing:
        raise ValueError(f"Missing required years or age groups by county: {missing}")

    return rows_by_county


def build_statewide_rows(
    rows_by_county: dict[tuple[str, str], dict[str, dict[str, dict[str, str]]]],
) -> dict[str, dict[str, dict[str, str]]]:
    needed_age_groups = {TOTAL_AGE_GROUP, *CHILD_AGE_GROUPS, *SENIOR_AGE_GROUPS}
    statewide_rows: dict[str, dict[str, dict[str, str]]] = {}

    for year in INDEX_YEARS:
        statewide_rows[year] = {}
        for age_group in needed_age_groups:
            statewide_rows[year][age_group] = {
                "STATE": STATEWIDE_KEY[0],
                "COUNTY": STATEWIDE_KEY[1],
                "CTYNAME": STATEWIDE_NAME,
                "YEAR": year,
                "AGEGRP": age_group,
                "TOT_POP": str(
                    sum(
                        population(county_rows[year][age_group])
                        for county_rows in rows_by_county.values()
                    )
                ),
            }

    return statewide_rows


def age_group_population(
    rows_by_year: dict[str, dict[str, dict[str, str]]],
    year: str,
    age_groups: tuple[str, ...],
) -> int:
    return sum(population(rows_by_year[year][age_group]) for age_group in age_groups)


def largest_county_keys(
    rows_by_county: dict[tuple[str, str], dict[str, dict[str, dict[str, str]]]],
    limit: int,
) -> list[tuple[str, str]]:
    return [
        key
        for key, rows_by_year in sorted(
            rows_by_county.items(),
            key=lambda item: population(item[1][START_YEAR][TOTAL_AGE_GROUP]),
            reverse=True,
        )[:limit]
    ]


def build_age_index_rows(
    rows_by_county: dict[tuple[str, str], dict[str, dict[str, dict[str, str]]]],
    county_keys: list[tuple[str, str]] | None = None,
) -> list[dict[str, str]]:
    output_rows = []

    for key in county_keys if county_keys is not None else sorted(rows_by_county):
        rows_by_year = rows_by_county[key]
        indexes: dict[str, float | None] = {}
        for year, label in INDEX_YEARS.items():
            children = age_group_population(rows_by_year, year, CHILD_AGE_GROUPS)
            seniors = age_group_population(rows_by_year, year, SENIOR_AGE_GROUPS)
            indexes[label] = age_index(children, seniors)

        children_2020 = age_group_population(rows_by_year, START_YEAR, CHILD_AGE_GROUPS)
        children_2025 = age_group_population(rows_by_year, END_YEAR, CHILD_AGE_GROUPS)
        seniors_2020 = age_group_population(rows_by_year, START_YEAR, SENIOR_AGE_GROUPS)
        seniors_2025 = age_group_population(rows_by_year, END_YEAR, SENIOR_AGE_GROUPS)

        index_point_change = (
            None
            if indexes["2020"] is None or indexes["2025"] is None
            else indexes["2025"] - indexes["2020"]
        )

        output_rows.append(
            {
                "county": rows_by_year[START_YEAR][TOTAL_AGE_GROUP]["CTYNAME"],
                "ageIndex2020": format_number(indexes["2020"], places=1),
                "ageIndex2021": format_number(indexes["2021"], places=1),
                "ageIndex2022": format_number(indexes["2022"], places=1),
                "ageIndex2023": format_number(indexes["2023"], places=1),
                "ageIndex2024": format_number(indexes["2024"], places=1),
                "ageIndex2025": format_number(indexes["2025"], places=1),
                "ageIndexPointChange20to25": format_number(index_point_change, places=1),
                "ageIndexPctChange20to25": format_number(
                    pct_change(indexes["2020"], indexes["2025"])
                ),
                "seniorAbsoluteChange": format_number(seniors_2025 - seniors_2020),
                "children014AbsoluteChange": format_number(children_2025 - children_2020),
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
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    write_csv(
        OUTPUT_DIR / "age-index-2020-2025.csv",
        AGE_INDEX_COLUMNS,
        build_age_index_rows(rows_by_county),
    )
    write_csv(
        OUTPUT_DIR / "10-largest-age-index-2020-2025.csv",
        AGE_INDEX_COLUMNS,
        build_age_index_rows(rows_with_statewide, largest_keys_with_statewide),
    )


if __name__ == "__main__":
    main()
