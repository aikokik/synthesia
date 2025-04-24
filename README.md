# Synthesia take home assignment

A service that handles crypto signing requests with rate limiting and asynchronous processing using Redis queue. Also added in memory dict as cache (just for illustration, can be done with Redis or better way for prod env)

## Features
- **Expose a `/crypto/sign` endpoint with a similar input syntax to ours.**
  
Implemented by FastAPI 

- **Your endpoint must always return immediately (within ~2s), regardless of whether the call to our endpoint succeeded**
  
Implemented with timeout of 1.8 seconds to upstream and asynchronous request processing with Redis queue with a 202 status code if request either failed or rate limited or timed out. Webhook notifications will be sent for completed requests from queue. **Please note, if no webhook provided reuqest will not be enqued and error will be returned to client immediately. 
Also there is retry limit both for upstream (synthesia api) and webhook notification, if max_retry is reached, client will get error response. 

- **You must not hit our endpoint more than 10 times per minute, but you should expect that your endpoint will get bursts of 60 requests in a minute, and still be able to eventually handle all of those.**
  
 Simple sliding window rate limiter was implemented to handle the case. Sliding window was chosen cause from testing upstream API (synthesia api), seems upstream uses sliding window. 
 
- **You must package your service in such a way that the service can be started as a Docker container or a set of containers with Docker Compose. This will help our engineers when they evaluate your challenge. We *will not* evaluate challenge solutions that are not containerised. **
  
Docker containerised 
- **[Bonus] If your service shuts down and restarts, users who requested a signature before the shutdown should still be notified when their signature is ready without re-requesting one from scratch**
  
Queue hence implemneted using Redis (initially it was just in memory queue, but for persistance after service restart, I reimplemneted with redis)

## Prerequisites

- Docker and Docker Compose
- Python 3.8 or higher (for local development)
- Redis

## Configuration

Create a `.env` file in the root directory:

```env
SYNTHESIA_API_KEY=71d40369d2b1e30a41394eeaf9edff25
```
added api key here as service only accepts this api key (for simplicity and for illustrative purpose of authorisation)

## Installation & Running

1. Clone the repository:
```bash
git clone <repository-url>
cd synthesia
```

2. Build and start the services:
```bash
docker-compose up --build
```

This will start:
- API service on port 8000
- Redis on port 6379
- Queue processor

## API Usage

### Sign Message Endpoint

```bash
curl -X GET "http://localhost:8000/crypto/sign?message=testing&webhook_url=YOUR_WEBHOOK_URL" \
-H "Authorization: API_KEY"
```

Parameters:
- `message`: The message to sign (required)
- `webhook_url`: URL to receive the result (optional)

Headers:
- `Authorization`: API key for authentication
## TESTING 

There are simple bash cripts under tests folder which I have used for testing which includes my webhook and authorisation key. Feel free to run for testing. Leave it will all credentials in any case if u need to do functionality test. 
For service restart, I just restrated service in docker. For enqued requests, check logs and check webhook notifications. 
### Response Types

1. Immediate Response (without webhook):
```json
{
    "request_id": "...",
    "status": 200,
    "signature": "..."
}
```

2. Delayed Response (with webhook):
```json
{
    "request_id": "...",
    "status": 202,
    "message": "Your request is being processed asynchronously."
}
```

## Architecture

The service consists of several components:

1. **FastAPI Server**: Handles incoming HTTP requests
2. **Redis Queue**: Manages request queue and rate limiting
3. **Queue Processor**: Processes queued requests asynchronously
4. **Webhook Manager**: Sends results to specified webhook URLs

## Rate Limiting

The service implements rate limiting:
- Maximum 10 requests per minute to upstream 
- Requests exceeding the limit are queued if a webhook URL is provided
- Without a webhook URL, requests exceeding the limit receive a 429 response

## Development

### Local Setup

1. Create a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  
```

2. Install dependencies:
```
make install
```

### Running Tests

```bash
# Simple test request
./tests/test.sh

# Rate limit test (60 requests)
./tests/test_rate_limit.sh
```

## Monitoring

View logs:
```bash
docker-compose logs -f api  # API service logs
docker-compose logs -f redis  # Redis logs
```

Check Redis queue:
```bash
docker-compose exec redis redis-cli
```

## Troubleshooting

1. If the service isn't responding:
```bash
docker-compose down
docker-compose up --build
```

2. To clear Redis queue:
```bash
docker-compose exec redis redis-cli FLUSHALL
```
