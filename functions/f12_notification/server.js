const http = require('http');

const port = process.env.PORT || 8080;

const server = http.createServer((req, res) => {
  res.writeHead(200, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({
    function: 'f12_notification',
    status: 'delivered',
    channel: 'push_notification',
    timestamp: new Date().toISOString()
  }));
});

server.listen(port, () => {
  console.log(`F12 notification listening on port ${port}`);
});
