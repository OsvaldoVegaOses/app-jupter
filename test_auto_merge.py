#!/usr/bin/env python
"""Test the auto-merge endpoint."""

import requests
import json

url = 'http://127.0.0.1:8000/api/codes/candidates/auto-merge'
headers = {'Content-Type': 'application/json', 'X-API-Key': 'test-key'}
data = {'project': 'default', 'pairs': [{'source_codigo': 'test', 'target_codigo': 'test2'}]}

print(f"Testing: {url}")
print(f"Data: {json.dumps(data, indent=2)}")

try:
    r = requests.post(url, json=data, headers=headers)
    print(f'Status: {r.status_code}')
    print(f'Response: {r.text[:500] if len(r.text) > 500 else r.text}')
except Exception as e:
    print(f'Error: {e}')
