#!/usr/bin/env python3
"""
This script populates Electricity rates defined in a custom YAML format
into an InfluxDB (v1) so it can be used in concert with emporia-vue or any
other electricity usage timeseries.

The script can run either continuously as a daemon or (soon TM)
in one shot mode to populate past data.

It will generate measurements (timeseries) for every plan and baseline allowance pricing at the exact timestamp the price change. It's important to pass the local timezone as an arg.
An additional measurement will be added to the database that contains only 0 or 1 to indicate which time of use (peak, off peak ...) is active. This can enable you to differenciate energy consumed during these different times.

More details on the YAML format in the rates.yaml file
"""

__author__ = "Mathieu Frappier"
__version__ = "0.1.0"
__license__ = "MIT"

from influxdb import InfluxDBClient  # influx v1
from typing import Dict, Optional, List, Union
import os
import yaml
import time
import argparse
from datetime import date, datetime, timedelta
from logzero import logger

from yaml.loader import FullLoader
import pytz


def get_offset_timestamp_from_hour(hour: int) -> int:
    return (hour // 100 * 3600 + hour % 100 * 60) % 86400


class Datapoint:
    def __init__(
        self, timestamp: int, measurement: str, values: Dict[str, Union[float, int]], tags: Dict
    ):
        self.measurement = measurement
        self.values = values
        self.tags = tags
        self.timestamp = timestamp

    def dump(self):
        tag_strings = []
        for k, v in self.tags.items():
            tag_strings.append(f"{k}={v}")
        result = []
        for k, v in self.values.items():
            result.append(f"{self.measurement},{','.join(tag_strings)} {k}={v} {self.timestamp}")
        return result


def write_measurement(s: str) -> None:
    print(s)


def iso_day_to_dt(d: str, timezone: pytz.timezone):
    return timezone.localize(datetime(*list(map(int, d.split("-")))))


def datapoints_to_csv(dpts: List[Datapoint], database_name: str) -> str:
    result = """# DML
# CONTEXT-DATABASE: {}
""".format(
        database_name
    )
    for d in dpts:
        result += "\n" + d

    return result


def generate_datapoints(
    providers: List[Dict],
    date_from: str,
    date_until: str,
    timezone: pytz.timezone,
    measurement: str,
) -> List[Datapoint]:

    datapoints = []
    for provider in providers:
        for plan in provider["plans"]:
            plan_being_date=plan.get("active_since")
            plan_begin_dt = iso_day_to_dt(
                str(plan_being_date) if plan_being_date is not None else "2000-01-01", timezone
            )
            plan_end_date=plan.get("deprecated_on")
            plan_end_dt = iso_day_to_dt(
                str(plan_end_date) if plan_end_date is not None else "2100-12-31", timezone
            )
            requested_fill_from_dt = iso_day_to_dt(date_from, timezone)
            requested_fill_until_dt = iso_day_to_dt(date_until, timezone)
            if (
                requested_fill_until_dt < plan_begin_dt
                or requested_fill_from_dt > plan_end_dt
            ):
                logger.debug(f"Ignoring plan {plan} out of dates {requested_fill_from_dt} - {requested_fill_until_dt}")
                continue
            fill_from_dt = max(requested_fill_from_dt, plan_begin_dt)
            fill_until_dt = min(requested_fill_until_dt, plan_end_dt)

            for rate in plan["rates"]:

                rate_begin_dt = timezone.localize(
                    datetime.strptime(f"{rate.get('date_begin', 'Jan 1')} {requested_fill_from_dt.year}", "%b %d %Y")
                )
                rate_end_dt = timezone.localize(
                    datetime.strptime(f"{rate.get('date_end', 'Dec 31')} {requested_fill_until_dt.year}", "%b %d %Y")
                )
                rate_fill_from_dt = max(
                    rate_begin_dt, requested_fill_from_dt, plan_begin_dt
                )
                if rate_begin_dt>rate_end_dt:
                    rate_end_dt += timedelta(days=365)
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
                tags={
                    "provider": provider["provider"],
                    "plan": plan.get("name", "default_plan")
                }
                allowance=rate.get("daily_allowance_Wh")
                if allowance is not None:
                    tags["allowance"]=allowance

                while day <= rate_fill_until_dt:
                    if day.strftime("%A") not in rate_valid_days:
                        day += timedelta(days=1)
                        continue

                    hour_begin = int(rate.get("time_begin", 0000))
                    timestamp = int(
                        (
                            day
                            + timedelta(
                                seconds=get_offset_timestamp_from_hour(hour_begin)
                            )
                        ).timestamp()
                    )
                    datapoints.extend(
                        Datapoint(
                            timestamp=timestamp,
                            measurement=measurement,
                            values={"price": rate.get("price"), "enabled": 1},
                            tags=tags
                        ).dump()
                    )
                    hour_end = rate.get("time_end")
                    if hour_end is not None:
                        timestamp_end = int(
                            (
                                day
                                + timedelta(
                                    seconds=get_offset_timestamp_from_hour(int(hour_end))
                                )
                            ).timestamp()
                        )
                        datapoints.extend(
                            Datapoint(
                                timestamp=timestamp,
                                measurement=measurement,
                                values={"enabled": 0},
                                tags=tags,
                            ).dump()
                        )
                    day += timedelta(days=1)
    return datapoints


def add_price_point(
    timestamp: float, plan: str, value: float, baseline: Optional[str] = None
) -> dict:
    return {}


data_point_template = {
    "measurement": "price",
    "tags": {
        "plan": None,
        "baseline": None,
    },
    "time": time.time(),
    "fields": {"value": 0},
}


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
        date_end = datetime.now().strftime("%Y-%m-%d")
    datapoints=generate_datapoints(rates, date_begin, date_end, timezone, args.measurement)
    # TODO: Replace this cheap CSV export
    if args.csv is True:
        print(datapoints_to_csv(datapoints,db))


if __name__ == "__main__":
    """This is executed when run from the command line"""
    parser = argparse.ArgumentParser()

    # Required positional argument
    parser.add_argument("rates_file", help="Required rates.yaml file")

    parser.add_argument("-c", "--csv", action='store_true', help="Do not connect to InfluxDB, just output CSV instead")
    # InfluxDB related arguments
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
        "-m",
        "--measurement",
        type=str,
        help="Name of the 'table' that is holding the data in influx",
        default="rates",
    )

    # Optional arguments to backfill
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
