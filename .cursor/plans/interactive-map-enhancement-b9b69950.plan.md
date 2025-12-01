<!-- b9b69950-9d62-4ddc-8ca1-0802b88a4e6f 07d60289-84f9-4963-bcce-b6f82ed81725 -->
# Density Dual Visualization Plan

## Overview

Retain the heatmap layer but add an additional proportional-circle overlay so users can inspect customer density numerically. Provide clear toggles and matching legend entries for both visualizations.

## Steps

### 1. Backend API (Optional)

- No server changes required; reuse existing customer data payload. If necessary, include aggregated totals per location (lat/lon already unique) so the frontend can size circles accurately.

### 2. Frontend – Data Processing (`templates/interactive_map.html`)

- Continue aggregating customer weights by lat/lon as we already do for the heatmap.
- Reuse that aggregated dataset to create proportional circle markers:
- Define circle radii based on the fixed weight buckets (<1k … >5k).
- Store bucket metadata so both the heatmap and circles share identical ranges/colors.

### 3. Frontend – Layer & Legend Updates

- Add a new Leaflet layer group, e.g., `customerCirclesLayer`, and include it in the layer control (“Customer Density – Circles”).
- When a search runs:
- Populate the heatmap layer as today (using fixed gradients).
- Create circle markers (non-clustered) with hover tooltips showing exact counts/bucket labels.
- Update the legend to mention both layers (e.g., the color scale applies to both heatmap and circle fill/stroke), or add a short note clarifying the relationship.

### 4. UX Improvements

- Ensure both “Customer Density (Heatmap)” and “Customer Density (Circles)” are enabled by default after each search so users immediately see both views (they can toggle either off).
- Consider adding a quick hint beneath the status text noting that the circles show actual counts per cell.

### 5. Verification

- Run sample searches (state and area/postcode) to confirm:
- Heatmap displays with fixed color bands.
- Circles appear on top, sized/colored per bucket and clickable for exact counts.
- Layer toggles work independently without performance issues.

### To-dos

- [ ] Remove static map endpoint from main.py, delete static_map.html, remove links from base.html
- [ ] Add Leaflet.heat CDN to interactive_map.html and create heatmap layer infrastructure
- [ ] Add search type selector UI and update search API to handle state/area/postcode flows
- [ ] Add functions to extract admin boundaries from geocoding API and predefined state bounds
- [ ] Implement layer control with toggles for customer density, service outlets, body & paint, traffic stations
- [ ] Update search results to display only searched area bounds and integrate heatmap data
- [ ] Remove static map endpoint from main.py, delete static_map.html, remove links from base.html
- [ ] Add Leaflet.heat CDN to interactive_map.html and create heatmap layer infrastructure
- [ ] Add search type selector UI and update search API to handle state/area/postcode flows
- [ ] Add functions to extract admin boundaries from geocoding API and predefined state bounds
- [ ] Implement layer control with toggles for customer density, service outlets, body & paint, traffic stations
- [ ] Update search results to display only searched area bounds and integrate heatmap data
- [ ] Remove static map endpoint from main.py, delete static_map.html, remove links from base.html
- [ ] Add Leaflet.heat CDN to interactive_map.html and create heatmap layer infrastructure
- [ ] Add search type selector UI and update search API to handle state/area/postcode flows
- [ ] Add functions to extract admin boundaries from geocoding API and predefined state bounds
- [ ] Implement layer control with toggles for customer density, service outlets, body & paint, traffic stations
- [ ] Update search results to display only searched area bounds and integrate heatmap data
- [ ] Remove static map endpoint from main.py, delete static_map.html, remove links from base.html
- [ ] Add Leaflet.heat CDN to interactive_map.html and create heatmap layer infrastructure
- [ ] Add search type selector UI and update search API to handle state/area/postcode flows
- [ ] Add functions to extract admin boundaries from geocoding API and predefined state bounds
- [ ] Implement layer control with toggles for customer density, service outlets, body & paint, traffic stations
- [ ] Update search results to display only searched area bounds and integrate heatmap data
- [ ] Remove static map endpoint from main.py, delete static_map.html, remove links from base.html
- [ ] Add Leaflet.heat CDN to interactive_map.html and create heatmap layer infrastructure
- [ ] Add search type selector UI and update search API to handle state/area/postcode flows
- [ ] Add functions to extract admin boundaries from geocoding API and predefined state bounds
- [ ] Implement layer control with toggles for customer density, service outlets, body & paint, traffic stations
- [ ] Update search results to display only searched area bounds and integrate heatmap data
- [ ] Remove static map endpoint from main.py, delete static_map.html, remove links from base.html
- [ ] Add Leaflet.heat CDN to interactive_map.html and create heatmap layer infrastructure
- [ ] Add search type selector UI and update search API to handle state/area/postcode flows
- [ ] Add functions to extract admin boundaries from geocoding API and predefined state bounds
- [ ] Implement layer control with toggles for customer density, service outlets, body & paint, traffic stations
- [ ] Update search results to display only searched area bounds and integrate heatmap data
- [ ] Implement validation and multi-term parsing in main.py
- [ ] Frontend: update UI hints, draw multiple boundaries with distinct colors, show validation errors
- [ ] Remove static map endpoint from main.py, delete static_map.html, remove links from base.html
- [ ] Add Leaflet.heat CDN to interactive_map.html and create heatmap layer infrastructure
- [ ] Add search type selector UI and update search API to handle state/area/postcode flows
- [ ] Add functions to extract admin boundaries from geocoding API and predefined state bounds
- [ ] Implement layer control with toggles for customer density, service outlets, body & paint, traffic stations
- [ ] Update search results to display only searched area bounds and integrate heatmap data
- [ ] Remove static map endpoint from main.py, delete static_map.html, remove links from base.html
- [ ] Add Leaflet.heat CDN to interactive_map.html and create heatmap layer infrastructure
- [ ] Add search type selector UI and update search API to handle state/area/postcode flows
- [ ] Add functions to extract admin boundaries from geocoding API and predefined state bounds
- [ ] Implement layer control with toggles for customer density, service outlets, body & paint, traffic stations
- [ ] Update search results to display only searched area bounds and integrate heatmap data
- [ ] Remove static map endpoint from main.py, delete static_map.html, remove links from base.html
- [ ] Add Leaflet.heat CDN to interactive_map.html and create heatmap layer infrastructure
- [ ] Add search type selector UI and update search API to handle state/area/postcode flows
- [ ] Add functions to extract admin boundaries from geocoding API and predefined state bounds
- [ ] Implement layer control with toggles for customer density, service outlets, body & paint, traffic stations
- [ ] Update search results to display only searched area bounds and integrate heatmap data
- [ ] Implement validation and multi-term parsing in main.py
- [ ] Frontend: update UI hints, draw multiple boundaries with distinct colors, show validation errors
- [ ] Remove static map endpoint from main.py, delete static_map.html, remove links from base.html
- [ ] Add Leaflet.heat CDN to interactive_map.html and create heatmap layer infrastructure
- [ ] Add search type selector UI and update search API to handle state/area/postcode flows
- [ ] Add functions to extract admin boundaries from geocoding API and predefined state bounds
- [ ] Implement layer control with toggles for customer density, service outlets, body & paint, traffic stations
- [ ] Update search results to display only searched area bounds and integrate heatmap data
- [ ] Remove static map endpoint from main.py, delete static_map.html, remove links from base.html
- [ ] Add Leaflet.heat CDN to interactive_map.html and create heatmap layer infrastructure
- [ ] Add search type selector UI and update search API to handle state/area/postcode flows
- [ ] Add functions to extract admin boundaries from geocoding API and predefined state bounds
- [ ] Implement layer control with toggles for customer density, service outlets, body & paint, traffic stations
- [ ] Update search results to display only searched area bounds and integrate heatmap data
- [ ] Remove static map endpoint from main.py, delete static_map.html, remove links from base.html
- [ ] Add Leaflet.heat CDN to interactive_map.html and create heatmap layer infrastructure
- [ ] Add search type selector UI and update search API to handle state/area/postcode flows
- [ ] Add functions to extract admin boundaries from geocoding API and predefined state bounds
- [ ] Implement layer control with toggles for customer density, service outlets, body & paint, traffic stations
- [ ] Update search results to display only searched area bounds and integrate heatmap data
- [ ] Remove static map endpoint from main.py, delete static_map.html, remove links from base.html
- [ ] Add Leaflet.heat CDN to interactive_map.html and create heatmap layer infrastructure
- [ ] Add search type selector UI and update search API to handle state/area/postcode flows
- [ ] Add functions to extract admin boundaries from geocoding API and predefined state bounds
- [ ] Implement layer control with toggles for customer density, service outlets, body & paint, traffic stations
- [ ] Update search results to display only searched area bounds and integrate heatmap data
- [ ] Remove static map endpoint from main.py, delete static_map.html, remove links from base.html
- [ ] Add Leaflet.heat CDN to interactive_map.html and create heatmap layer infrastructure
- [ ] Add search type selector UI and update search API to handle state/area/postcode flows
- [ ] Add functions to extract admin boundaries from geocoding API and predefined state bounds
- [ ] Implement layer control with toggles for customer density, service outlets, body & paint, traffic stations
- [ ] Update search results to display only searched area bounds and integrate heatmap data
- [ ] Remove static map endpoint from main.py, delete static_map.html, remove links from base.html
- [ ] Add Leaflet.heat CDN to interactive_map.html and create heatmap layer infrastructure
- [ ] Add search type selector UI and update search API to handle state/area/postcode flows
- [ ] Add functions to extract admin boundaries from geocoding API and predefined state bounds
- [ ] Implement layer control with toggles for customer density, service outlets, body & paint, traffic stations
- [ ] Update search results to display only searched area bounds and integrate heatmap data
- [ ] Implement validation and multi-term parsing in main.py
- [ ] Frontend: update UI hints, draw multiple boundaries with distinct colors, show validation errors
- [ ] Remove static map endpoint from main.py, delete static_map.html, remove links from base.html
- [ ] Add Leaflet.heat CDN to interactive_map.html and create heatmap layer infrastructure
- [ ] Add search type selector UI and update search API to handle state/area/postcode flows
- [ ] Add functions to extract admin boundaries from geocoding API and predefined state bounds
- [ ] Implement layer control with toggles for customer density, service outlets, body & paint, traffic stations
- [ ] Update search results to display only searched area bounds and integrate heatmap data
- [ ] Remove static map endpoint from main.py, delete static_map.html, remove links from base.html
- [ ] Add Leaflet.heat CDN to interactive_map.html and create heatmap layer infrastructure
- [ ] Add search type selector UI and update search API to handle state/area/postcode flows
- [ ] Add functions to extract admin boundaries from geocoding API and predefined state bounds
- [ ] Implement layer control with toggles for customer density, service outlets, body & paint, traffic stations
- [ ] Update search results to display only searched area bounds and integrate heatmap data
- [ ] Remove static map endpoint from main.py, delete static_map.html, remove links from base.html
- [ ] Add Leaflet.heat CDN to interactive_map.html and create heatmap layer infrastructure
- [ ] Add search type selector UI and update search API to handle state/area/postcode flows
- [ ] Add functions to extract admin boundaries from geocoding API and predefined state bounds
- [ ] Implement layer control with toggles for customer density, service outlets, body & paint, traffic stations
- [ ] Update search results to display only searched area bounds and integrate heatmap data