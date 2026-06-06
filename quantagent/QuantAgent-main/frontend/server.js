const { createServer } = require('http');
const { parse } = require('url');
const next = require('next');
const http = require('http');
const https = require('https');

const dev = false;
const app = next({ dev });
const handle = app.getRequestHandler();

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || 'http://backend:8000';
const BACKEND = new URL(BACKEND_URL);

app.prepare().then(() => {
  createServer((req, res) => {
    const parsedUrl = parse(req.url, true);

    // Proxy /api/ requests to backend with 10-minute timeout
    if (parsedUrl.pathname.startsWith('/api/')) {
      const options = {
        hostname: BACKEND.hostname,
        port: BACKEND.port,
        path: req.url,
        method: req.method,
        headers: { ...req.headers, host: BACKEND.host },
        timeout: 600000, // 10 minutes
      };

      const proxy = http.request(options, (proxyRes) => {
        res.writeHead(proxyRes.statusCode, proxyRes.headers);
        proxyRes.pipe(res);
      });

      proxy.on('timeout', () => { proxy.destroy(); res.writeHead(504); res.end('Gateway Timeout'); });
      proxy.on('error', (e) => { res.writeHead(502); res.end('Proxy Error: ' + e.message); });
      req.pipe(proxy);
      return;
    }

    handle(req, res, parsedUrl);
  }).listen(3000, (err) => {
    if (err) throw err;
    console.log('> Ready on http://localhost:3000');
  });
});
