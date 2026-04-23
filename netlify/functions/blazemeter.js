// Netlify Serverless Function — BlazeMeter API Proxy
// Runs on Netlify's servers so there are NO browser CORS restrictions
// Called by perftest.html as /.netlify/functions/blazemeter

exports.handler = async function(event, context) {

  // Allow all origins (your own site calls this)
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type, x-bzm-key-id, x-bzm-key-secret',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Content-Type': 'application/json'
  };

  // Handle preflight OPTIONS request
  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 200, headers, body: '' };
  }

  try {
    // Get API credentials from request headers (never stored)
    const keyId     = event.headers['x-bzm-key-id']     || event.headers['X-Bzm-Key-Id'];
    const keySecret = event.headers['x-bzm-key-secret'] || event.headers['X-Bzm-Key-Secret'];

    if (!keyId || !keySecret) {
      return {
        statusCode: 401,
        headers,
        body: JSON.stringify({ error: 'Missing BlazeMeter API credentials' })
      };
    }

    // Get the BlazeMeter API path from query string e.g. ?path=/api/v4/tests
    const path   = event.queryStringParameters?.path || '/api/v4/user';
    const method = event.httpMethod === 'GET' ? 'GET' : 'POST';
    const bzmUrl = 'https://a.blazemeter.com' + path;

    // Build the auth header using Base64 encoding
    const authString = Buffer.from(keyId + ':' + keySecret).toString('base64');

    // Make the real API call from the server — no CORS issues here
    const fetchOptions = {
      method: method,
      headers: {
        'Authorization': 'Basic ' + authString,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      }
    };

    // Forward the request body for POST calls
    if (method === 'POST' && event.body) {
      fetchOptions.body = event.body;
    }

    const response = await fetch(bzmUrl, fetchOptions);
    const data     = await response.json();

    return {
      statusCode: response.status,
      headers,
      body: JSON.stringify(data)
    };

  } catch (err) {
    console.error('BlazeMeter proxy error:', err);
    return {
      statusCode: 500,
      headers,
      body: JSON.stringify({
        error: 'Proxy error: ' + err.message,
        details: 'The Netlify function failed to reach BlazeMeter API'
      })
    };
  }
};
