// Vercel Serverless Function — BlazeMeter API Proxy
// Equivalent of netlify/functions/blazemeter.js but for Vercel
// Deployed at /api/blazemeter on your site

export default async function handler(req, res) {

  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, x-bzm-key-id, x-bzm-key-secret');

  // Handle preflight
  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  try {
    // Get API credentials from request headers
    const keyId     = req.headers['x-bzm-key-id'];
    const keySecret = req.headers['x-bzm-key-secret'];

    if (!keyId || !keySecret) {
      return res.status(401).json({ error: 'Missing BlazeMeter API credentials' });
    }

    // Get the BlazeMeter API path from query string
    const path   = req.query.path || '/api/v4/user';
    const method = req.method === 'GET' ? 'GET' : 'POST';
    const bzmUrl = 'https://a.blazemeter.com' + path;

    // Base64 auth
    const authString = Buffer.from(keyId + ':' + keySecret).toString('base64');

    const fetchOptions = {
      method,
      headers: {
        'Authorization': 'Basic ' + authString,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      }
    };

    if (method === 'POST' && req.body) {
      fetchOptions.body = typeof req.body === 'string'
        ? req.body
        : JSON.stringify(req.body);
    }

    const response = await fetch(bzmUrl, fetchOptions);
    const data     = await response.json();

    return res.status(response.status).json(data);

  } catch (err) {
    console.error('BlazeMeter proxy error:', err);
    return res.status(500).json({
      error: 'Proxy error: ' + err.message
    });
  }
}
