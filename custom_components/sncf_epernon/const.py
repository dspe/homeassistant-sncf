"""Constants for the Épernon departure board."""

DOMAIN = "sncf_epernon"
TITLE = "Épernon → Paris-Montparnasse"
ROUTE_ID = "87394114_87391003"
CONF_INTERVAL = "update_interval"
CONF_COUNT = "train_count"
DEFAULT_INTERVAL = 60
DEFAULT_COUNT = 5
API_URL = (
    "https://api.sncf.com/v1/coverage/sncf/stop_areas/"
    "stop_area:SNCF:87394114/departures"
)
