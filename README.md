# Elecflux
This generates timeseries data for InfluxDB 1.8 for utility rates that you define in a YAML file.
If you have your realtime usage in InfluxDB/Grafana you can have a realtime cost dashboard.
It works well with https://github.com/jertel/vuegraf


![Dashboard screenshot](https://raw.githubusercontent.com/matfra/elecflux/main/dashboard.png "Example dashboard")


```
git clone https://github.com/matfra/elecflux.git
cd elecflux
python -m virtualenv -p python3 venv
venv/bin/pip install -r requirements.txt
venv/bin/python ./elecflux.py rates.yaml -b 2021-06-01 -e 2021-12-31 --csv > rates_2021_H2.csv
```

To import in an influxDB:
```
influx --host 127.0.0.1 -import -path=rates_2021_H2.csv -precision=s -database=vue
```
# Disclaimer
Anything is provided as an example and shouldn't be used in production

# To-do
Currently this only generates a CSV file. It doesn't connect to influxdb yet
The grafana dashboard currently does not implement allowances/limits