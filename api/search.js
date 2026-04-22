// Vercel serverless function — proxies Google Places API
// Keeps API keys off the client.
//
// GET /api/search?zip=10001&category=food+pantry
//
// Returns: { results: [ { name, address, phone } ] }

const GOOGLE_API_KEY = process.env.GOOGLE_MAPS_API_KEY;
const GEOCODE_URL    = 'https://maps.googleapis.com/maps/api/geocode/json';
const PLACES_URL     = 'https://maps.googleapis.com/maps/api/place/textsearch/json';
const DETAILS_URL    = 'https://maps.googleapis.com/maps/api/place/details/json';

const SEARCH_RADIUS_METERS = 8000; // ~5 miles

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const { zip, category } = req.query;

  if (!zip || !/^\d{5}$/.test(zip)) {
    return res.status(400).json({ error: 'Invalid zip code' });
  }
  if (!category || !category.trim()) {
    return res.status(400).json({ error: 'Category is required' });
  }
  if (!GOOGLE_API_KEY) {
    return res.status(500).json({ error: 'Server configuration error' });
  }

  try {
    // Step 1: Geocode the zip code → lat/lng
    const geoRes  = await fetch(`${GEOCODE_URL}?address=${zip}&key=${GOOGLE_API_KEY}`);
    const geoData = await geoRes.json();

    if (geoData.status !== 'OK' || !geoData.results.length) {
      return res.status(400).json({ error: 'Could not find that zip code' });
    }

    const { lat, lng } = geoData.results[0].geometry.location;

    // Step 2: Text search for places matching the category near that location
    const searchQuery  = encodeURIComponent(category);
    const location     = `${lat},${lng}`;
    const placesRes    = await fetch(
      `${PLACES_URL}?query=${searchQuery}&location=${location}&radius=${SEARCH_RADIUS_METERS}&key=${GOOGLE_API_KEY}`
    );
    const placesData   = await placesRes.json();

    if (placesData.status === 'ZERO_RESULTS') {
      return res.status(200).json({ results: [] });
    }
    if (placesData.status !== 'OK') {
      return res.status(502).json({ error: 'Places search failed' });
    }

    // Step 3: Fetch phone numbers for top results (Places Details API)
    const topPlaces = placesData.results.slice(0, 8);

    const detailsPromises = topPlaces.map(place =>
      fetch(`${DETAILS_URL}?place_id=${place.place_id}&fields=name,formatted_address,formatted_phone_number&key=${GOOGLE_API_KEY}`)
        .then(r => r.json())
        .catch(() => null)
    );

    const detailsResults = await Promise.all(detailsPromises);

    const results = detailsResults
      .filter(d => d && d.status === 'OK')
      .map(d => ({
        name:    d.result.name,
        address: d.result.formatted_address,
        phone:   d.result.formatted_phone_number || null,
      }));

    return res.status(200).json({ results });

  } catch (err) {
    console.error('Search error:', err);
    return res.status(500).json({ error: 'Unexpected server error' });
  }
}
