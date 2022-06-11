#!/usr/bin/env python3
"""
This script populates Electricity rates defined in a custom YAML format
into an InfluxDB (v1) so it can be used in concert with emporia-vue or any
other electricity usage timeseries.

The script can run either continuously as a daemon or (soon TM)
in one shot mode to populate past data.

It will generate measurements (timeseries) for every plan and baseline allowance pricing (tiers) at the exact timestamp the price change. It's important to pass the local timezone as an arg.
An additional measurement will be added to the database that contains only 0 or 1 to indicate which time of use (peak, off peak ...) is active. This can enable you to differenciate energy consumed during these different times.

More details on the YAML format in the rates.yaml file
"""

__author__ = "Mathieu Frappier"
__version__ = "0.2.1"
__license__ = "MIT"

from typing import Dict, List, Union
import os
import yaml
import argparse
from datetime import datetime as dt
from datetime import timedelta
from logzero import logger

from yaml.loader import FullLoader
import pytz


class Datapoint:
    def __init__(
        self,
        d: dt,
        measurement: str,
        values: Dict[str, Union[float, int]],
        tags: Dict,
    ):
        self.measurement = measurement
        self.values = values
        self.tags = tags
        self.d = d
        self.timestamp = int(dt.timestamp(self.d))

    def __eq__(self, other):

        return (
            self.d == other.d
            and self.measurement == other.measurement
            and self.values == other.values
            and self.tags == other.tags
        )

    def __repr__(self):
        return f"{self.measurement} {self.values} {self.tags} {self.d}"

    def dump(self):
        tag_strings = []
        for k, v in self.tags.items():
            tag_strings.append(f"{k}={v}")
        result = []
        for k, v in self.values.items():

            result.append(
                f"{self.measurement},{','.join(tag_strings)} {k}={v} {self.timestamp}"
            )
        return result


def get_offset_timestamp_from_hour(hour: int) -> int:
    return (hour // 100 * 3600 + hour % 100 * 60) % 86400


def iso_day_to_dt(d: str, timezone: pytz.timezone):
    return timezone.localize(dt(*list(map(int, d.split("-")))))


def datapoints_to_csv(dpts: List[Datapoint], database_name: str) -> str:
    result = """# DML
# CONTEXT-DATABASE: {}
""".format(
        database_name
    )
    for d in dpts:
        result += "\n" + d.dump()

    return result


def generate_datapoints(
    providers: List[Dict], date_from: str, date_until: str, timezone: pytz.timezone
) -> List[Datapoint]:
    """
    This is the main function that generates datapoints for both prices (rates) and limits (baseline allowance)
    """

    datapoints = []
    requested_fill_from_dt = iso_day_to_dt(date_from, timezone)
    requested_fill_until_dt = iso_day_to_dt(date_until, timezone)
    for provider in providers:
        # Generate the baseline allowances (or limits) timeseries
        for allowance in provider.get("allowances", []):
            all_electric = 1 if allowance.get("all_electric", False) is True else 0
            allowance_begin_date = allowance.get("active_since")
            allowance_begin_dt = iso_day_to_dt(
                str(allowance_begin_date)
                if allowance_begin_date is not None
                else "1970-01-01",
                timezone,
            )
            allowance_end_date = allowance.get("deprecated_on")
            allowance_end_dt = iso_day_to_dt(
                str(allowance_end_date)
                if allowance_end_date is not None
                else "2100-12-31",  # EOL
                timezone,
            )
            if (
                requested_fill_until_dt < allowance_begin_dt
                or requested_fill_from_dt > allowance_end_dt
            ):
                logger.debug(
                    f"Ignoring allowance {allowance} out of dates {requested_fill_from_dt} - {requested_fill_until_dt}"
                )
                continue
            fill_from_dt = max(requested_fill_from_dt, allowance_begin_dt)
            fill_until_dt = min(requested_fill_until_dt, allowance_end_dt)

            year = fill_from_dt.year
            while year <= fill_until_dt.year:
                allowance_season_begin_dt = timezone.localize(
                    dt.strptime(
                        f"{allowance.get('date_begin', 'Jan 1')} {year}",
                        "%b %d %Y",
                    )
                )
                allowance_season_end_dt = timezone.localize(
                    dt.strptime(
                        f"{allowance.get('date_end', 'Dec 31')} {year}",
                        "%b %d %Y",
                    )
                )

                if allowance_season_end_dt < allowance_season_begin_dt:
                    allowance_season_begin_dt -= timedelta(days=365)
                elif allowance_season_begin_dt > allowance_season_end_dt:
                    allowance_season_end_dt += timedelta(days=365)

                allowance_season_fill_from_dt = max(
                    allowance_season_begin_dt,
                    requested_fill_from_dt,
                    allowance_begin_dt,
                )
                allowance_season_fill_until_dt = min(
                    allowance_season_end_dt, requested_fill_until_dt, allowance_end_dt
                )
                day = allowance_season_fill_from_dt
                while day <= allowance_season_fill_until_dt:
                    for territory, daily_allowance_kwh in allowance.get(
                        "daily_allowance_per_territory_kWh", {}
                    ).items():
                        datapoints.append(
                            Datapoint(
                                d=day,
                                measurement="allowances",
                                values={"allowance": daily_allowance_kwh},
                                tags={
                                    "provider": provider["provider"],
                                    "territory": territory,
                                    "all_electric": all_electric,
                                },
                            )
                        )
                    day = timezone.localize(
                        day.replace(tzinfo=None) + timedelta(days=1)
                    )
                year += 1

        # Generate the rates (or prices) timeseries
        for plan in provider.get("plans", []):
            plan_begin_date = plan.get("active_since")
            plan_begin_dt = iso_day_to_dt(
                str(plan_begin_date) if plan_begin_date is not None else "1970-01-01",
                timezone,
            )
            plan_end_date = plan.get("deprecated_on")
            plan_end_dt = iso_day_to_dt(
                str(plan_end_date) if plan_end_date is not None else "2100-12-31",
                timezone,
            )
            if (
                requested_fill_until_dt < plan_begin_dt
                or requested_fill_from_dt > plan_end_dt
            ):
                logger.debug(
                    f"Ignoring plan {plan} out of dates {requested_fill_from_dt} - {requested_fill_until_dt}"
                )
                continue
            fill_from_dt = max(requested_fill_from_dt, plan_begin_dt)
            fill_until_dt = min(requested_fill_until_dt, plan_end_dt)
            year = fill_from_dt.year
            while year <= fill_until_dt.year:
                for rate in plan["rates"]:

                    rate_begin_dt = timezone.localize(
                        dt.strptime(
                            f"{rate.get('date_begin', 'Jan 1')} {year}",
                            "%b %d %Y",
                        )
                    )
                    rate_end_dt = timezone.localize(
                        dt.strptime(
                            f"{rate.get('date_end', 'Dec 31')} {year}",
                            "%b %d %Y",
                        )
                    )
                    if rate_end_dt < rate_begin_dt:
                        rate_begin_dt -= timedelta(days=365)
                    elif rate_begin_dt > rate_end_dt:
                        rate_end_dt += timedelta(days=365)
                    rate_fill_from_dt = max(
                        rate_begin_dt, requested_fill_from_dt, plan_begin_dt
                    )
                    rate_fill_until_dt = min(
                        rate_end_dt, requested_fill_until_dt, plan_end_dt
                    )
                    day = rate_fill_from_dt
                    rate_valid_days = set(
                        rate.get(
                            "days",
                            [
                                "Monday",
                                "Tuesday",
                                "Wednesday",
                                "Thursday",
                                "Friday",
                                "Saturday",
                                "Sunday",
                            ],
                        )
                    )
                    tags = {
                        "provider": provider["provider"],
                        "plan": plan.get("name", "default_plan"),
                        "tier": rate.get("tier", 1),
                    }

                    while day <= rate_fill_until_dt:
                        if day.strftime("%A") not in rate_valid_days:
                            day = timezone.localize(
                                day.replace(tzinfo=None) + timedelta(days=1)
                            )
                            continue

                        hour_begin = int(rate.get("time_begin", 0000))
                        dh_begin = timezone.localize(
                            day.replace(tzinfo=None)
                            + timedelta(
                                seconds=get_offset_timestamp_from_hour(hour_begin)
                            )
                        )
                        hour_end = rate.get("time_end")
                        if hour_end is not None:
                            dh_end = timezone.localize(
                                day.replace(tzinfo=None)
                                + timedelta(
                                    seconds=get_offset_timestamp_from_hour(
                                        int(hour_end)
                                    )
                                )
                            )

                            if hour_begin > hour_end:  # Create a midnight datapoint??
                                datapoints.append(
                                    Datapoint(
                                        d=timezone.localize(
                                            day.replace(tzinfo=None)
                                        ),
                                        measurement="rates",
                                        values={"price": rate.get("price")},
                                        tags=tags,
                                    )
                                )
                        datapoints.append(
                            Datapoint(
                                d=timezone.localize(dh_begin.replace(tzinfo=None)),
                                measurement="rates",
                                values={"price": rate.get("price")},
                                tags=tags,
                            )
                        )
                        day = timezone.localize(
                            day.replace(tzinfo=None) + timedelta(days=1)
                        )
                year += 1
        check_for_overlapping_plans(datapoints)
    return datapoints


def check_for_overlapping_plans(datapoints):
    tags_by_date = {}
    for data in datapoints:
        tags = data.tags
        m = data.measurement
        v = data.values
        d = data.d

        if d not in tags_by_date:
            tags_by_date[d] = []
        if (tags, m) in tags_by_date[d]:
            raise ValueError(
                f'Overlapping plans detected for measurement "{m}" detected at ts: {d}:\n\t{tags} is overlapping with {tags_by_date[d]}'
            )
        else:
            tags_by_date[d].append((tags, m))


def load_rates_from_file(rates_file: str) -> Dict:
    with open(rates_file, "r") as rates_file:
        return yaml.load(rates_file, Loader=FullLoader)


def run_daemon(rates, timezone):
    raise SystemError("Daemon mode is not implemented yet")
    return False


def main(args):
    logger.debug("Running with the following args:")
    logger.debug(args)
    rates = load_rates_from_file(args.rates_file)
    date_begin = args.date_begin
    date_end = args.date_end
    db = args.influxdb_database
    timezone = pytz.timezone(args.timezone)
    if date_begin is None:
        exit(run_daemon(rates, timezone))
    if date_end is None:
        date_end = dt.now().strftime("%Y-%m-%d")
    datapoints = generate_datapoints(rates, date_begin, date_end, timezone)
    # TODO: Replace this cheap CSV export
    if args.csv is True:
        print(datapoints_to_csv(datapoints, db))


if __name__ == "__main__":
    """This is executed when run from the command line"""
    parser = argparse.ArgumentParser()

    # Required positional argument
    parser.add_argument("rates_file", help="Required rates.yaml file")

    parser.add_argument(
        "-c",
        "--csv",
        action="store_true",
        help="Do not connect to InfluxDB, just output CSV instead",
    )

    parser.add_argument(
        "-i", "--influxdb-host", type=str, help="Influxdb host", default="127.0.0.1"
    )
    parser.add_argument("-p", "--influxdb-port", type=int, default=8086)
    parser.add_argument(
        "-d",
        "--influxdb-database",
        type=str,
        default="vue",
        help="Name of the database to write to",
    )
    parser.add_argument(
        "-u",
        "--influxdb-username",
        type=str,
        help="Username can also be passed as a ENV VAR INFLUXDB_USERNAME",
        default=os.getenv("INFLUXDB_USERNAME", ""),
    )
    parser.add_argument(
        "-s",
        "--influxdb-password",
        type=str,
        help="Password can also be passed as a ENV VAR INFLUXDB_PASSWORD",
        default=os.getenv("INFLUXDB_PASSWORD", ""),
    )

    parser.add_argument(
        "-e",
        "--date-end",
        type=str,
        default=None,
        help="Date to backfill until. If date-begin is set this will default to today",
    )
    parser.add_argument(
        "-b",
        "--date-begin",
        type=str,
        default=None,
        help="Date to start the backfill, example: 2020-01-31. If ommited, runs in daemon mode. ",
    )
    parser.add_argument(
        "-t",
        "--timezone",
        type=str,
        help="Timezone for the TOU rates to be accurate eg. America/Los_Angeles",
        default="America/Los_Angeles",
    )

    # Optional verbosity counter (eg. -v, -vv, -vvv, etc.)
    parser.add_argument(
        "-v", "--verbose", action="count", default=0, help="Verbosity (-v, -vv, etc)"
    )

    # Specify output of "--version"
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s (version {version})".format(version=__version__),
    )

    args = parser.parse_args()
    main(args)
