# Elecflux
This generates timeseries data for InfluxDB 1.8 for utility rates that you define in a YAML file.
If you have your realtime usage in InfluxDB/Grafana you can have a realtime cost dashboard.
It works well with https://github.com/jertel/vuegraf


![Dashboard screenshot](https://raw.githubusercontent.com/matfra/elecflux/main/dashboard.png "Example dashboard")


```
git clone https://github.com/matfra/elecflux.git
cd elecflux
python -m venv -p python3 venv
venv/bin/pip install -r requirements.txt
venv/bin/python ./elecflux.py rates.yaml -b 2025-01-01 -e 2026-12-31 --csv > rates_2025-2026.csv
```

To import in an influxDB:
```
~/influxdb2-client-2.3.0-linux-amd64$ ./influx write -b "vue/autogen" -p ns --format=lp -f ../rates_2025-2026.csv
```

# Disclaimer
Anything is provided as an example and shouldn't be used in production

# To-do
E-TOU-C and E-1 are broken on the dashboard due to the way allowance works. Need to rethink that
Currently this only generates a CSV file. It doesn't connect to influxdb yet
The grafana dashboard currently does not implement allowances/limits