"""
Calculate driving, walking, and biking distances/times to Denver Recreation Centers 
using Google Maps Directions API.

Setup:
1. Enable the Directions API in Google Cloud Console:
   https://console.cloud.google.com/apis/library/directions-backend.googleapis.com
2. Set your API key as an environment variable:
   export GOOGLE_MAPS_API_KEY="your-api-key-here"
"""
import json
import os
from pathlib import Path
import googlemaps
from datetime import datetime
import pandas as pd

pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)
pd.set_option('display.max_colwidth', None)

# Get the data directory
try:
    SCRIPT_DIR = Path(__file__).parent
    DATA_DIR = SCRIPT_DIR.parent / "data"
except NameError:
    DATA_DIR = Path("/Users/dustinwicker/projects/denver_rec_centers/data")


def load_rec_centers():
    """Load recreation centers from JSON file."""
    with open(DATA_DIR / "rec_centers.json", 'r') as f:
        data = json.load(f)
    return data['rec_centers']


def get_directions_info(gmaps, origin, destination, mode="driving"):
    """
    Get distance and time between two addresses for a given travel mode.
    
    Args:
        gmaps: Google Maps client
        origin: Starting address
        destination: Ending address
        mode: "driving", "walking", "bicycling", or "transit"
    
    Returns:
        dict with distance_miles, duration_minutes, duration_text, distance_text
    """
    try:
        # Use departure_time for driving (traffic estimates), not for other modes
        kwargs = {
            "origin": origin,
            "destination": destination,
            "mode": mode
        }
        if mode == "driving":
            kwargs["departure_time"] = datetime.now()
        
        result = gmaps.directions(**kwargs)
        
        if result and len(result) > 0:
            leg = result[0]['legs'][0]
            
            # Get distance in miles
            distance_meters = leg['distance']['value']
            distance_miles = distance_meters / 1609.34
            
            # Get duration (with traffic if available for driving)
            if mode == "driving" and 'duration_in_traffic' in leg:
                duration_seconds = leg['duration_in_traffic']['value']
                duration_text = leg['duration_in_traffic']['text']
            else:
                duration_seconds = leg['duration']['value']
                duration_text = leg['duration']['text']
            
            duration_minutes = duration_seconds / 60
            
            return {
                "distance_miles": round(distance_miles, 1),
                "distance_text": leg['distance']['text'],
                "duration_minutes": round(duration_minutes, 0),
                "duration_text": duration_text
            }
        else:
            return None
            
    except Exception as e:
        print(f"    Error getting {mode} directions: {e}")
        return None


def calculate_all_distances(origin_address):
    """
    Calculate driving, walking, biking, and transit distances/times from origin to all recreation centers.
    
    Args:
        origin_address: Your starting address (e.g., "1600 Broadway, Denver, CO")
    
    Returns:
        DataFrame with all distances and times
    """
    # Get API key
    api_key = os.environ.get('GOOGLE_MAPS_API_KEY')
    if not api_key:
        print("ERROR: GOOGLE_MAPS_API_KEY environment variable not set!")
        print("\nTo set it, run:")
        print('  export GOOGLE_MAPS_API_KEY="your-api-key-here"')
        return None
    
    # Initialize Google Maps client
    gmaps = googlemaps.Client(key=api_key)
    
    # Load recreation centers
    centers = load_rec_centers()
    
    print(f"Calculating distances from: {origin_address}")
    print(f"To {len(centers)} recreation centers...")
    print(f"Modes: driving, walking, bicycling, transit")
    print("-" * 60)
    
    results = []
    
    for i, center in enumerate(centers):
        destination = f"{center['address']}, {center['city']}, {center['state']}"
        print(f"[{i+1}/{len(centers)}] {center['name']}...")
        
        row = {
            "name": center['name'],
            "tier": center['tier'],
            "address": center['address'],
            "full_address": destination,
            "phone": center['phone'],
            "email": center['email']
        }
        
        # Get driving info
        driving = get_directions_info(gmaps, origin_address, destination, "driving")
        if driving:
            row["driving_miles"] = driving['distance_miles']
            row["driving_minutes"] = driving['duration_minutes']
            row["driving_time"] = driving['duration_text']
            print(f"    🚗 Driving: {driving['distance_text']} / {driving['duration_text']}")
        else:
            row["driving_miles"] = None
            row["driving_minutes"] = None
            row["driving_time"] = None
        
        # Get walking info
        walking = get_directions_info(gmaps, origin_address, destination, "walking")
        if walking:
            row["walking_miles"] = walking['distance_miles']
            row["walking_minutes"] = walking['duration_minutes']
            row["walking_time"] = walking['duration_text']
            print(f"    🚶 Walking: {walking['distance_text']} / {walking['duration_text']}")
        else:
            row["walking_miles"] = None
            row["walking_minutes"] = None
            row["walking_time"] = None
        
        # Get biking info
        biking = get_directions_info(gmaps, origin_address, destination, "bicycling")
        if biking:
            row["biking_miles"] = biking['distance_miles']
            row["biking_minutes"] = biking['duration_minutes']
            row["biking_time"] = biking['duration_text']
            print(f"    🚴 Biking: {biking['distance_text']} / {biking['duration_text']}")
        else:
            row["biking_miles"] = None
            row["biking_minutes"] = None
            row["biking_time"] = None
        
        # Get transit info
        transit = get_directions_info(gmaps, origin_address, destination, "transit")
        if transit:
            row["transit_miles"] = transit['distance_miles']
            row["transit_minutes"] = transit['duration_minutes']
            row["transit_time"] = transit['duration_text']
            print(f"    🚌 Transit: {transit['distance_text']} / {transit['duration_text']}")
        else:
            row["transit_miles"] = None
            row["transit_minutes"] = None
            row["transit_time"] = None
        
        results.append(row)
    
    # Create DataFrame
    df = pd.DataFrame(results)
    
    # Sort by driving time
    df = df.sort_values('driving_minutes').reset_index(drop=True)
    
    return df


def find_nearest(origin_address, n=8, save_results=True):
    """
    Find the N nearest recreation centers by driving time.
    Calculates driving, walking, biking, and transit times for all centers.
    
    Args:
        origin_address: Your starting address
        n: Number of nearest centers to display (default 8)
        save_results: Whether to save results to CSV and JSON
    
    Returns:
        DataFrame with all results (sorted by driving time)
    """
    df = calculate_all_distances(origin_address)
    
    if df is None or df.empty:
        return None
    
    print("\n" + "=" * 70)
    print(f"TOP {n} NEAREST RECREATION CENTERS BY DRIVING TIME")
    print(f"From: {origin_address}")
    print("=" * 70)
    
    for i, row in df.head(n).iterrows():
        print(f"\n{i+1}. {row['name']} ({row['tier']})")
        print(f"   📍 {row['address']}")
        print(f"   🚗 Drive:   {row['driving_miles']} mi / {row['driving_time']}")
        print(f"   🚴 Bike:    {row['biking_miles']} mi / {row['biking_time']}")
        print(f"   🚶 Walk:    {row['walking_miles']} mi / {row['walking_time']}")
        if pd.notna(row.get('transit_time')):
            print(f"   🚌 Transit: {row['transit_miles']} mi / {row['transit_time']}")
        print(f"   📞 {row['phone']}")
    
    if save_results:
        # Save to CSV
        csv_file = DATA_DIR / "rec_centers_distances.csv"
        df.to_csv(csv_file, index=False)
        print(f"\n✓ Saved CSV to {csv_file}")
        
        # Save to JSON
        json_output = {
            "origin": origin_address,
            "calculated_at": datetime.now().isoformat(),
            "centers": df.to_dict(orient='records')
        }
        json_file = DATA_DIR / "rec_centers_distances.json"
        with open(json_file, 'w') as f:
            json.dump(json_output, f, indent=2)
        print(f"✓ Saved JSON to {json_file}")
    
    return df


def print_summary_table(df, n=10):
    """Print a compact summary table of the nearest centers."""
    print("\n" + "=" * 80)
    print(f"{'#':<3} {'Name':<35} {'Drive':<12} {'Bike':<12} {'Walk':<12}")
    print("=" * 80)
    
    for i, row in df.head(n).iterrows():
        print(f"{i+1:<3} {row['name']:<35} {row['driving_time']:<12} {row['biking_time']:<12} {row['walking_time']:<12}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Denver Recreation Center Distance Calculator")
        print("=" * 50)
        print("\nUsage:")
        print("  python driving_distances.py <your-address>")
        print()
        print("Examples:")
        print('  python driving_distances.py "1600 Broadway, Denver, CO"')
        print('  python driving_distances.py "2401 E Colfax Ave, Denver, CO"')
        print()
        print("Make sure to set your Google Maps API key:")
        print('  export GOOGLE_MAPS_API_KEY="your-api-key-here"')
        sys.exit(1)
    
    # Join all arguments as the address
    address = " ".join(sys.argv[1:])
    
    # Find nearest centers
    df = find_nearest(address, n=8)
    
    if df is not None:
        print("\n")
        print_summary_table(df, n=10)
