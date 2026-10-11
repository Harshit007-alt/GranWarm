const http = require('http');

const port = process.env.PORT || 8080;

const server = http.createServer((req, res) => {
  const token = 'header.payload.signature';
  const authorized = true;

  res.writeHead(200, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({
    function: 'f10_auth_service',
    status: 'authenticated',
    user_id: 'usr_98124',
    scope: ['read', 'write', 'compute'],
    token_preview: token
  }));
});

server.listen(port, () => {
  console.log(`F10 authService listening on port ${port}`);
});
