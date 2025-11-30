"""
Scrape Denver Recreation Center schedule from GroupExPro website using Selenium.
Uses the ?view=new URL which includes cancelled class information.
Supports scraping multiple weeks (current, past, and future).
"""
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime, timedelta
from pathlib import Path
import time
import re
import json

# Base URL for schedule
BASE_URL = "https://groupexpro.com/schedule/522/?view=new"

# Get the data directory (works both in script and interactive mode)
try:
    SCRIPT_DIR = Path(__file__).parent
    DATA_DIR = SCRIPT_DIR.parent / "data"
except NameError:
    # Running in interactive mode (Jupyter/IPython)
    DATA_DIR = Path("/Users/dustinwicker/projects/denver_rec_centers/data")


def get_week_start(date):
    """Get the Sunday that starts the week containing the given date."""
    # GroupExPro weeks start on Sunday
    days_since_sunday = date.weekday() + 1  # Monday=0, so Sunday=6+1=7, but we want 0
    if date.weekday() == 6:  # Sunday
        days_since_sunday = 0
    return date - timedelta(days=days_since_sunday)


def scrape_week(target_date=None, driver=None):
    """
    Scrape a single week's schedule.
    
    Args:
        target_date: A date within the week to scrape. Defaults to today.
        driver: Optional existing webdriver instance.
    
    Returns:
        dict: Events by day for the week
    """
    if target_date is None:
        target_date = datetime.now().date()
    elif isinstance(target_date, datetime):
        target_date = target_date.date()
    
    # Build URL with date parameter
    url = f"{BASE_URL}&date={target_date.isoformat()}"
    
    close_driver = False
    if driver is None:
        driver = create_driver()
        close_driver = True
    
    all_events = {}
    
    try:
        print(f"Fetching week containing {target_date}...")
        print(f"URL: {url}")
        driver.get(url)
        
        # Wait for page to load
        print("Waiting for page to load...")
        time.sleep(5)
        
        # Find day tabs
        day_tabs = driver.find_elements(By.CSS_SELECTOR, ".day-tab, [class*='day-selector'] > div, .calendar-day")
        if not day_tabs:
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
        
        return all_events
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        if close_driver:
            driver.quit()
            print("Browser closed.")


def create_driver():
    """Create and configure a Chrome webdriver."""
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    print(f"Starting browser...")
    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )


def scrape_multiple_weeks(weeks_back=1, weeks_forward=2):
    """
    Scrape multiple weeks of schedule data.
    
    Args:
        weeks_back: Number of weeks in the past to scrape (default 1)
        weeks_forward: Number of weeks in the future to scrape (default 2)
    
    Returns:
        list: List of week manifest info
    """
    today = datetime.now().date()
    current_week_start = get_week_start(today)
    
    all_weeks = []
    driver = create_driver()
    
    try:
        # Calculate all weeks to scrape
        weeks_to_scrape = []
        for i in range(-weeks_back, weeks_forward + 1):
            week_start = current_week_start + timedelta(weeks=i)
            weeks_to_scrape.append(week_start)
        
        print(f"\nWill scrape {len(weeks_to_scrape)} weeks:")
        for ws in weeks_to_scrape:
            week_end = ws + timedelta(days=6)
            print(f"  - {ws} to {week_end}")
        print()
        
        # Scrape each week
        for week_start in weeks_to_scrape:
            week_end = week_start + timedelta(days=6)
            print(f"\n{'='*50}")
            print(f"Scraping week: {week_start} to {week_end}")
            print(f"{'='*50}")
            
            all_events = scrape_week(week_start, driver)
            
            if all_events:
                # Save daily files and week manifest
                week_info = save_week_files(all_events, week_start, week_end)
                all_weeks.append(week_info)
            else:
                print(f"No events found for week {week_start}")
        
        # Create master manifest linking all weeks
        save_master_manifest(all_weeks)
        
        return all_weeks
        
    finally:
        driver.quit()
        print("\nBrowser closed.")


def save_week_files(all_events, week_start, week_end):
    """Save individual day JSON files and a week manifest with date range in filename."""
    
    # Format dates for filename
    start_str = week_start.strftime('%Y_%m_%d')
    end_str = week_end.strftime('%Y_%m_%d')
    manifest_filename = f"manifest_{start_str}_to_{end_str}.json"
    
    # Save each day
    for date_str, day_data in all_events.items():
        filename = DATA_DIR / f"denver_{date_str.replace('-', '_')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(day_data, f, indent=2)
        print(f"Saved {filename.name}")
    
    # Create week manifest
    manifest = {
        'week_start': week_start.isoformat(),
        'week_end': week_end.isoformat(),
        'display_range': f"{week_start.strftime('%B %d')} - {week_end.strftime('%B %d, %Y')}",
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
    
    manifest_file = DATA_DIR / manifest_filename
    with open(manifest_file, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)
    print(f"Saved {manifest_file.name}")
    
    return {
        'file': manifest_filename,
        'week_start': week_start.isoformat(),
        'week_end': week_end.isoformat(),
        'display_range': manifest['display_range'],
        'day_count': len(manifest['days']),
        'event_count': sum(d['event_count'] for d in manifest['days'])
    }


def save_master_manifest(all_weeks):
    """Save a master manifest that links all week manifests together."""
    
    # Sort weeks by start date
    all_weeks_sorted = sorted(all_weeks, key=lambda w: w['week_start'])
    
    master = {
        'generated': datetime.now().isoformat(),
        'weeks': all_weeks_sorted,
        'current_week': None
    }
    
    # Identify current week
    today = datetime.now().date().isoformat()
    for week in all_weeks_sorted:
        if week['week_start'] <= today <= week['week_end']:
            master['current_week'] = week['file']
            break
    
    # Also create/update week_manifest.json to point to current week for backwards compatibility
    if master['current_week']:
        current_week_file = DATA_DIR / master['current_week']
        if current_week_file.exists():
            with open(current_week_file, 'r') as f:
                current_week_data = json.load(f)
            with open(DATA_DIR / 'week_manifest.json', 'w') as f:
                json.dump(current_week_data, f, indent=2)
            print("Updated week_manifest.json to current week")
    
    master_file = DATA_DIR / "master_manifest.json"
    with open(master_file, 'w', encoding='utf-8') as f:
        json.dump(master, f, indent=2)
    print(f"\nSaved {master_file.name}")
    print(f"  Total weeks: {len(all_weeks_sorted)}")
    print(f"  Current week: {master['current_week']}")


def scrape_schedule():
    """
    Legacy function - scrapes current week only.
    For multiple weeks, use scrape_multiple_weeks().
    """
    all_events = scrape_week()
    
    if all_events:
        # Save the rendered HTML
        # Note: We can't save HTML when using shared driver, skip for now
        
        # Get week range
        dates = sorted(all_events.keys())
        if dates:
            week_start = datetime.fromisoformat(dates[0]).date()
            week_end = datetime.fromisoformat(dates[-1]).date()
            save_week_files(all_events, week_start, week_end)
    
    return all_events


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


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Scrape Denver Recreation Center schedules')
    parser.add_argument('--weeks-back', type=int, default=0, 
                        help='Number of weeks in the past to scrape (default: 0)')
    parser.add_argument('--weeks-forward', type=int, default=1,
                        help='Number of weeks in the future to scrape (default: 1)')
    parser.add_argument('--current-only', action='store_true',
                        help='Only scrape the current week')
    
    args = parser.parse_args()
    
    if args.current_only:
        print("Scraping current week only...")
        scrape_schedule()
    else:
        print(f"Scraping {args.weeks_back} weeks back and {args.weeks_forward} weeks forward...")
        scrape_multiple_weeks(weeks_back=args.weeks_back, weeks_forward=args.weeks_forward)
    
    print("\nDone!")
