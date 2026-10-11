const http = require('http');

const port = process.env.PORT || 8080;

const server = http.createServer((req, res) => {
  res.writeHead(200, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({
    function: 'f01_hello_world',
    message: 'Hello from F1!',
    timestamp: new Date().toISOString()
  }));
});

server.listen(port, () => {
  console.log(`F1 listening on port ${port}`);
});
