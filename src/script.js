(() => {
  const qs = sel => document.querySelector(sel);
  const qsa = sel => Array.from(document.querySelectorAll(sel));
  const el = (tag, cls) => { const e = document.createElement(tag); if(cls) e.className=cls; return e; };

  const palette = ["#4f46e5","#0ea5e9","#ef4444","#f97316","#06b6d4","#8b5cf6","#f59e0b","#10b981","#f43f5e","#6366f1","#14b8a6","#ec4899"];

  const colorFor = (() => {
    const cache = {};
    return (name) => {
      if(!name) return palette[0];
      if(cache[name]) return cache[name];
      let hash = 0;
      for(let i=0; i<name.length; i++) hash = ((hash << 5) - hash) + name.charCodeAt(i);
      const idx = Math.abs(hash) % palette.length;
      cache[name] = palette[idx];
      return cache[name];
    };
  })();

  const toggleDark = qs('#toggle-dark');
  const statusEl = qs('#status');
  const dayTabsEl = qs('#day-tabs');
  const weekHeaderEl = qs('#week-header');
  const prevWeekBtn = qs('#prev-week');
  const nextWeekBtn = qs('#next-week');
  const distanceSortSel = qs('#distance-sort');
  const gymLimitSel = qs('#gym-limit');
  
  // Master manifest for multi-week navigation
  let masterManifest = null;
  let currentWeekIndex = 0;

  const startHourSel = qs('#start-hour');
  const endHourSel = qs('#end-hour');
  for(let h=0; h<=23; h++) {
    const o = document.createElement('option');
    o.value = h;
    o.textContent = (h%12||12) + (h<12?'am':'pm');
    startHourSel.appendChild(o.cloneNode(true));
    endHourSel.appendChild(o.cloneNode(true));
  }
  startHourSel.value = 5;
  endHourSel.value = 22;

  const THEME_KEY = 'swimcal_theme';
  function setTheme(isDark) {
    if(isDark) document.documentElement.classList.add('dark');
    else document.documentElement.classList.remove('dark');
    localStorage.setItem(THEME_KEY, isDark ? 'dark' : 'light');
  }
  setTheme(localStorage.getItem(THEME_KEY) === 'dark');
  toggleDark.addEventListener('click', () => setTheme(!document.documentElement.classList.contains('dark')));

  // Store parsed data globally for filtering
  let allData = [];
  let allGyms = [];
  let allClasses = [];
  let weekManifest = null;
  let currentDayIndex = 0;
  let distancesData = null; // Store distances data
  let classDescriptions = {}; // Store class descriptions
  let locationStatus = 'unknown'; // 'unknown', 'loading', 'granted', 'denied', 'cached'
  let userLocation = null;

  // Store static (Google Maps) distances data
  let staticDistancesData = null;
  let homeLocation = null; // User's home location from static data
  
  // Load distances data - uses static Google Maps data when at home, dynamic when away
  async function loadDistancesData() {
    // First load static Google Maps data (always available as fallback)
    try {
      const response = await fetch('data/rec_centers_distances.json');
      if (response.ok) {
        staticDistancesData = await response.json();
        distancesData = staticDistancesData; // Use as default
        
        // Parse home location from origin address
        // Origin is "1220 Lafayette St, Denver, CO 80218"
        // Exact GPS coordinates from user's location
        homeLocation = { lat: 39.735607, lng: -104.970528 }; // 1220 Lafayette St, Denver (exact coordinates)
        
        console.log('Loaded static Google Maps distances for', staticDistancesData.centers?.length, 'centers');
      }
    } catch(e) {
      console.log('No static distances data available');
    }
    
    // Then check if user is away from home - if so, use dynamic distances
    // IMPORTANT: This will check location and use static data if at home
    if (typeof GeoService !== 'undefined') {
      await checkLocationAndLoadDistances();
    } else {
      // If GeoService not available, just use static data
      distancesData = staticDistancesData;
    }
  }
  
  // Check if user is at home or away, load appropriate distances
  async function checkLocationAndLoadDistances() {
    locationStatus = 'loading';
    updateLocationIndicator();
    
    try {
      const userPos = await GeoService.getCurrentPosition();
      userLocation = userPos;
      
      // ALWAYS check if user is at home FIRST, before using any cached dynamic data
      if (homeLocation && staticDistancesData) {
        const distanceFromHome = GeoService.haversineDistance(
          userPos.lat, userPos.lng,
          homeLocation.lat, homeLocation.lng
        );
        
        if (distanceFromHome <= 0.1) {
          // User is at home - use accurate Google Maps data
          distancesData = staticDistancesData;
          locationStatus = 'home';
          
          // Clear any cached dynamic data since we're using static
          if (typeof GeoService !== 'undefined') {
            GeoService.clearCache();
          }
          
          updateLocationIndicator();
          
          // Re-apply filters to update the display with Google Maps data
          if (allData.length > 0) {
            applyFilters();
          }
          return; // IMPORTANT: Return early, don't load dynamic distances
        }
      }
      
      // Only get here if user is away from home - use dynamic distances
      await loadDynamicDistances(false);
      
    } catch (e) {
      console.log('Could not get location, using static data:', e.message);
      distancesData = staticDistancesData; // Fall back to static data
      locationStatus = 'denied';
      updateLocationIndicator();
    }
  }
  
  // Load dynamic distances based on user's current location
  async function loadDynamicDistances(forceRefresh = false) {
    if (typeof GeoService === 'undefined') {
      console.log('GeoService not available');
      return;
    }
    
    locationStatus = 'loading';
    updateLocationIndicator();
    
    try {
      const result = await GeoService.getDistances((msg, pct) => {
        console.log(`[Geo] ${msg} (${pct}%)`);
      }, forceRefresh);
      
      if (result.data) {
        distancesData = result.data;
        userLocation = result.userLocation;
        locationStatus = result.source === 'cache' ? 'cached' : 'granted';
        console.log(`Loaded ${result.source} distances for ${distancesData.centers?.length} centers`);
        
        // Re-apply filters to update the display with new distances
        if (allData.length > 0) {
          applyFilters();
        }
      } else {
        locationStatus = 'denied';
        console.log('Could not get location-based distances:', result.error);
      }
    } catch (e) {
      locationStatus = 'denied';
      console.error('Error loading dynamic distances:', e);
    }
    
    updateLocationIndicator();
  }
  
  // Update the location indicator in the UI
  function updateLocationIndicator() {
    let indicator = qs('#location-indicator');
    if (!indicator) return;
    
    const hasApiKey = typeof GeoService !== 'undefined' && GeoService.hasApiKey();
    
    switch (locationStatus) {
      case 'loading':
        indicator.innerHTML = '📍 <span>Getting location...</span>';
        indicator.className = 'location-indicator loading';
        break;
      case 'home':
        indicator.innerHTML = '🏠 <span>At home</span> <button id="refresh-location" title="Refresh location">↻</button>';
        indicator.className = 'location-indicator home';
        break;
      case 'granted':
        indicator.innerHTML = '📍 <span>Your location</span> <button id="refresh-location" title="Refresh location">↻</button>' + 
          (!hasApiKey ? ' <button id="setup-api-key" title="Add API key for accurate times">⚙️</button>' : '');
        indicator.className = 'location-indicator active';
        break;
      case 'cached':
        indicator.innerHTML = '📍 <span>Away (cached)</span> <button id="refresh-location" title="Refresh location">↻</button>' +
          (!hasApiKey ? ' <button id="setup-api-key" title="Add API key for accurate times">⚙️</button>' : '');
        indicator.className = 'location-indicator cached';
        break;
      case 'denied':
        indicator.innerHTML = '📍 <span>Location off</span> <button id="refresh-location" title="Try again">↻</button>';
        indicator.className = 'location-indicator denied';
        break;
      default:
        indicator.innerHTML = '📍 <span>Enable location</span>';
        indicator.className = 'location-indicator unknown';
    }
    
    // Add click handler for refresh button
    const refreshBtn = indicator.querySelector('#refresh-location');
    if (refreshBtn) {
      refreshBtn.onclick = (e) => {
        e.stopPropagation();
        loadDynamicDistances(true);
      };
    }
    
    // Add click handler for API key setup
    const apiKeyBtn = indicator.querySelector('#setup-api-key');
    if (apiKeyBtn) {
      apiKeyBtn.onclick = (e) => {
        e.stopPropagation();
        showApiKeyModal();
      };
    }
  }
  
  // Show modal for API key setup
  function showApiKeyModal() {
    const existingModal = qs('.event-modal-overlay');
    if (existingModal) existingModal.remove();
    
    const currentKey = typeof GeoService !== 'undefined' ? GeoService.getApiKey() || '' : '';
    
    const overlay = el('div', 'event-modal-overlay');
    const modal = el('div', 'event-modal api-key-modal');
    
    modal.innerHTML = `
      <button class="modal-close" title="Close">&times;</button>
      <h2 class="modal-title">🔑 OpenRouteService API Key</h2>
      <div class="api-key-info">
        <p>For <strong>accurate</strong> driving/biking/walking times, add a free OpenRouteService API key.</p>
        <p class="api-key-note">Without an API key, times are estimated from straight-line distances.</p>
        <ol>
          <li>Go to <a href="https://openrouteservice.org/dev/#/signup" target="_blank">openrouteservice.org</a></li>
          <li>Sign up for a free account</li>
          <li>Copy your API key from the dashboard</li>
          <li>Paste it below</li>
        </ol>
        <p class="api-key-free">✓ Free tier: 2,000 requests/day (plenty for personal use)</p>
      </div>
      <div class="api-key-input-group">
        <input type="text" id="api-key-input" placeholder="Paste your API key here" value="${currentKey}" />
      </div>
      <div class="modal-actions">
        <button class="modal-btn primary" id="save-api-key">💾 Save Key</button>
        ${currentKey ? '<button class="modal-btn secondary" id="clear-api-key">🗑️ Clear Key</button>' : ''}
        <button class="modal-btn tertiary cancel-btn">Cancel</button>
      </div>
    `;
    
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    
    // Save handler
    modal.querySelector('#save-api-key').addEventListener('click', () => {
      const key = modal.querySelector('#api-key-input').value.trim();
      if (key) {
        GeoService.setApiKey(key);
        GeoService.clearCache(); // Clear cache to recalculate with new API
        overlay.remove();
        loadDynamicDistances(true); // Recalculate with new API key
      }
    });
    
    // Clear handler
    const clearBtn = modal.querySelector('#clear-api-key');
    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        GeoService.clearApiKey();
        GeoService.clearCache();
        overlay.remove();
        loadDynamicDistances(true);
      });
    }
    
    // Close handlers
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) overlay.remove();
    });
    modal.querySelector('.modal-close').addEventListener('click', () => overlay.remove());
    modal.querySelector('.cancel-btn').addEventListener('click', () => overlay.remove());
  }

  // Load class descriptions
  async function loadClassDescriptions() {
    try {
      const response = await fetch('data/class_descriptions.json');
      if (response.ok) {
        classDescriptions = await response.json();
        console.log('Loaded descriptions for', Object.keys(classDescriptions).length, 'classes');
      }
    } catch(e) {
      console.log('No class descriptions available');
    }
  }

  // Get description for a class (tries exact match, then partial match)
  function getClassDescription(className) {
    if (!className) return null;
    
    // Try exact match first
    if (classDescriptions[className]) {
      return classDescriptions[className];
    }
    
    // Try partial match (e.g., "Zumba Gold®" matches "Zumba Gold")
    const lowerName = className.toLowerCase();
    for (const [key, desc] of Object.entries(classDescriptions)) {
      if (lowerName.includes(key.toLowerCase()) || key.toLowerCase().includes(lowerName)) {
        return desc;
      }
    }
    
    return null;
  }

  // Get distance info for a gym
  function getDistanceInfo(gymName) {
    if (!distancesData || !distancesData.centers) return null;
    
    // Try to match gym name (handle slight variations)
    const center = distancesData.centers.find(c => {
      const centerName = c.name.replace(' Recreation Center', '').toLowerCase();
      const searchName = gymName.toLowerCase();
      return centerName.includes(searchName) || searchName.includes(centerName);
    });
    
    return center || null;
  }

  // Get sorted gyms based on distance type
  function getSortedGymsByDistance(gymNames, sortType) {
    if (!distancesData || !distancesData.centers || sortType === 'name') {
      return gymNames.slice().sort();
    }
    
    const gymsWithDistance = gymNames.map(name => {
      const info = getDistanceInfo(name);
      let sortValue = Infinity;
      
      if (info) {
        switch(sortType) {
          case 'driving':
            sortValue = info.driving_minutes || Infinity;
            break;
          case 'biking':
            sortValue = info.biking_minutes || Infinity;
            break;
          case 'walking':
            sortValue = info.walking_minutes || Infinity;
            break;
        }
      }
      
      return { name, sortValue, info };
    });
    
    gymsWithDistance.sort((a, b) => a.sortValue - b.sortValue);
    return gymsWithDistance.map(g => g.name);
  }

  function parseJsonSchedule(dayData) {
    // dayData is now the day object with events array
    const events = dayData.events || [];
    
    allData = events.map(ev => ({
      gym: ev.location || ev.location_name || 'Unknown',
      className: ev.class_name || ev.title || 'Event',
      category: ev.category || '',
      studio: ev.studio || '',
      instructor: ev.instructor || '',
      start: ev.start_time,
      end: ev.end_time,
      cancelled: ev.cancelled || false,
      requiresSignup: ev.requires_signup || false
    }));
    
    // Get unique gyms and classes sorted
    allGyms = [...new Set(allData.map(d => d.gym))].sort();
    allClasses = [...new Set(allData.map(d => d.className))].sort();
    
    return groupDataByGym(allData);
  }
  
  function groupDataByGym(data, skipLimit = false) {
    const gymsMap = {};
    data.forEach(item => {
      if(!gymsMap[item.gym]) gymsMap[item.gym] = [];
      gymsMap[item.gym].push(item);
    });
    
    // Get sort type and limit
    const sortType = distanceSortSel ? distanceSortSel.value : 'biking';
    const limitValue = gymLimitSel ? gymLimitSel.value : '8';
    const limit = limitValue === 'all' ? Infinity : parseInt(limitValue, 10);
    
    // Sort gyms by selected distance type
    let gymNames = Object.keys(gymsMap);
    gymNames = getSortedGymsByDistance(gymNames, sortType);
    
    // Apply limit (unless gyms were manually selected)
    if (!skipLimit && limit < gymNames.length) {
      gymNames = gymNames.slice(0, limit);
    }
    
    const gyms = gymNames.map(g => ({
      gym: g,
      items: gymsMap[g]
    }));
    return { gyms };
  }

  function normalizeTimeString(s) {
    if(!s) return s;
    s = s.replace(/\s+/g,'').toLowerCase().replace(/\./g,'');
    // Handle times like "6pm" -> "6:00pm"
    if(/^\d{1,2}(am|pm)$/.test(s)) s = s.replace(/(\d{1,2})(am|pm)/,'$1:00$2');
    return s;
  }
  function timeToMinutes(t) {
    if(!t) return 0;
    t = normalizeTimeString(t);
    // Match patterns like "6:00pm", "12:30am", etc.
    const m = t.match(/(\d{1,2}):(\d{2})(am|pm)/i);
    if(!m) {
      console.warn('Could not parse time:', t);
      return 0;
    }
    let hh = parseInt(m[1],10);
    const mm = parseInt(m[2],10);
    const ampm = m[3].toLowerCase();
    
    // Convert to 24-hour format
    if(ampm === 'pm' && hh !== 12) hh += 12;
    if(ampm === 'am' && hh === 12) hh = 0;
    
    const result = hh * 60 + mm;
    return result;
  }

  const calendarRoot = qs('#calendar-root');

  function clearCalendar() {
    calendarRoot.innerHTML = '';
  }
  
  // Create Google Maps directions link based on travel mode
  function createGoogleMapsDirectionsLink(destination, travelMode) {
    const encodedDest = encodeURIComponent(destination);
    let mode = 'driving';
    
    switch(travelMode) {
      case 'walking':
        mode = 'walking';
        break;
      case 'biking':
        mode = 'bicycling';
        break;
      default:
        mode = 'driving';
    }
    
    // Uses current location as origin (empty origin parameter)
    return `https://www.google.com/maps/dir/?api=1&destination=${encodedDest}&travelmode=${mode}`;
  }

  // Calculate columns for overlapping events
  function calculateEventColumns(items, startHour, endHour) {
    const positions = [];
    const activeEvents = []; // Track events that are currently "active" (not yet ended)
    
    items.forEach((item, idx) => {
      const startMins = timeToMinutes(item.start);
      const endMins = timeToMinutes(item.end);
      
      // Skip events outside visible range
      if (endMins <= startHour * 60 || startMins >= endHour * 60) {
        positions[idx] = { column: 0, totalColumns: 1 };
        return;
      }
      
      // Remove events that have ended before this one starts
      const stillActive = activeEvents.filter(e => e.endMins > startMins);
      
      // Find the first available column
      const usedColumns = new Set(stillActive.map(e => e.column));
      let column = 0;
      while (usedColumns.has(column)) {
        column++;
      }
      
      // Add this event to active list
      const eventInfo = { idx, startMins, endMins, column };
      stillActive.push(eventInfo);
      activeEvents.length = 0;
      activeEvents.push(...stillActive);
      
      positions[idx] = { column, totalColumns: 1 }; // totalColumns updated later
    });
    
    // Second pass: calculate total columns for each group of overlapping events
    items.forEach((item, idx) => {
      const startMins = timeToMinutes(item.start);
      const endMins = timeToMinutes(item.end);
      
      // Find all events that overlap with this one
      let maxColumn = positions[idx].column;
      items.forEach((other, otherIdx) => {
        if (idx === otherIdx) return;
        const otherStart = timeToMinutes(other.start);
        const otherEnd = timeToMinutes(other.end);
        
        // Check if they overlap
        if (startMins < otherEnd && endMins > otherStart) {
          maxColumn = Math.max(maxColumn, positions[otherIdx].column);
        }
      });
      
      positions[idx].totalColumns = maxColumn + 1;
    });
    
    // Third pass: ensure all overlapping events have the same totalColumns
    items.forEach((item, idx) => {
      const startMins = timeToMinutes(item.start);
      const endMins = timeToMinutes(item.end);
      
      items.forEach((other, otherIdx) => {
        if (idx === otherIdx) return;
        const otherStart = timeToMinutes(other.start);
        const otherEnd = timeToMinutes(other.end);
        
        if (startMins < otherEnd && endMins > otherStart) {
          const maxCols = Math.max(positions[idx].totalColumns, positions[otherIdx].totalColumns);
          positions[idx].totalColumns = maxCols;
          positions[otherIdx].totalColumns = maxCols;
        }
      });
    });
    
    return positions;
  }

  function renderCalendar(parsed) {
    clearCalendar();
    // Clear time indicator tracking
    timeIndicatorElements = [];
    
    const gyms = parsed.gyms || [];
    if(!gyms.length) {
      calendarRoot.innerHTML = '<div style="padding:20px">No events found.</div>';
      return;
    }

    const startHour = parseInt(startHourSel.value, 10) || 5;
    const endHour = parseInt(endHourSel.value, 10) || 22;
    // Get hour height from CSS variable (responsive - 56px desktop, 48px mobile)
    const hourHeight = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--hour-height')) || 56;
    const totalHeight = (endHour - startHour) * hourHeight;

    // Get current sort type for display
    const sortType = distanceSortSel ? distanceSortSel.value : 'biking';

    // Create scroll container to sync time column and gym columns
    const scrollContainer = el('div', 'calendar-scroll');
    
    const timeCol = el('div', 'time-col');
    // Add empty header to match gym column headers
    const timeHeader = el('div', 'time-header');
    timeHeader.textContent = '';
    timeCol.appendChild(timeHeader);
    
    for(let h = startHour; h < endHour; h++) {
      const slot = el('div', 'time-slot');
      slot.textContent = (h%12||12) + (h<12?'am':'pm');
      timeCol.appendChild(slot);
    }

    const gymsWrapper = el('div', 'days-wrapper');

    // Each gym is a column
    gyms.forEach(gymData => {
      const gymName = gymData.gym;
      const gymColor = colorFor(gymName);
      const distanceInfo = getDistanceInfo(gymName);
      
      const col = el('div', 'day-column');
      col.dataset.gym = gymName;
      
      const hd = el('div', 'day-header');
      hd.style.background = gymColor;
      hd.style.color = '#fff';
      
      // Create header content with gym name and distance info
      const headerContent = el('div', 'header-content');
      const nameDiv = el('div', 'gym-name');
      nameDiv.textContent = gymName;
      headerContent.appendChild(nameDiv);
      
      // Add distance info based on sort type
      if (distanceInfo && sortType !== 'name') {
        const distDiv = el('div', 'gym-distance');
        let distText = '';
        let icon = '';
        
        switch(sortType) {
          case 'driving':
            icon = '🚗';
            distText = `${distanceInfo.driving_miles} mi, ${distanceInfo.driving_time}`;
            break;
          case 'biking':
            icon = '🚴';
            distText = `${distanceInfo.biking_miles} mi, ${distanceInfo.biking_time}`;
            break;
          case 'walking':
            icon = '🚶';
            distText = `${distanceInfo.walking_miles} mi, ${distanceInfo.walking_time}`;
            break;
        }
        
        distDiv.innerHTML = `${icon} ${distText}`;
        headerContent.appendChild(distDiv);
      }
      
      // Add directions button if we have address info
      const gymAddress = distanceInfo?.full_address || distanceInfo?.address || `${gymName} Recreation Center, Denver, CO`;
      if (gymAddress) {
        const directionsBtn = el('a', 'directions-btn');
        directionsBtn.href = createGoogleMapsDirectionsLink(gymAddress, sortType);
        directionsBtn.target = '_blank';
        directionsBtn.title = 'Get directions';
        directionsBtn.innerHTML = '📍';
        directionsBtn.addEventListener('click', (e) => e.stopPropagation());
        headerContent.appendChild(directionsBtn);
      }
      
      hd.appendChild(headerContent);
      hd.style.cursor = 'pointer';
      hd.addEventListener('click', () => {
        window.open(createGoogleMapsDirectionsLink(gymAddress, sortType), '_blank');
      });
      col.appendChild(hd);
      
      const grid = el('div', 'hour-grid');
      grid.style.height = totalHeight + 'px';
      grid.style.minHeight = totalHeight + 'px';
      col.appendChild(grid);

      // Sort items by start time
      const sortedItems = gymData.items.slice().sort((a, b) => timeToMinutes(a.start) - timeToMinutes(b.start));
      
      // Calculate overlapping events and assign columns
      const eventPositions = calculateEventColumns(sortedItems, startHour, endHour);
      
      sortedItems.forEach((item, idx) => {
        const startMins = timeToMinutes(item.start);
        const endMins = timeToMinutes(item.end);
        
        // Skip events completely outside the time range
        if (endMins <= startHour * 60 || startMins >= endHour * 60) return;
        
        // Clamp to visible range
        const visibleStart = Math.max(startMins, startHour * 60);
        const visibleEnd = Math.min(endMins, endHour * 60);
        
        const topPx = (visibleStart - startHour * 60) / 60 * hourHeight;
        const heightPx = Math.max(24, (visibleEnd - visibleStart) / 60 * hourHeight);
        
        const ev = el('div', 'event');
        ev.style.background = gymColor;
        ev.style.top = topPx + 'px';
        ev.style.height = heightPx + 'px';
        
        // Apply column positioning for overlapping events
        const pos = eventPositions[idx];
        if (pos && pos.totalColumns > 1) {
          const colWidth = 100 / pos.totalColumns;
          ev.style.left = (pos.column * colWidth) + '%';
          ev.style.width = colWidth + '%';
          ev.style.right = 'auto';
        }
        
        // Add cancelled class if applicable
        if (item.cancelled) {
          ev.classList.add('cancelled');
        }
        
        ev.innerHTML = `<div class="title">${item.className}</div><div class="meta">${item.start} - ${item.end}</div>`;
        if(item.studio) {
          ev.innerHTML += `<div class="studio">${item.studio}</div>`;
        }
        if(item.category) {
          ev.innerHTML += `<div class="category">${item.category}</div>`;
        }
        if(item.cancelled) {
          ev.innerHTML += `<div class="cancelled-label">CANCELLED</div>`;
        }
        
        // Add action buttons (Add to Calendar, Sign Up if required)
        if (!item.cancelled) {
          const actions = el('div', 'event-actions');
          
          // Google Calendar link
          const calLink = createGoogleCalendarLink(item, gymName);
          actions.innerHTML = `<a href="${calLink}" target="_blank" class="event-btn cal-btn" title="Add to Google Calendar">📅</a>`;
          
          // Sign Up link (only if requires signup) - shows confirmation modal
          if (item.requiresSignup) {
            const signUpBtn = el('button', 'event-btn signup-btn');
            signUpBtn.innerHTML = '🎟️';
            signUpBtn.title = 'Sign Up / Reserve';
            signUpBtn.addEventListener('click', (e) => {
              e.stopPropagation();
              showExternalLinkModal(item.className, gymName);
            });
            actions.appendChild(signUpBtn);
          }
          
          ev.appendChild(actions);
        }
        
        // Add click handler to show event details modal
        ev.addEventListener('click', (e) => {
          // Don't trigger if clicking on action buttons
          if (e.target.closest('.event-actions')) return;
          showEventModal(item, gymName);
        });
        ev.style.cursor = 'pointer';
        
        ev.dataset.className = item.className;
        grid.appendChild(ev);
      });
      
      // Add current time indicator to this gym's grid
      const isFirstGym = gymsWrapper.children.length === 0;
      addCurrentTimeIndicator(grid, startHour, endHour, hourHeight, isFirstGym);
      
      gymsWrapper.appendChild(col);
    });

    // Add time column and gyms wrapper to scroll container
    scrollContainer.appendChild(timeCol);
    scrollContainer.appendChild(gymsWrapper);
    calendarRoot.appendChild(scrollContainer);
  }
  
  // Create Google Calendar link for an event
  function createGoogleCalendarLink(item, gymName) {
    // Get current selected day's date
    const currentDay = weekManifest?.days?.[currentDayIndex];
    const dateStr = currentDay?.date || new Date().toISOString().split('T')[0];
    
    // Parse start and end times
    const startTime = parseTimeToISO(item.start, dateStr);
    const endTime = parseTimeToISO(item.end, dateStr);
    
    const title = encodeURIComponent(`${item.className} @ ${gymName}`);
    const details = encodeURIComponent(`Class: ${item.className}\nStudio: ${item.studio || 'N/A'}\nCategory: ${item.category || 'N/A'}\nInstructor: ${item.instructor || 'N/A'}`);
    const location = encodeURIComponent(`${gymName} Recreation Center, Denver, CO`);
    
    return `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${title}&dates=${startTime}/${endTime}&details=${details}&location=${location}`;
  }
  
  // Parse time string to Google Calendar format (YYYYMMDDTHHMMSS)
  function parseTimeToISO(timeStr, dateStr) {
    const normalized = normalizeTimeString(timeStr);
    const m = normalized.match(/(\d{1,2}):(\d{2})(am|pm)/i);
    if (!m) return '';
    
    let hours = parseInt(m[1], 10);
    const mins = parseInt(m[2], 10);
    const ampm = m[3].toLowerCase();
    
    if (ampm === 'pm' && hours !== 12) hours += 12;
    if (ampm === 'am' && hours === 12) hours = 0;
    
    const [year, month, day] = dateStr.split('-');
    return `${year}${month}${day}T${String(hours).padStart(2, '0')}${String(mins).padStart(2, '0')}00`;
  }
  
  // Show event details modal
  // Show confirmation modal before navigating to external sign-up page
  function showExternalLinkModal(className, gymName) {
    // Remove existing modal if any
    const existingModal = qs('.event-modal-overlay');
    if (existingModal) existingModal.remove();
    
    const signUpLink = `https://groupexpro.com/schedule/522/?view=new`;
    
    const overlay = el('div', 'event-modal-overlay');
    const modal = el('div', 'event-modal external-link-modal');
    
    modal.innerHTML = `
      <button class="modal-close" title="Close">&times;</button>
      <div class="external-link-icon">🔗</div>
      <h2 class="modal-title">Leaving This Site</h2>
      <div class="external-link-message">
        <p>You are about to leave the Denver Recreation Center Calendar to sign up for:</p>
        <div class="external-link-class">
          <strong>${className}</strong>
          <span>at ${gymName}</span>
        </div>
        <p class="external-link-url">You will be redirected to:</p>
        <code class="external-link-destination">${signUpLink}</code>
        <p class="external-link-note">This is the official GroupExPro scheduling site for Denver Recreation Centers.</p>
      </div>
      <div class="modal-actions">
        <button class="modal-btn primary continue-btn">✓ Continue to Sign Up</button>
        <button class="modal-btn secondary cancel-btn">Cancel</button>
      </div>
    `;
    
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    
    // Continue button - open link then close modal
    modal.querySelector('.continue-btn').addEventListener('click', () => {
      window.open(signUpLink, '_blank');
      overlay.remove();
    });
    
    // Close handlers
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) overlay.remove();
    });
    modal.querySelector('.modal-close').addEventListener('click', () => overlay.remove());
    modal.querySelector('.cancel-btn').addEventListener('click', () => overlay.remove());
    document.addEventListener('keydown', function escHandler(e) {
      if (e.key === 'Escape') {
        overlay.remove();
        document.removeEventListener('keydown', escHandler);
      }
    });
  }

  function showEventModal(item, gymName) {
    // Remove existing modal if any
    const existingModal = qs('.event-modal-overlay');
    if (existingModal) existingModal.remove();
    
    const currentDay = weekManifest?.days?.[currentDayIndex];
    const dateDisplay = currentDay?.display_date || 'Today';
    
    const overlay = el('div', 'event-modal-overlay');
    const modal = el('div', 'event-modal');
    
    const calLink = createGoogleCalendarLink(item, gymName);
    const signUpLink = `https://groupexpro.com/schedule/522/?view=new`;
    
    const description = getClassDescription(item.className);
    
    modal.innerHTML = `
      <button class="modal-close" title="Close">&times;</button>
      <h2 class="modal-title">${item.className}</h2>
      <div class="modal-date">${dateDisplay}</div>
      <div class="modal-time">${item.start} - ${item.end}</div>
      <div class="modal-details">
        <div class="modal-row"><span class="modal-label">Location:</span> ${gymName}</div>
        <div class="modal-row"><span class="modal-label">Studio:</span> ${item.studio || 'N/A'}</div>
        <div class="modal-row"><span class="modal-label">Category:</span> ${item.category || 'N/A'}</div>
        <div class="modal-row"><span class="modal-label">Instructor:</span> ${item.instructor || 'N/A'}</div>
      </div>
      ${item.cancelled ? '<div class="modal-cancelled">⚠️ This class has been CANCELLED</div>' : ''}
      ${description ? `
        <div class="modal-description-text">
          <strong>Description:</strong>
          <p>${description}</p>
        </div>
      ` : `
        <div class="modal-description">
          <p><em>No description available. Click "See More" on GroupExPro for details.</em></p>
        </div>
      `}
      <div class="modal-actions">
        ${!item.cancelled ? `
          <a href="${calLink}" target="_blank" class="modal-btn primary">📅 Add to Calendar</a>
          ${item.requiresSignup ? `<button class="modal-btn secondary signup-external-btn">🎟️ Sign Up / Reserve</button>` : ''}
          <a href="${signUpLink}" target="_blank" class="modal-btn tertiary">See More on GroupExPro</a>
        ` : `
          <a href="${signUpLink}" target="_blank" class="modal-btn secondary">View on GroupExPro</a>
        `}
      </div>
    `;
    
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    
    // Add click handler for sign up button to show external link modal
    const signupBtn = modal.querySelector('.signup-external-btn');
    if (signupBtn) {
      signupBtn.addEventListener('click', () => {
        overlay.remove();
        showExternalLinkModal(item.className, gymName);
      });
    }
    
    // Handle external links - open in new tab then close modal
    modal.querySelectorAll('a[target="_blank"]').forEach(link => {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        window.open(link.href, '_blank');
        // Small delay before closing to ensure the new tab opens
        setTimeout(() => overlay.remove(), 100);
      });
    });
    
    // Close handlers
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) overlay.remove();
    });
    modal.querySelector('.modal-close').addEventListener('click', () => overlay.remove());
    document.addEventListener('keydown', function escHandler(e) {
      if (e.key === 'Escape') {
        overlay.remove();
        document.removeEventListener('keydown', escHandler);
      }
    });
  }

  // Track the user-selected time (null = use current time)
  let userSelectedMinutes = null;
  let timeIndicatorElements = [];
  let currentHourHeight = 56;
  let currentStartHour = 5;
  let currentEndHour = 22;

  // Add current time indicator line to a grid
  function addCurrentTimeIndicator(grid, startHour, endHour, hourHeight, isFirst = false) {
    // Store these for drag calculations
    currentHourHeight = hourHeight;
    currentStartHour = startHour;
    currentEndHour = endHour;
    
    const now = new Date();
    const currentMins = now.getHours() * 60 + now.getMinutes();
    let displayMins = userSelectedMinutes !== null ? userSelectedMinutes : currentMins;
    
    // Clamp displayMins to visible range (with small buffer)
    const minMins = startHour * 60;
    const maxMins = endHour * 60;
    displayMins = Math.max(minMins, Math.min(maxMins, displayMins));
    
    // If user selected time is out of range, update it to be in range
    if (userSelectedMinutes !== null) {
      userSelectedMinutes = displayMins;
    }
    
    const topPx = (displayMins - startHour * 60) / 60 * hourHeight;
    
    // Add indicator line to the grid
    const timeLine = el('div', 'current-time-line');
    timeLine.style.top = topPx + 'px';
    
    // Track all time lines for synchronized updates
    timeIndicatorElements.push(timeLine);
    
    // Add draggable dot only on the first column
    if (isFirst) {
      const timeDot = el('div', 'time-dot');
      timeDot.setAttribute('draggable', 'false'); // We'll use mouse events instead
      
      // Add time label
      const timeLabel = el('div', 'time-label');
      timeLabel.textContent = formatMinutesToTime(displayMins);
      timeDot.appendChild(timeLabel);
      
      // Add reset button (only shows when user has moved the line)
      if (userSelectedMinutes !== null) {
        const resetBtn = el('div', 'time-reset');
        resetBtn.textContent = '↺';
        resetBtn.title = 'Reset to current time';
        resetBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          userSelectedMinutes = null;
          applyFilters(); // Use applyFilters instead of renderCalendar to preserve data
        });
        timeDot.appendChild(resetBtn);
      }
      
      timeLine.appendChild(timeDot);
      
      // Make the dot draggable
      setupDragHandler(timeDot, grid);
    }
    
    grid.appendChild(timeLine);
  }
  
  // Format minutes to readable time (e.g., 480 -> "8:00 AM")
  function formatMinutesToTime(totalMins) {
    let hours = Math.floor(totalMins / 60);
    const mins = totalMins % 60;
    const ampm = hours >= 12 ? 'PM' : 'AM';
    if (hours > 12) hours -= 12;
    if (hours === 0) hours = 12;
    return `${hours}:${String(mins).padStart(2, '0')} ${ampm}`;
  }
  
  // Setup drag handling for the time indicator dot
  function setupDragHandler(dot, grid) {
    let isDragging = false;
    let startY = 0;
    let startTop = 0;
    let lastValidTop = 0;
    
    const onMouseDown = (e) => {
      e.preventDefault();
      e.stopPropagation();
      isDragging = true;
      startY = e.clientY || e.touches?.[0]?.clientY || 0;
      const timeLine = dot.parentElement;
      startTop = parseFloat(timeLine.style.top) || 0;
      lastValidTop = startTop;
      
      document.body.style.userSelect = 'none';
      dot.classList.add('dragging');
    };
    
    const onMouseMove = (e) => {
      if (!isDragging) return;
      e.preventDefault();
      
      const clientY = e.clientY || e.touches?.[0]?.clientY || 0;
      const deltaY = clientY - startY;
      let newTop = startTop + deltaY;
      
      // Clamp to valid range (with a small buffer to prevent edge issues)
      const minTop = 0;
      const maxTop = (currentEndHour - currentStartHour) * currentHourHeight - 2;
      newTop = Math.max(minTop, Math.min(maxTop, newTop));
      lastValidTop = newTop;
      
      // Update all time lines
      timeIndicatorElements.forEach(line => {
        line.style.top = newTop + 'px';
      });
      
      // Calculate and display the time
      const newMins = Math.round((newTop / currentHourHeight) * 60 + currentStartHour * 60);
      const timeLabel = dot.querySelector('.time-label');
      if (timeLabel) {
        timeLabel.textContent = formatMinutesToTime(newMins);
      }
      
      // Update userSelectedMinutes in real-time (don't wait for mouseup)
      userSelectedMinutes = newMins;
    };
    
    const onMouseUp = (e) => {
      if (!isDragging) return;
      isDragging = false;
      
      document.body.style.userSelect = '';
      dot.classList.remove('dragging');
      
      // Use the last valid position
      userSelectedMinutes = Math.round((lastValidTop / currentHourHeight) * 60 + currentStartHour * 60);
      
      // Clamp userSelectedMinutes to valid range
      const minMins = currentStartHour * 60;
      const maxMins = currentEndHour * 60;
      userSelectedMinutes = Math.max(minMins, Math.min(maxMins, userSelectedMinutes));
      
      // Show reset button by adding it dynamically instead of full re-render
      if (!dot.querySelector('.time-reset')) {
        const resetBtn = document.createElement('div');
        resetBtn.className = 'time-reset';
        resetBtn.textContent = '↺';
        resetBtn.title = 'Reset to current time';
        resetBtn.addEventListener('click', (evt) => {
          evt.stopPropagation();
          userSelectedMinutes = null;
          applyFilters(); // Use applyFilters instead of renderCalendar to preserve data
        });
        dot.appendChild(resetBtn);
      }
    };
    
    // Mouse events
    dot.addEventListener('mousedown', onMouseDown);
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
    
    // Touch events for mobile
    dot.addEventListener('touchstart', onMouseDown, { passive: false });
    document.addEventListener('touchmove', onMouseMove, { passive: false });
    document.addEventListener('touchend', onMouseUp);
  }

  // Track selected filters
  let selectedGyms = [];
  let selectedClasses = []; // Empty = show all classes
  let hideCancelled = true;
  let filtersInitialized = false;

  function setupFilters() {
    if (filtersInitialized) {
      // Just update the dropdowns with new data
      updateDropdown('gym', allGyms, Infinity);
      updateDropdown('class', allClasses, Infinity);
      return;
    }
    
    const searchInput = qs('#search-text');
    const resetGymBtn = qs('#reset-gym-filter');
    const resetClassBtn = qs('#reset-class-filter');
    const resetSearchBtn = qs('#reset-search');
    const hideCancelledCheckbox = qs('#hide-cancelled');

    // Setup gym dropdown (no limit now since we use distance sorting)
    setupDropdown('gym', allGyms, Infinity);
    
    // Setup class dropdown (no limit)
    setupDropdown('class', allClasses, Infinity);

    searchInput.addEventListener('input', applyFilters);
    
    // Hide cancelled checkbox
    hideCancelledCheckbox.addEventListener('change', () => {
      hideCancelled = hideCancelledCheckbox.checked;
      applyFilters();
    });
    
    // Distance sort change
    if (distanceSortSel) {
      distanceSortSel.addEventListener('change', applyFilters);
    }
    
    // Gym limit change
    if (gymLimitSel) {
      gymLimitSel.addEventListener('change', applyFilters);
    }
    
    resetGymBtn.addEventListener('click', () => {
      selectedGyms = [];
      updateDropdown('gym', allGyms, Infinity);
      applyFilters();
    });
    
    resetClassBtn.addEventListener('click', () => {
      selectedClasses = [];
      updateDropdown('class', allClasses, Infinity);
      applyFilters();
    });
    
    resetSearchBtn.addEventListener('click', () => {
      searchInput.value = '';
      applyFilters();
    });

    // Re-render on time range change
    startHourSel.addEventListener('change', applyFilters);
    endHourSel.addEventListener('change', applyFilters);
    
    // Close dropdowns when clicking outside
    document.addEventListener('click', (e) => {
      if (!e.target.closest('.dropdown-container')) {
        qsa('.dropdown-menu').forEach(menu => menu.classList.remove('open'));
      }
    });
    
    filtersInitialized = true;
  }

  function setupDropdown(type, items, maxItems) {
    const toggle = qs(`#${type}-dropdown-toggle`);
    const menu = qs(`#${type}-dropdown-menu`);
    
    // Toggle dropdown
    toggle.addEventListener('click', (e) => {
      e.stopPropagation();
      // Close other dropdowns
      qsa('.dropdown-menu').forEach(m => {
        if (m !== menu) m.classList.remove('open');
      });
      menu.classList.toggle('open');
    });
    
    updateDropdown(type, items, maxItems);
  }

  function updateDropdown(type, items, maxItems) {
    const menu = qs(`#${type}-dropdown-menu`);
    const countEl = qs(`#${type}-count`);
    const selected = type === 'gym' ? selectedGyms : selectedClasses;
    
    menu.innerHTML = '';
    
    items.forEach(item => {
      const div = el('div', 'dropdown-item');
      const isChecked = selected.includes(item);
      const isDisabled = !isChecked && selected.length >= maxItems;
      
      if (isDisabled) div.classList.add('disabled');
      
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.checked = isChecked;
      checkbox.disabled = isDisabled;
      
      const label = document.createElement('span');
      label.textContent = item;
      
      div.appendChild(checkbox);
      div.appendChild(label);
      
      div.addEventListener('click', (e) => {
        if (isDisabled && !isChecked) return;
        e.stopPropagation();
        
        if (type === 'gym') {
          if (selectedGyms.includes(item)) {
            selectedGyms = selectedGyms.filter(g => g !== item);
          } else if (selectedGyms.length < maxItems) {
            selectedGyms.push(item);
          }
        } else {
          if (selectedClasses.includes(item)) {
            selectedClasses = selectedClasses.filter(c => c !== item);
          } else if (selectedClasses.length < maxItems) {
            selectedClasses.push(item);
          }
        }
        
        updateDropdown(type, items, maxItems);
        applyFilters();
      });
      
      menu.appendChild(div);
    });
    
    // Update count badge
    countEl.textContent = selected.length > 0 ? selected.length : '';
  }

  function applyFilters() {
    const searchInput = qs('#search-text');
    const searchQuery = searchInput.value.trim().toLowerCase();
    
    // Filter the data
    let filtered = allData;
    
    // Filter out cancelled events if checkbox is checked
    if (hideCancelled) {
      filtered = filtered.filter(d => !d.cancelled);
    }
    
    // If specific gyms are manually selected, use those
    // Otherwise, we'll apply the limit in groupDataByGym
    if (selectedGyms.length > 0) {
      filtered = filtered.filter(d => selectedGyms.includes(d.gym));
    }
    
    if (selectedClasses.length > 0) {
      filtered = filtered.filter(d => selectedClasses.includes(d.className));
    }
    
    if (searchQuery) {
      filtered = filtered.filter(d => 
        d.gym.toLowerCase().includes(searchQuery) ||
        d.className.toLowerCase().includes(searchQuery) ||
        d.category.toLowerCase().includes(searchQuery)
      );
    }
    
    // Re-render with filtered data
    // Pass whether gyms were manually selected (to skip limit if so)
    const parsed = groupDataByGym(filtered, selectedGyms.length > 0);
    renderCalendar(parsed);
    status(`Showing ${filtered.length} events`);
  }

  function status(msg) {
    if(statusEl) statusEl.textContent = msg;
  }

  // Day selector functionality
  function renderDayTabs() {
    if (!weekManifest || !weekManifest.days) return;
    
    dayTabsEl.innerHTML = '';
    
    // Get month name from first day
    const firstDay = weekManifest.days[0];
    if (firstDay) {
      const dateParts = firstDay.display_date.split(' ');
      weekHeaderEl.textContent = dateParts[1]; // Month name
    }
    
    weekManifest.days.forEach((day, index) => {
      const tab = el('div', 'day-tab');
      if (index === currentDayIndex) {
        tab.classList.add('active');
      }
      
      // Parse day info
      const dayName = day.day_name.substring(0, 3); // Mon, Tue, etc.
      const dateParts = day.date.split('-');
      const dayNum = parseInt(dateParts[2], 10);
      
      tab.innerHTML = `
        <div class="day-name">${dayName}</div>
        <div class="day-num">${dayNum}</div>
      `;
      
      tab.addEventListener('click', () => {
        currentDayIndex = index;
        loadDayData(day.file);
        renderDayTabs();
      });
      
      dayTabsEl.appendChild(tab);
    });
  }

  async function loadDayData(filename) {
    status('Loading data...');
    try {
      const response = await fetch(`data/${filename}`);
      if (!response.ok) {
        throw new Error(`Failed to load ${filename}`);
      }
      const dayData = await response.json();
      parseJsonSchedule(dayData);
      setupFilters();
      applyFilters();
    } catch(e) {
      status('Error: ' + e.message);
      console.error(e);
    }
  }

  async function loadMasterManifest() {
    try {
      const response = await fetch('data/master_manifest.json');
      if (response.ok) {
        masterManifest = await response.json();
        
        // Find current week index
        if (masterManifest.current_week) {
          currentWeekIndex = masterManifest.weeks.findIndex(w => w.file === masterManifest.current_week);
          if (currentWeekIndex === -1) currentWeekIndex = 0;
        }
        
        updateWeekNavButtons();
        return true;
      }
    } catch(e) {
      console.log('No master manifest found, using single week mode');
    }
    return false;
  }
  
  function updateWeekNavButtons() {
    if (!masterManifest || masterManifest.weeks.length <= 1) {
      prevWeekBtn.disabled = true;
      nextWeekBtn.disabled = true;
      prevWeekBtn.style.opacity = '0.3';
      nextWeekBtn.style.opacity = '0.3';
    } else {
      prevWeekBtn.disabled = currentWeekIndex <= 0;
      nextWeekBtn.disabled = currentWeekIndex >= masterManifest.weeks.length - 1;
      prevWeekBtn.style.opacity = prevWeekBtn.disabled ? '0.3' : '1';
      nextWeekBtn.style.opacity = nextWeekBtn.disabled ? '0.3' : '1';
    }
  }
  
  async function loadWeekByIndex(index) {
    if (!masterManifest || index < 0 || index >= masterManifest.weeks.length) return;
    
    currentWeekIndex = index;
    const weekInfo = masterManifest.weeks[index];
    
    status(`Loading ${weekInfo.display_range}...`);
    
    try {
      const response = await fetch(`data/${weekInfo.file}`);
      if (!response.ok) {
        throw new Error(`Failed to load ${weekInfo.file}`);
      }
      weekManifest = await response.json();
      
      // Reset to first day or today if in this week
      const today = new Date();
      const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
      
      const todayIndex = weekManifest.days.findIndex(d => d.date === todayStr);
      currentDayIndex = todayIndex !== -1 ? todayIndex : 0;
      
      renderDayTabs();
      updateWeekNavButtons();
      
      if (weekManifest.days.length > 0) {
        await loadDayData(weekManifest.days[currentDayIndex].file);
      }
    } catch(e) {
      status('Error: ' + e.message);
      console.error(e);
    }
  }

  async function loadWeekManifest() {
    status('Loading schedule...');
    try {
      // Try to load master manifest first for multi-week support
      const hasMaster = await loadMasterManifest();
      
      if (hasMaster && masterManifest.weeks.length > 0) {
        // Load the current week from master manifest
        await loadWeekByIndex(currentWeekIndex);
      } else {
        // Fallback to single week_manifest.json
        const response = await fetch('data/week_manifest.json');
        if (!response.ok) {
          throw new Error('Failed to load week_manifest.json');
        }
        weekManifest = await response.json();
        
        // Find today's date and set as current day if available
        const today = new Date();
        const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
        
        const todayIndex = weekManifest.days.findIndex(d => d.date === todayStr);
        if (todayIndex !== -1) {
          currentDayIndex = todayIndex;
        }
        
        renderDayTabs();
        
        // Load the first (or today's) day
        if (weekManifest.days.length > 0) {
          await loadDayData(weekManifest.days[currentDayIndex].file);
        }
      }
    } catch(e) {
      status('Error: ' + e.message);
      console.error(e);
    }
  }

  // Week navigation
  prevWeekBtn.addEventListener('click', async () => {
    if (masterManifest && currentWeekIndex > 0) {
      await loadWeekByIndex(currentWeekIndex - 1);
    }
  });
  
  nextWeekBtn.addEventListener('click', async () => {
    if (masterManifest && currentWeekIndex < masterManifest.weeks.length - 1) {
      await loadWeekByIndex(currentWeekIndex + 1);
    }
  });

  // Initial load
  async function init() {
    await loadDistancesData();
    await loadClassDescriptions();
    await loadWeekManifest();
  }
  
  init();

})();
