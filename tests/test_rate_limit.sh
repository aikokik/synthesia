#!/bin/bash

send_request() {
    local id=$1
    curl -s -X GET "http://localhost:8000/crypto/sign?message=test_message_$id&webhook_url=https://webhook.site/fa4441ca-ca81-4d01-aaf0-38c37193818d" \
    -H "Authorization: 71d40369d2b1e30a41394eeaf9edff25"
}

start_time=$(date +%s)

# Send 60 requests
for i in {1..60}; do
    send_request $i
    
    sleep 0.1
done

wait

end_time=$(date +%s)
elapsed=$((end_time - start_time))

echo "Sent 60 requests in $elapsed seconds"