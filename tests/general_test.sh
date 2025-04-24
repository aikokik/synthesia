#!/bin/bash

curl -X GET "http://localhost:8000/crypto/sign?message=testing&webhook_url=https://webhook.site/fa4441ca-ca81-4d01-aaf0-38c37193818d" \
-H "Authorization: 71d40369d2b1e30a41394eeaf9edff25"
