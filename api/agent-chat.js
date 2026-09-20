// api/agent-chat.js
//
// Serverless function that lets a browser talk to an Argovaa agent without ever
// seeing your Anthropic key. The key stays in Vercel's environment variables.
//
//   POST /api/agent-chat
//   { "agent": "hair-restoration-patient-assistant",
//     "messages": [ { "role": "user", "content": "How long is recovery?" } ] }
//
//   -> 200 { "reply": "...", "model": "claude-sonnet-5" }
//
// Required env var:  ANTHROPIC_API_KEY
// Optional env vars: ANTHROPIC_MODEL, MAX_TOKENS, ALLOWED_ORIGINS

import { getAgent } from './_agents.js';

const ANTHROPIC_URL = 'https://api.anthropic.com/v1/messages';
const ANTHROPIC_VERSION = '2023-06-01';

const DEFAULT_MODEL = 'claude-sonnet-5';
const DEFAULT_MAX_TOKENS = 1024;

// Sites allowed to call this function. Extra origins can be added in Vercel via
// ALLOWED_ORIGINS as a comma-separated list, without editing this file.
const BASE_ORIGINS = [
  'https://argovaa.com',
  'https://www.argovaa.com',
  'https://californiahairsurgeon.com',
  'https://www.californiahairsurgeon.com',
];

// Input caps. These exist to stop a single request running up a large bill.
const MAX_MESSAGES = 30;
const MAX_CHARS_PER_MESSAGE = 4000;
const MAX_TOTAL_CHARS = 20000;

function allowedOrigins() {
  const extra = (process.env.ALLOWED_ORIGINS || '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
  return [...BASE_ORIGINS, ...extra];
}

function isAllowed(origin) {
  if (!origin) return false;
  if (allowedOrigins().includes(origin)) return true;
  // Your own Vercel deployments, including preview URLs.
  try {
    const host = new URL(origin).hostname;
    return host.endsWith('.vercel.app');
  } catch {
    return false;
  }
}

function applyCors(req, res) {
  const origin = req.headers.origin;
  if (isAllowed(origin)) {
    res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Vary', 'Origin');
  }
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.setHeader('Access-Control-Max-Age', '86400');
}

function parseBody(req) {
  // Vercel usually parses JSON bodies for you, but not always (raw body,
  // odd content-type). Handle both.
  if (req.body && typeof req.body === 'object') return req.body;
  if (typeof req.body === 'string' && req.body.length) {
    try {
      return JSON.parse(req.body);
    } catch {
      return null;
    }
  }
  return null;
}

function validateMessages(messages) {
  if (!Array.isArray(messages) || messages.length === 0) {
    return { error: 'messages must be a non-empty array' };
  }
  if (messages.length > MAX_MESSAGES) {
    return { error: `messages cannot exceed ${MAX_MESSAGES} turns` };
  }

  let total = 0;
  const cleaned = [];

  for (const m of messages) {
    if (!m || typeof m !== 'object') {
      return { error: 'each message must be an object' };
    }
    if (m.role !== 'user' && m.role !== 'assistant') {
      return { error: 'message role must be "user" or "assistant"' };
    }
    if (typeof m.content !== 'string' || !m.content.trim()) {
      return { error: 'message content must be a non-empty string' };
    }
    const content = m.content.slice(0, MAX_CHARS_PER_MESSAGE);
    total += content.length;
    if (total > MAX_TOTAL_CHARS) {
      return { error: 'conversation is too long' };
    }
    cleaned.push({ role: m.role, content });
  }

  if (cleaned[cleaned.length - 1].role !== 'user') {
    return { error: 'the last message must be from the user' };
  }

  return { messages: cleaned };
}

export default async function handler(req, res) {
  applyCors(req, res);

  if (req.method === 'OPTIONS') {
    return res.status(204).end();
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed. Use POST.' });
  }

  const origin = req.headers.origin;
  // Requests with no Origin header (curl, server-to-server) are allowed through;
  // browsers always send one, so this only blocks cross-site browser calls.
  if (origin && !isAllowed(origin)) {
    return res.status(403).json({ error: 'Origin not allowed' });
  }

  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    // Deliberately vague to the caller; the detail goes to your Vercel logs.
    console.error('ANTHROPIC_API_KEY is not set on this deployment');
    return res.status(500).json({ error: 'Server is not configured' });
  }

  const body = parseBody(req);
  if (!body) {
    return res.status(400).json({ error: 'Body must be JSON' });
  }

  const agent = getAgent(body.agent);
  if (!agent) {
    return res.status(400).json({ error: 'Unknown agent' });
  }

  const check = validateMessages(body.messages);
  if (check.error) {
    return res.status(400).json({ error: check.error });
  }

  const model = process.env.ANTHROPIC_MODEL || DEFAULT_MODEL;
  const maxTokens = Number(process.env.MAX_TOKENS) || DEFAULT_MAX_TOKENS;

  try {
    const upstream = await fetch(ANTHROPIC_URL, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': ANTHROPIC_VERSION,
      },
      body: JSON.stringify({
        model,
        max_tokens: maxTokens,
        system: agent.systemPrompt,
        messages: check.messages,
      }),
    });

    if (!upstream.ok) {
      const detail = await upstream.text();
      // Log status and Anthropic's message for debugging. Patient text is not logged.
      console.error('Anthropic API error', upstream.status, detail.slice(0, 500));
      const status = upstream.status === 429 ? 429 : 502;
      return res.status(status).json({
        error:
          status === 429
            ? 'The assistant is busy right now. Please try again in a moment.'
            : 'The assistant is unavailable right now.',
      });
    }

    const data = await upstream.json();
    const reply = (data.content || [])
      .filter((block) => block.type === 'text')
      .map((block) => block.text)
      .join('\n')
      .trim();

    if (!reply) {
      return res.status(502).json({ error: 'Empty response from the assistant' });
    }

    res.setHeader('Cache-Control', 'no-store');
    return res.status(200).json({ reply, model, agent: agent.name });
  } catch (err) {
    console.error('agent-chat failed:', err && err.message);
    return res.status(500).json({ error: 'Something went wrong' });
  }
}
