# Denver Recreation Center Calendar

A web-based calendar for viewing Denver Recreation Center schedules with filtering, sorting by distance, and Google Calendar integration.

![Calendar Preview](https://img.shields.io/badge/status-active-brightgreen)

## Features

- 📅 **Weekly Schedule View** - Navigate between days with an intuitive day selector
- 🚴 **Distance-Based Sorting** - Sort recreation centers by biking, driving, walking, or transit time from your location
- 🔍 **Smart Filtering** - Filter by gym, class type, or search by keyword
- 📱 **Mobile Friendly** - Responsive design works on desktop, tablet, and mobile
- 🌙 **Dark Mode** - Toggle between light and dark themes
- 📆 **Add to Calendar** - One-click Google Calendar integration
- 🎟️ **Sign Up Links** - Direct links to reserve classes that require sign-up
- ❌ **Cancelled Class Indicators** - Visual indicators for cancelled classes with option to hide them

## Official Website

[View the calendar](https://dustinwicker.github.io/denver_rec_centers/)

## Quick Start

1. Clone the repository:
   ```bash
   git clone https://github.com/dustinwicker/denver-rec-centers.git
   cd denver-rec-centers
   ```

2. Start a local server:
   ```bash
   python3 -m http.server 8000
   ```

3. Open http://localhost:8000 in your browser

## Project Structure

```
denver_rec_centers/
├── index.html              # Main HTML file
├── src/
│   ├── script.js           # Calendar logic and rendering
│   ├── style.css           # Styles (including responsive/dark mode)
│   ├── scrape_schedule.py  # Scrapes schedule from GroupExPro
│   ├── manual_json.py      # Parses scraped data into JSON
│   └── distances.py        # Calculates distances via Google Maps API
└── data/
    ├── week_manifest.json          # Week metadata
    ├── denver_2025_*.json          # Daily schedule files
    ├── rec_centers_distances.json  # Pre-calculated distances
    └── class_descriptions.json     # Class descriptions
```

## Updating Schedule Data

### 1. Scrape the latest schedule

```bash
cd src
python3 scrape_schedule.py
```

This uses Selenium to scrape the schedule from [GroupExPro](https://groupexpro.com/schedule/522/) and saves raw data to the `data/` folder.

### 2. Parse into daily JSON files

```bash
python3 manual_json.py
```

This creates individual JSON files for each day of the week.

### 3. Update distances (optional)

If you want to update distances from a different origin:

```bash
export GOOGLE_MAPS_API_KEY="your-api-key"
python3 distances.py
```

Requires a Google Maps API key with the Directions API enabled.

## Dependencies

**Frontend:** Pure HTML/CSS/JavaScript (no frameworks)

**Python scripts (for data generation):**
- `selenium` - Web scraping
- `webdriver-manager` - Chrome driver management
- `pandas` - Data manipulation
- `googlemaps` - Google Maps API client

Install with:
```bash
pip install selenium webdriver-manager pandas googlemaps
```

## Data Sources

- **Schedule data:** [GroupExPro - Denver Recreation](https://groupexpro.com/schedule/522/)
- **Recreation center info:** [Denver Parks & Recreation](https://denvergov.org/Government/Agencies-Departments-Offices/Agencies-Departments-Offices-Directory/Parks-Recreation/Recreation-Centers-Pools/Recreation-Centers)

## License

MIT License - feel free to use and modify!

## Contributing

Contributions welcome! Feel free to open issues or submit pull requests.

