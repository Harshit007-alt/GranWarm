const http = require('http');

const port = process.env.PORT || 8080;

const server = http.createServer((req, res) => {
  const dummyData = Array.from({ length: 100 }, (_, i) => ({
    id: i,
    val: Math.random() * 100,
    tags: ['faas', 'serverless', 'knative']
  }));

  const transformed = dummyData
    .filter(x => x.val > 50)
    .map(x => ({ ...x, normalized: x.val / 100 }));

  res.writeHead(200, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({
    function: 'f02_json_transform',
    count: transformed.length,
    sample: transformed.slice(0, 3)
  }));
});

server.listen(port, () => {
  console.log(`F2 listening on port ${port}`);
});
