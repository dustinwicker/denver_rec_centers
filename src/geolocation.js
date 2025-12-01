/**
 * Geolocation and Distance Service
 * Uses browser geolocation + OpenRouteService for accurate routing distances
 * 
 * OpenRouteService free tier: 2,000 requests/day
 * Sign up at: https://openrouteservice.org/dev/#/signup
 */

const GeoService = (() => {
  const CACHE_KEY = 'denver_rec_geo_cache';
  const ORS_API_KEY_STORAGE = 'denver_rec_ors_api_key';
  const LOCATION_THRESHOLD_MILES = 0.25; // Recalculate if moved more than 0.25 miles
  const ORS_BASE_URL = 'https://api.openrouteservice.org';
  
  // Recreation center coordinates (geocoded from addresses)
  const REC_CENTERS = [
    { name: "Ashland", lat: 39.7433, lng: -104.9686, address: "1600 E 19th Ave, Denver, CO 80218" },
    { name: "Athmar", lat: 39.6958, lng: -105.0206, address: "1200 S Hazel Ct, Denver, CO 80219" },
    { name: "Barnum", lat: 39.7261, lng: -105.0297, address: "360 Hooker St, Denver, CO 80219" },
    { name: "Carla Madison", lat: 39.7400, lng: -104.9528, address: "2401 E Colfax Ave, Denver, CO 80206" },
    { name: "Central Park", lat: 39.7583, lng: -104.8686, address: "9651 E Martin Luther King Jr Blvd, Denver, CO 80238" },
    { name: "Cook Park", lat: 39.6506, lng: -104.9336, address: "7100 S Cherry Creek Dr, Denver, CO 80224" },
    { name: "Dunham", lat: 39.7486, lng: -105.0294, address: "1355 Osceola St, Denver, CO 80204" },
    { name: "Glenarm", lat: 39.7528, lng: -104.9847, address: "2800 Glenarm Pl, Denver, CO 80205" },
    { name: "Green Valley Ranch", lat: 39.8347, lng: -104.7697, address: "4890 Argonne St, Denver, CO 80249" },
    { name: "Harvey Park", lat: 39.6761, lng: -105.0503, address: "2120 S Tennyson St, Denver, CO 80219" },
    { name: "Hiawatha Davis", lat: 39.7597, lng: -104.9281, address: "3334 Holly St, Denver, CO 80207" },
    { name: "Highland", lat: 39.7667, lng: -105.0167, address: "2880 Osceola St, Denver, CO 80212" },
    { name: "La Alma", lat: 39.7333, lng: -105.0047, address: "1325 W 11th Ave, Denver, CO 80204" },
    { name: "La Familia", lat: 39.7119, lng: -104.9869, address: "65 S Elati St, Denver, CO 80223" },
    { name: "Martin Luther King Jr", lat: 39.7597, lng: -104.9119, address: "3880 Newport St, Denver, CO 80207" },
    { name: "Montbello", lat: 39.7833, lng: -104.8333, address: "15555 E 53rd Ave, Denver, CO 80239" },
    { name: "Montclair", lat: 39.7167, lng: -104.9167, address: "729 Ulster Way, Denver, CO 80220" },
    { name: "Paco Sanchez", lat: 39.7394, lng: -105.0456, address: "4701 W 10th Ave, Denver, CO 80204" },
    { name: "Platt Park", lat: 39.6833, lng: -104.9833, address: "1500 S Grant St, Denver, CO 80210" },
    { name: "Rude", lat: 39.7314, lng: -105.0078, address: "2855 W Holden Pl, Denver, CO 80204" },
    { name: "Scheitler", lat: 39.7778, lng: -105.0461, address: "5031 W 46th Ave, Denver, CO 80212" },
    { name: "St. Charles", lat: 39.7611, lng: -104.9542, address: "3777 Lafayette St, Denver, CO 80205" },
    { name: "Stapleton", lat: 39.7667, lng: -104.8833, address: "3815 N Magnolia St, Denver, CO 80207" },
    { name: "Twentieth Street", lat: 39.7475, lng: -104.9867, address: "1011 20th St, Denver, CO 80205" },
    { name: "Virginia Village", lat: 39.6833, lng: -104.9167, address: "2250 S Dahlia St, Denver, CO 80222" },
    { name: "Washington Park", lat: 39.6972, lng: -104.9722, address: "701 S Franklin St, Denver, CO 80209" },
    { name: "Woodbury", lat: 39.6850, lng: -104.9078, address: "3101 S Grape St, Denver, CO 80222" }
  ];

  // ORS profile names
  const ORS_PROFILES = {
    driving: 'driving-car',
    biking: 'cycling-regular',
    walking: 'foot-walking'
  };

  /**
   * Get or prompt for API key
   */
  function getApiKey() {
    return localStorage.getItem(ORS_API_KEY_STORAGE);
  }

  function setApiKey(key) {
    localStorage.setItem(ORS_API_KEY_STORAGE, key);
  }

  function clearApiKey() {
    localStorage.removeItem(ORS_API_KEY_STORAGE);
  }

  /**
   * Calculate distance between two coordinates in miles (Haversine formula)
   */
  function haversineDistance(lat1, lng1, lat2, lng2) {
    const R = 3959; // Earth's radius in miles
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLng = (lng2 - lng1) * Math.PI / 180;
    const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
              Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
              Math.sin(dLng/2) * Math.sin(dLng/2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    return R * c;
  }

  /**
   * Get user's current location via browser geolocation
   */
  function getCurrentPosition() {
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) {
        reject(new Error('Geolocation not supported'));
        return;
      }
      
      navigator.geolocation.getCurrentPosition(
        (position) => {
          resolve({
            lat: position.coords.latitude,
            lng: position.coords.longitude,
            accuracy: position.coords.accuracy
          });
        },
        (error) => {
          reject(error);
        },
        {
          enableHighAccuracy: true,
          timeout: 10000,
          maximumAge: 60000 // Cache position for 1 minute
        }
      );
    });
  }

  /**
   * Calculate distances using OpenRouteService Matrix API
   * @param {number} userLat - User's latitude
   * @param {number} userLng - User's longitude
   * @param {string} profile - 'driving', 'biking', or 'walking'
   */
  async function calculateDistancesORS(userLat, userLng, profile) {
    const apiKey = getApiKey();
    if (!apiKey) {
      console.warn('No ORS API key set');
      return null;
    }

    const orsProfile = ORS_PROFILES[profile] || ORS_PROFILES.driving;
    
    // Build locations array: user first, then all rec centers
    const locations = [[userLng, userLat], ...REC_CENTERS.map(c => [c.lng, c.lat])];
    
    const url = `${ORS_BASE_URL}/v2/matrix/${orsProfile}`;
    
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Authorization': apiKey,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          locations: locations,
          sources: [0], // Only from user location
          metrics: ['distance', 'duration'],
          units: 'm' // meters
        })
      });
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.error?.message || `ORS request failed: ${response.status}`);
      }
      
      const data = await response.json();
      
      // Extract distances and durations from user (source 0) to all destinations
      const distances = data.distances[0].slice(1); // Skip first (user to user = 0)
      const durations = data.durations[0].slice(1);
      
      return REC_CENTERS.map((center, i) => ({
        name: center.name,
        address: center.address,
        lat: center.lat,
        lng: center.lng,
        [`${profile}_meters`]: distances[i],
        [`${profile}_miles`]: distances[i] ? (distances[i] / 1609.34).toFixed(1) : null,
        [`${profile}_seconds`]: durations[i],
        [`${profile}_minutes`]: durations[i] ? Math.round(durations[i] / 60) : null,
        [`${profile}_time`]: durations[i] ? formatDuration(durations[i]) : 'N/A'
      }));
    } catch (error) {
      console.error(`ORS ${profile} calculation failed:`, error);
      return null;
    }
  }

  /**
   * Format seconds into human-readable duration
   */
  function formatDuration(seconds) {
    if (!seconds) return 'N/A';
    const mins = Math.round(seconds / 60);
    if (mins < 60) return `${mins} mins`;
    const hours = Math.floor(mins / 60);
    const remainingMins = mins % 60;
    return `${hours} hr ${remainingMins} mins`;
  }

  /**
   * Calculate all distances (driving, biking, walking) for user location
   */
  async function calculateAllDistances(userLat, userLng, onProgress) {
    const results = {
      origin: { lat: userLat, lng: userLng },
      timestamp: Date.now(),
      centers: []
    };
    
    // Initialize centers with basic info and straight-line distances
    results.centers = REC_CENTERS.map(c => ({
      name: c.name,
      address: c.address,
      lat: c.lat,
      lng: c.lng,
      straight_line_miles: haversineDistance(userLat, userLng, c.lat, c.lng).toFixed(1)
    }));
    
    // Use realistic estimates based on straight-line distance
    // Roads are typically 1.3-1.4x longer than straight-line in urban areas
    const ROAD_FACTOR = 1.35;
    
    // Realistic average speeds for Denver urban area (accounting for traffic, lights, stops)
    // These are effective speeds, not top speeds
    const SPEEDS = {
      driving: 18,  // ~18 mph average in city (traffic, lights, parking)
      biking: 10,   // ~10 mph average (includes hills, stops)
      walking: 3    // ~3 mph average
    };
    
    console.log('Calculating distances with realistic city estimates');
    
    results.centers.forEach(c => {
      const straightDist = parseFloat(c.straight_line_miles);
      const roadDist = (straightDist * ROAD_FACTOR).toFixed(1);
      
      // Driving
      c.driving_miles = roadDist;
      c.driving_minutes = Math.round((parseFloat(roadDist) / SPEEDS.driving) * 60);
      c.driving_time = `~${c.driving_minutes} mins`;
      c.driving_estimated = true; // Flag to show "~" in UI
      
      // Biking
      c.biking_miles = roadDist;
      c.biking_minutes = Math.round((parseFloat(roadDist) / SPEEDS.biking) * 60);
      c.biking_time = `~${c.biking_minutes} mins`;
      c.biking_estimated = true;
      
      // Walking
      c.walking_miles = roadDist;
      c.walking_minutes = Math.round((parseFloat(roadDist) / SPEEDS.walking) * 60);
      c.walking_time = `~${c.walking_minutes} mins`;
      c.walking_estimated = true;
    });
    
    // Mark this data as estimated
    results.estimated = true;
    
    return results;
  }

  /**
   * Get cached data if user hasn't moved significantly
   */
  function getCachedData() {
    try {
      const cached = localStorage.getItem(CACHE_KEY);
      if (!cached) return null;
      return JSON.parse(cached);
    } catch (e) {
      return null;
    }
  }

  /**
   * Save data to cache
   */
  function setCachedData(data) {
    try {
      localStorage.setItem(CACHE_KEY, JSON.stringify(data));
    } catch (e) {
      console.warn('Could not cache distance data:', e);
    }
  }

  /**
   * Check if user has moved significantly from cached location
   */
  function hasMovedSignificantly(currentLat, currentLng, cachedLat, cachedLng) {
    const distance = haversineDistance(currentLat, currentLng, cachedLat, cachedLng);
    return distance > LOCATION_THRESHOLD_MILES;
  }

  /**
   * Main function: Get distances for current user location
   * Uses cache if user hasn't moved, otherwise recalculates
   */
  async function getDistances(onProgress, forceRefresh = false) {
    // Try to get current position
    let userLocation;
    try {
      if (onProgress) onProgress('Getting your location...', 0);
      userLocation = await getCurrentPosition();
    } catch (error) {
      console.warn('Could not get location:', error.message);
      // Return cached data if available, otherwise null
      const cached = getCachedData();
      if (cached) {
        return { data: cached, source: 'cache', error: 'Location unavailable, using cached data' };
      }
      return { data: null, source: 'none', error: 'Location unavailable and no cached data' };
    }
    
    // Check cache
    const cached = getCachedData();
    
    if (!forceRefresh && cached && cached.origin) {
      const moved = hasMovedSignificantly(
        userLocation.lat, userLocation.lng,
        cached.origin.lat, cached.origin.lng
      );
      
      if (!moved) {
        console.log('Using cached distances (within 0.25 miles of cached location)');
        return { data: cached, source: 'cache', userLocation };
      } else {
        console.log('User moved significantly, recalculating distances');
      }
    }
    
    // Calculate new distances
    if (onProgress) onProgress('Calculating distances to rec centers...', 10);
    
    const newData = await calculateAllDistances(userLocation.lat, userLocation.lng, onProgress);
    
    // Cache the results
    setCachedData(newData);
    
    if (onProgress) onProgress('Done!', 100);
    
    return { data: newData, source: 'calculated', userLocation };
  }

  /**
   * Clear cached data
   */
  function clearCache() {
    localStorage.removeItem(CACHE_KEY);
  }

  /**
   * Get rec center coordinates for a given name
   */
  function getRecCenterCoords(name) {
    const searchName = name.toLowerCase();
    return REC_CENTERS.find(c => 
      c.name.toLowerCase().includes(searchName) || 
      searchName.includes(c.name.toLowerCase())
    );
  }

  /**
   * Check if API key is configured
   */
  function hasApiKey() {
    return !!getApiKey();
  }

  // Public API
  return {
    getDistances,
    getCurrentPosition,
    clearCache,
    getCachedData,
    getRecCenterCoords,
    haversineDistance,
    hasApiKey,
    getApiKey,
    setApiKey,
    clearApiKey,
    REC_CENTERS
  };
})();

// Export for use in script.js
if (typeof window !== 'undefined') {
  window.GeoService = GeoService;
}
