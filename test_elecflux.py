from elecflux import (
    get_offset_timestamp_from_hour,
    iso_day_to_dt,
    generate_datapoints,
    Datapoint,
)
import pytest
import pytz
import datetime
from logzero import logger


def test_get_offset_timestamp_from_hour():
    assert (
        get_offset_timestamp_from_hour(100) == 3600
    )  # 1AM => 3600s past the begining of the day
    assert get_offset_timestamp_from_hour(2400) == 0  # 24:00 = 0h00
    assert get_offset_timestamp_from_hour(2401) == 60  # 24:01 = 0h01 == 60s
    assert get_offset_timestamp_from_hour(2359) == 86400 - 60  # 23:59
    with pytest.raises(TypeError):
        get_offset_timestamp_from_hour("0100")


def test_iso_day_to_dt():
    mytz = pytz.timezone("America/Los_Angeles")
    assert iso_day_to_dt("2020-01-01", mytz) == mytz.localize(
        datetime.datetime(2020, 1, 1)
    )


def test_generate_datapoints_multiple_rates():
    RATES = [
        {
            "provider": "foo",
            "plans": [
                {
                    "name": "bar",
                    "deprecated_on": None,
                    "rates": [
                        {
                            "tier": 1,
                            "price": 0.26,
                            "date_begin": "Jan 2",
                            "date_end": "Sep 30",
                        },
                        {
                            "tier": 1,
                            "price": 0.9,
                            "date_begin": "Oct 1",
                            "date_end": "Jan 1",
                        },
                    ],
                }
            ],
        }
    ]
    mytz = pytz.timezone("UTC")
    results = generate_datapoints(RATES, "1970-01-01", "1970-01-02", mytz)

    assert (
        Datapoint(
            d=mytz.localize(datetime.datetime(1970, 1, 2)),
            measurement="rates",
            values={"price": 0.26},
            tags={"provider": "foo", "plan": "bar", "tier": 1},
        )
        in results
    )

    assert (
        Datapoint(
            d=mytz.localize(datetime.datetime(1970, 1, 1)),
            measurement="rates",
            values={"price": 0.9},
            tags={"provider": "foo", "plan": "bar", "tier": 1},
        )
        in results
    )


def test_generate_datapoints_overlapping_plans():
    RATES = [
        {
            "provider": "foo",
            "plans": [
                {
                    "name": "bar",
                    "deprecated_on": None,
                    "active_since": "2020-07-01",
                    "rates": [
                        {
                            "price": 0.26,
                            "date_begin": "Jun 1",
                            "date_end": "Sep 30",
                        },
                        {
                            "price": 0.9,
                            "date_begin": "Oct 1",
                            "date_end": "May 31",
                        },
                    ],
                },
                {
                    "name": "bar",
                    "deprecated_on": "2020-07-31",
                    "rates": [
                        {
                            "price": 0.1,
                            "date_begin": "Jun 1",
                            "date_end": "Sep 30",
                        },
                        {
                            "price": 0.9,
                            "date_begin": "Oct 1",
                            "date_end": "May 31",
                        },
                    ],
                },
            ],
        }
    ]
    mytz = pytz.timezone("America/Los_Angeles")
    with pytest.raises(Exception) as e_info:
        generate_datapoints(RATES, "2020-07-29", "2020-08-02", mytz)
        print(e_info)


def test_generate_datapoints_expired_plan():
    RATES = [
        {
            "provider": "foo",
            "plans": [
                {
                    "name": "bar",
                    "deprecated_on": None,
                    "active_since": "2020-08-01",
                    "rates": [
                        {
                            "price": 0.26,
                            "date_begin": "Jun 1",
                            "date_end": "Sep 30",
                        },
                        {
                            "price": 0.9,
                            "date_begin": "Oct 1",
                            "date_end": "May 31",
                        },
                    ],
                },
                {
                    "name": "bar",
                    "deprecated_on": "2020-07-31",
                    "rates": [
                        {
                            "price": 0.1,
                            "date_begin": "Jun 1",
                            "date_end": "Sep 30",
                        },
                        {
                            "price": 0.9,
                            "date_begin": "Oct 1",
                            "date_end": "May 31",
                        },
                    ],
                },
            ],
        }
    ]
    mytz = pytz.timezone("America/Los_Angeles")
    results = generate_datapoints(RATES, "2020-07-29", "2020-08-02", mytz)
    assert (
        Datapoint(
            d=mytz.localize(datetime.datetime(2020, 7, 31)),
            measurement="rates",
            values={"price": 0.1},
            tags={"provider": "foo", "plan": "bar", "tier": 1},
        )
        in results
    )

    assert (
        Datapoint(
            d=mytz.localize(datetime.datetime(2020, 7, 31)),
            measurement="rates",
            values={"price": 0.26},
            tags={"provider": "foo", "plan": "bar", "tier": 1},
        )
        not in results
    )

    assert (
        Datapoint(
            d=mytz.localize(datetime.datetime(2020, 8, 1)),
            measurement="rates",
            values={"price": 0.26},
            tags={"provider": "foo", "plan": "bar", "tier": 1},
        )
        in results
    )
    assert (
        Datapoint(
            d=mytz.localize(datetime.datetime(2020, 8, 1)),
            measurement="rates",
            values={"price": 0.1},
            tags={"provider": "foo", "plan": "bar", "tier": 1},
        )
        not in results
    )


def test_generate_datapoints_weekdays_plan():
    RATES = [
        {
            "provider": "foo",
            "plans": [
                {
                    "name": "bar",
                    "rates": [
                        {
                            "price": 0.2,
                            "days": ["Saturday"],
                        },
                        {
                            "price": 0.4,
                            "days": ["Sunday"],
                            "date_begin": "Jan 1",
                            "date_end": "Dec 31",
                        },
                    ],
                }
            ],
        }
    ]
    mytz = pytz.timezone("America/Los_Angeles")
    results = generate_datapoints(RATES, "2021-10-01", "2021-10-03", mytz)

    assert (
        Datapoint(
            d=mytz.localize(datetime.datetime(2021, 10, 2)),
            measurement="rates",
            values={"price": 0.2},
            tags={"provider": "foo", "plan": "bar", "tier": 1},
        )
        in results
    )

    assert (
        Datapoint(
            d=mytz.localize(datetime.datetime(2021, 10, 3)),
            measurement="rates",
            values={"price": 0.4},
            tags={"provider": "foo", "plan": "bar", "tier": 1},
        )
        in results
    )


def test_generate_datapoints_allowances():
    RATES = [
        {
            "provider": "foo",
            "allowances": [
                {
                    "all_electric": True,
                    "daily_allowance_per_territory_kWh": {
                        "T": 13.6,
                    },
                    "date_begin": "Oct 1",
                    "date_end": "May 31",
                },
                {
                    "all_electric": True,
                    "daily_allowance_per_territory_kWh": {
                        "T": 7.5,
                    },
                    "date_begin": "Jun 1",
                    "date_end": "Sep 30",
                },
            ],
        }
    ]
    mytz = pytz.timezone("America/Los_Angeles")
    results = generate_datapoints(RATES, "2005-05-31", "2005-06-01", mytz)
    assert len(results) == 2
    assert (
        Datapoint(
            d=mytz.localize(datetime.datetime(2005, 6, 1)),
            measurement="allowances",
            values={"allowance": 7.5},
            tags={"provider": "foo", "territory": "T", "all_electric": 1},
        )
        in results
    )
    assert (
        Datapoint(
            d=mytz.localize(datetime.datetime(2005, 5, 31)),
            measurement="allowances",
            values={"allowance": 13.6},
            tags={"provider": "foo", "territory": "T", "all_electric": 1},
        )
        in results
    )
    assert (
        Datapoint(
            d=mytz.localize(datetime.datetime(2005, 6, 1)),
            measurement="allowances",
            values={"allowance": 13.6},
            tags={"provider": "foo", "territory": "T", "all_electric": 1},
        )
        not in results
    )
    assert (
        Datapoint(
            d=mytz.localize(datetime.datetime(2005, 5, 31)),
            measurement="allowances",
            values={"allowance": 7.5},
            tags={"provider": "foo", "territory": "T", "all_electric": 1},
        )
        not in results
    )


def test_dst_fall_back():
    RATES = [
        {
            "provider": "foo",
            "plans": [
                {
                    "name": "bar",
                    "rates": [
                        {
                            "price": 0.1,
                            "time_begin": 1000,
                            "time_end": 2000,
                        },
                        {
                            "price": 0.5,
                            "time_begin": 2000,
                            "time_end": 1000,
                        },
                    ],
                }
            ],
        }
    ]
    mytz = pytz.timezone("America/Los_Angeles")
    results = generate_datapoints(RATES, "2021-11-06", "2021-11-07", mytz)
    assert len(results) == 2 * 3  # 2 days with 3 points: midnight, 10AM, 10PM
    assert (
        Datapoint(
            d=mytz.localize(datetime.datetime(2021, 11, 6, 10, 0, 0)),
            measurement="rates",
            values={"price": 0.1},
            tags={"provider": "foo", "plan": "bar", "tier": 1},
        )
        in results
    )
    assert (
        Datapoint(
            d=mytz.localize(datetime.datetime(2021, 11, 7, 10, 0, 0)),
            measurement="rates",
            values={"price": 0.1},
            tags={"provider": "foo", "plan": "bar", "tier": 1},
        )
        in results
    )
    assert (
        Datapoint(
            d=mytz.localize(datetime.datetime(2021, 11, 7, 20, 0, 0)),
            measurement="rates",
            values={"price": 0.5},
            tags={"provider": "foo", "plan": "bar", "tier": 1},
        )
        in results
    )


def test_prices_over_multiple_years():
    RATES = [
        {
            "provider": "foo",
            "plans": [
                {
                    "name": "bar",
                    "rates": [
                        {
                            "price": 0.1,
                            "date_begin": "Jan 1",
                            "date_end": "May 31",
                        },
                        {
                            "price": 0.5,
                            "date_begin": "Jun 1",
                            "date_end": "Dec 31",
                        },
                    ],
                }
            ],
        }
    ]
    mytz = pytz.timezone("America/Los_Angeles")
    results = generate_datapoints(RATES, "2021-12-31", "2024-01-01", mytz)
    assert (
        Datapoint(
            d=mytz.localize(datetime.datetime(2021, 12, 31)),
            measurement="rates",
            values={"price": 0.5},
            tags={"provider": "foo", "plan": "bar", "tier": 1},
        )
        in results
    )
    assert (
        Datapoint(
            d=mytz.localize(datetime.datetime(2022, 1, 1)),
            measurement="rates",
            values={"price": 0.5},
            tags={"provider": "foo", "plan": "bar", "tier": 1},
        )
        not in results
    )
    assert (
        Datapoint(
            d=mytz.localize(datetime.datetime(2022, 1, 1)),
            measurement="rates",
            values={"price": 0.1},
            tags={"provider": "foo", "plan": "bar", "tier": 1},
        )
        in results
    )
    assert (
        Datapoint(
            d=mytz.localize(datetime.datetime(2024, 1, 1)),
            measurement="rates",
            values={"price": 0.5},
            tags={"provider": "foo", "plan": "bar", "tier": 1},
        )
        not in results
    )
    assert (
        Datapoint(
            d=mytz.localize(datetime.datetime(2024, 1, 1)),
            measurement="rates",
            values={"price": 0.1},
            tags={"provider": "foo", "plan": "bar", "tier": 1},
        )
        in results
    )


def test_midnight_datapoint():
    RATES = [
        {
            "provider": "foo",
            "plans": [
                {
                    "name": "bar",
                    "deprecated_on": None,
                    "rates": [
                        {
                            "price": 0.1,
                            "time_begin": 1000,
                            "time_end": 2000,
                            "date_begin": "Jan 1",
                            "date_end": "Dec 31",
                        },
                        {
                            "price": 0.5,
                            "time_begin": 2000,
                            "time_end": 1000,
                            "date_begin": "Jan 1",
                            "date_end": "Dec 31",
                        },
                    ],
                }
            ],
        }
    ]
    mytz = pytz.timezone("America/Los_Angeles")
    results = generate_datapoints(RATES, "2021-11-11", "2021-11-13", mytz)

    assert (
        Datapoint(
            d=mytz.localize(datetime.datetime(2021, 11, 11, 20, 0, 0)),
            measurement="rates",
            values={"price": 0.5},
            tags={"provider": "foo", "plan": "bar", "tier": 1},
        )
        in results
    )
    assert (
        Datapoint(
            d=mytz.localize(datetime.datetime(2021, 11, 12, 0, 0, 0)),
            measurement="rates",
            values={"price": 0.5},
            tags={"provider": "foo", "plan": "bar", "tier": 1},
        )
        in results
    )
