"""
Scrape Denver Recreation Center schedule from GroupExPro website using Selenium.
Uses the ?view=new URL which includes cancelled class information.
Clicks through each day to get the full week's schedule.
"""
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime
from pathlib import Path
import time
import re
import json

# Add Sign Up functionality (add little button to go directly to sign up page)

# Use the new view URL which has cancelled information
URL = "https://groupexpro.com/schedule/522/?view=new"

# Get the data directory (works both in script and interactive mode)
try:
    SCRIPT_DIR = Path(__file__).parent
    DATA_DIR = SCRIPT_DIR.parent / "data"
except NameError:
    # Running in interactive mode (Jupyter/IPython)
    DATA_DIR = Path("/Users/dustinwicker/projects/denver_rec_centers/data")

def scrape_schedule():
    """Scrape the schedule using Selenium (handles JavaScript)."""
    # Setup Chrome options
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    print(f"Starting browser...")
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    
    all_events = {}
    
    try:
        print(f"Fetching {URL}...")
        driver.get(URL)
        
        # Wait for page to load
        print("Waiting for page to load...")
        time.sleep(5)
        
        # Find day tabs
        day_tabs = driver.find_elements(By.CSS_SELECTOR, ".day-tab, [class*='day-selector'] > div, .calendar-day")
        if not day_tabs:
            # Try alternative selectors
            day_tabs = driver.find_elements(By.XPATH, "//div[contains(@class, 'day')]")
        
        print(f"Found {len(day_tabs)} day tabs")
        
        # If we can't find clickable day tabs, just parse the current view
        if len(day_tabs) < 2:
            print("Could not find day tabs, parsing current view only...")
            events = parse_current_day(driver)
            if events:
                for date_key, day_data in events.items():
                    all_events[date_key] = day_data
        else:
            # Click through each day tab
            for i, tab in enumerate(day_tabs):
                try:
                    tab_text = tab.text.strip()
                    print(f"Clicking day tab {i+1}: {tab_text}")
                    tab.click()
                    time.sleep(3)  # Wait for content to load
                    
                    events = parse_current_day(driver)
                    if events:
                        for date_key, day_data in events.items():
                            all_events[date_key] = day_data
                except Exception as e:
                    print(f"Error clicking tab {i}: {e}")
        
        # If still no events, try parsing the full page text
        if not all_events:
            print("Trying full page parse...")
            all_events = parse_full_page(driver)
        
        # Save the rendered HTML
        html = driver.page_source
        with open(DATA_DIR / 'schedule_raw.html', 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"Saved raw HTML to {DATA_DIR}/schedule_raw.html")
        
        # Save parsed events
        if all_events:
            # Save as single parsed file
            json_filename = DATA_DIR / 'schedule_parsed.json'
            with open(json_filename, 'w', encoding='utf-8') as f:
                json.dump(all_events, f, indent=2)
            print(f"Saved parsed schedule to {json_filename}")
            
            # Also save individual day files and manifest
            save_daily_files(all_events)
        
        return all_events
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        driver.quit()
        print("Browser closed.")


def parse_current_day(driver):
    """Parse the currently displayed day's events."""
    events_by_day = {}
    
    body_text = driver.find_element(By.TAG_NAME, 'body').text
    lines = body_text.split('\n')
    
    current_day = None
    current_day_key = None
    i = 0
    
    # Day pattern like "Friday, November 28"
    day_pattern = re.compile(r'^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+(\w+)\s+(\d{1,2})$')
    # Time pattern like "12:30am-2:30pm"
    time_pattern = re.compile(r'^(\d{1,2}:\d{2}(?:am|pm))\s*-\s*(\d{1,2}:\d{2}(?:am|pm))$')
    
    while i < len(lines):
        line = lines[i].strip()
        
        # Check for day header
        day_match = day_pattern.match(line)
        if day_match:
            day_name, month_name, day_num = day_match.groups()
            month_map = {
                'January': 1, 'February': 2, 'March': 3, 'April': 4,
                'May': 5, 'June': 6, 'July': 7, 'August': 8,
                'September': 9, 'October': 10, 'November': 11, 'December': 12
            }
            month_num = month_map.get(month_name, 1)
            
            # Determine year (handle year boundary)
            current_month = datetime.now().month
            year = datetime.now().year
            if month_num < current_month - 6:  # Likely next year
                year += 1
            
            current_day_key = f"{year}-{month_num:02d}-{int(day_num):02d}"
            current_day = {
                'day_name': day_name,
                'date': current_day_key,
                'display_date': f"{day_name}, {month_name} {day_num}, {year}",
                'events': []
            }
            events_by_day[current_day_key] = current_day
            i += 1
            continue
        
        # Check for time range (start of an event)
        time_match = time_pattern.match(line)
        if time_match and current_day:
            start_time, end_time = time_match.groups()
            
            # Look ahead for event details
            event_lines = []
            j = i + 1
            while j < len(lines) and j < i + 15:
                next_line = lines[j].strip()
                if not next_line:
                    j += 1
                    continue
                # Stop if we hit another time or day
                if time_pattern.match(next_line) or day_pattern.match(next_line):
                    break
                event_lines.append(next_line)
                j += 1
            
            # Parse event details
            class_name = event_lines[0] if len(event_lines) > 0 else "Unknown"
            studio = event_lines[1] if len(event_lines) > 1 else ""
            instructor = ""
            location = ""
            category = ""
            is_cancelled = False
            
            # Check for cancelled and sign-up required in any line
            requires_signup = False
            for el in event_lines:
                if el == 'Cancelled':
                    is_cancelled = True
                if 'Sign Up' in el or 'Reserve' in el:
                    requires_signup = True
            
            # Extract instructor (usually has a period at the end or is "NA - No Instructor")
            for el in event_lines:
                if 'NA - No Instructor' in el:
                    instructor = 'NA - No Instructor'
                    break
                elif el.endswith('.') and len(el.split()) <= 3:
                    instructor = el.rstrip('.')
                    break
            
            # Extract location and category
            known_locations = [
                'Carla Madison', 'Central Park', 'Glenarm', 'Rude', 'Athmar', 'Aztlan',
                'Barnum', 'Harvey Park', 'Highland', 'Johnson', 'La Alma', 'La Familia',
                'Martin Luther King Jr.', 'Montbello', 'Montclair', 'Scheitler',
                'Southwest', 'Washington Park', 'Ashland', 'Green Valley Ranch',
                'College View', 'City Park', 'Hiawatha Davis Jr.', 'St. Charles',
                'Twentieth Street', 'Swansea', 'Harvard Gulch', 'Sloan\'s Lake',
                '5090 Broadway', 'Cook Park', 'Eisenhower', 'Platt Park', 'Ruby Hill Park'
            ]
            
            for el in event_lines:
                # Check for location
                for loc in known_locations:
                    if loc in el:
                        location = loc
                        break
                # Check for category
                cat_match = re.search(r'\(([A-Z]+)\)', el)
                if cat_match:
                    category = cat_match.group(1)
            
            # Clean up studio (remove trailing spaces)
            studio = studio.rstrip()
            
            current_day['events'].append({
                'start_time': start_time,
                'end_time': end_time,
                'class_name': class_name,
                'studio': studio,
                'instructor': instructor,
                'location': location,
                'category': category,
                'cancelled': is_cancelled,
                'requires_signup': requires_signup
            })
            
            i = j
            continue
        
        i += 1
    
    return events_by_day


def parse_full_page(driver):
    """Parse the full page text for all days."""
    return parse_current_day(driver)


def save_daily_files(all_events):
    """Save individual day JSON files and a manifest."""
    
    # Save each day
    for date_str, day_data in all_events.items():
        filename = DATA_DIR / f"denver_{date_str.replace('-', '_')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(day_data, f, indent=2)
        print(f"Saved {filename.name}")
    
    # Create manifest
    manifest = {
        'days': []
    }
    
    for date_str, day_data in sorted(all_events.items()):
        manifest['days'].append({
            'date': date_str,
            'day_name': day_data['day_name'],
            'display_date': day_data['display_date'],
            'event_count': len(day_data['events']),
            'file': f"denver_{date_str.replace('-', '_')}.json"
        })
    
    manifest_file = DATA_DIR / "week_manifest.json"
    with open(manifest_file, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)
    print(f"Saved {manifest_file.name}")


if __name__ == "__main__":
    scrape_schedule()
    print("\nDone!")
