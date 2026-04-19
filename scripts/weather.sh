#!/usr/bin/env bash
# Fetch weather for New Taipei City from Open-Meteo API (free, no key).
# Output: /tmp/weather.json

set -euo pipefail

OUTPUT="/tmp/weather.json"

# New Taipei City coordinates
LAT="25.01"
LON="121.46"

# Fetch forecast
RAW=$(curl -sf --max-time 10 \
  "https://api.open-meteo.com/v1/forecast?latitude=${LAT}&longitude=${LON}&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code&timezone=Asia/Taipei&forecast_days=1")

if [ -z "$RAW" ]; then
  echo '{"error": "Failed to fetch weather data"}' > "$OUTPUT"
  echo "ERROR: Weather fetch failed" >&2
  exit 1
fi

# Map WMO weather code to Chinese description
# See: https://open-meteo.com/en/docs#weathervariables
CODE=$(echo "$RAW" | python3 -c "
import sys, json
data = json.load(sys.stdin)
code = data['daily']['weather_code'][0]
temp_max = data['daily']['temperature_2m_max'][0]
temp_min = data['daily']['temperature_2m_min'][0]
precip = data['daily']['precipitation_probability_max'][0]

weather_map = {
    0: '晴天',
    1: '大致晴朗', 2: '多雲', 3: '陰天',
    45: '霧', 48: '霧凇',
    51: '小毛毛雨', 53: '毛毛雨', 55: '大毛毛雨',
    61: '小雨', 63: '中雨', 65: '大雨',
    71: '小雪', 73: '中雪', 75: '大雪',
    80: '陣雨', 81: '中陣雨', 82: '大陣雨',
    95: '雷雨', 96: '雷雨夾冰雹', 99: '強雷雨夾冰雹',
}
desc = weather_map.get(code, f'未知({code})')

result = {
    'temp_max': temp_max,
    'temp_min': temp_min,
    'precipitation_probability': precip,
    'weather_code': code,
    'description': desc,
    'location': '新北市',
}
print(json.dumps(result, ensure_ascii=False))
")

echo "$CODE" > "$OUTPUT"
echo "Weather data written to $OUTPUT" >&2
