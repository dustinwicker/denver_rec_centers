"""
Parse weekly schedule text file and create JSON files for each day.
"""
import json
import re
from pathlib import Path
from datetime import datetime

# Get the data directory
try:
    SCRIPT_DIR = Path(__file__).parent
    DATA_DIR = SCRIPT_DIR.parent / "data"
except NameError:
    # Running in interactive mode (Jupyter/IPython)
    DATA_DIR = Path("/Users/dustinwicker/projects/denver_rec_centers/data")

# Schedule file to parse (update this to match your file)
SCHEDULE_FILE = DATA_DIR / "schedule_11_24_11_30_2025.txt"

def parse_weekly_schedule(filepath):
    """Parse the weekly schedule and return events grouped by day."""
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.splitlines()
    
    # Pattern to match day headers like "Monday, November 24, 2025"
    day_pattern = re.compile(r'^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+(\w+)\s+(\d{1,2}),\s+(\d{4})$')
    
    # Pattern to match time range at the start of a line like "5:30am-9:00am Lap Swim"
    time_class_pattern = re.compile(r'^(\d{1,2}:\d{2}(?:am|pm))\s*-\s*(\d{1,2}:\d{2}(?:am|pm))\s+(.+)$')
    
    # Find all day header positions (skip the first occurrence which is in the filter section)
    day_positions = []
    for i, line in enumerate(lines):
        match = day_pattern.match(line.strip())
        if match and i > 100:  # Skip the filter section at the top
            day_name, month_name, day_num, year = match.groups()
            day_positions.append({
                'index': i,
                'day_name': day_name,
                'month_name': month_name,
                'day_num': int(day_num),
                'year': int(year)
            })
    
    print(f"Found {len(day_positions)} days in schedule")
    
    # Parse events for each day
    all_days = {}
    
    for idx, day_info in enumerate(day_positions):
        start_idx = day_info['index'] + 1
        end_idx = day_positions[idx + 1]['index'] if idx + 1 < len(day_positions) else len(lines)
        
        day_lines = lines[start_idx:end_idx]
        
        events = []
        i = 0
        while i < len(day_lines):
            line = day_lines[i].strip()
            
            # Skip empty lines and special markers
            if not line or line in ['Add to Calendar', 'See More', 'Sign Up »', 'zumba_fitness.jpg', 'logo_41484.jpg']:
                i += 1
                continue
            
            # Check if this line starts with a time range
            time_match = time_class_pattern.match(line)
            if time_match:
                start_time, end_time, class_name = time_match.groups()
                
                # Next line should have instructor, studio, category, duration, location
                if i + 1 < len(day_lines):
                    detail_line = day_lines[i + 1].strip()
                    
                    # Parse the detail line
                    # Format: "NA - No Instructor Lap Pool Aquatics (AQ) 210 Carla Madison Description »"
                    # or: "Andrea Charry Spin Studio Fitness (FIT) 45 Central Park Description »"
                    
                    # Remove "Description »" at the end
                    detail_line = re.sub(r'\s*Description\s*»\s*$', '', detail_line)
                    
                    # Try to extract category (in parentheses)
                    category_match = re.search(r'\(([A-Z]+)\)', detail_line)
                    category = category_match.group(1) if category_match else ''
                    
                    # Try to extract duration (number before location)
                    duration_match = re.search(r'\s(\d+)\s+([A-Za-z])', detail_line)
                    
                    # Known locations to help parsing
                    known_locations = [
                        'Carla Madison', 'Central Park', 'Glenarm', 'Rude', 'Athmar', 'Aztlan',
                        'Barnum', 'Berkeley', 'Harvey Park', 'Highland', 'Johnson', 'La Alma',
                        'La Familia', 'Martin Luther King Jr.', 'Montbello', 'Montclair',
                        'Scheitler', 'Southwest', 'Swansea', 'Washington Park', 'Ashland',
                        'Green Valley Ranch', 'Hiawatha Davis Jr.', 'St. Charles', 'Twentieth Street',
                        'City Park', 'College View', 'Cook Park', 'Eisenhower', 'Harvard Gulch',
                        'Platt Park', 'Ruby Hill Park', 'Sloan\'s Lake'
                    ]
                    
                    location = ''
                    for loc in known_locations:
                        if loc in detail_line:
                            location = loc
                            break
                    
                    # If no known location found, try to extract from the end
                    if not location:
                        # Try to get text after the duration number
                        if duration_match:
                            after_duration = detail_line[duration_match.end()-1:].strip()
                            location = after_duration
                    
                    # Extract instructor (before the studio/category info)
                    instructor = ''
                    if 'NA - No Instructor' in detail_line:
                        instructor = 'NA - No Instructor'
                    else:
                        # Try to get instructor name (usually first two words)
                        parts = detail_line.split()
                        if len(parts) >= 2:
                            instructor = f"{parts[0]} {parts[1]}"
                    
                    # Extract studio (text between instructor and category)
                    studio = ''
                    if category_match:
                        # Get text between instructor and category
                        cat_pos = detail_line.find(f'({category})')
                        if cat_pos > 0:
                            before_cat = detail_line[:cat_pos].strip()
                            # Remove instructor from the beginning
                            if instructor and before_cat.startswith(instructor):
                                studio = before_cat[len(instructor):].strip()
                    
                    # Check if cancelled
                    is_cancelled = 'Cancelled' in class_name or 'Cancelled' in detail_line
                    
                    events.append({
                        "start_time": start_time,
                        "end_time": end_time,
                        "class_name": class_name.replace('Cancelled', '').strip(),
                        "studio": studio,
                        "instructor": instructor,
                        "location": location,
                        "category": category,
                        "cancelled": is_cancelled
                    })
                    
                    i += 2  # Skip the detail line
                    continue
            
            i += 1
        
        # Create date key
        month_map = {
            'January': 1, 'February': 2, 'March': 3, 'April': 4,
            'May': 5, 'June': 6, 'July': 7, 'August': 8,
            'September': 9, 'October': 10, 'November': 11, 'December': 12
        }
        month_num = month_map.get(day_info['month_name'], 1)
        date_str = f"{day_info['year']}-{month_num:02d}-{day_info['day_num']:02d}"
        
        all_days[date_str] = {
            'day_name': day_info['day_name'],
            'date': date_str,
            'display_date': f"{day_info['day_name']}, {day_info['month_name']} {day_info['day_num']}, {day_info['year']}",
            'events': events
        }
        
        print(f"  {day_info['day_name']} {day_info['month_name']} {day_info['day_num']}: {len(events)} events")
    
    return all_days

def save_daily_json_files(all_days):
    """Save each day's events to a separate JSON file."""
    
    for date_str, day_data in all_days.items():
        filename = DATA_DIR / f"denver_{date_str.replace('-', '_')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(day_data, f, indent=2)
        print(f"Saved {filename.name}")

def save_week_manifest(all_days):
    """Save a manifest file with info about all available days."""
    
    manifest = {
        'days': []
    }
    
    for date_str, day_data in sorted(all_days.items()):
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
    
    return manifest

if __name__ == "__main__":
    print(f"Parsing {SCHEDULE_FILE}...")
    all_days = parse_weekly_schedule(SCHEDULE_FILE)
    
    print(f"\nSaving daily JSON files...")
    save_daily_json_files(all_days)
    
    print(f"\nSaving week manifest...")
    manifest = save_week_manifest(all_days)
    
    print(f"\nDone! Created {len(all_days)} daily files.")
