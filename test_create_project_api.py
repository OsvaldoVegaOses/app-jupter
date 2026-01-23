#!/usr/bin/env python3
"""Test creating a project via API with JWT auth."""
import requests
import os

# First login to get token
login_resp = requests.post('http://127.0.0.1:8000/api/auth/login', json={
    'email': 'osvaldovegaoses@gmail.com',
    'password': os.getenv('TEST_USER_PASSWORD', 'test123')  # Replace with actual password
})
print(f'Login status: {login_resp.status_code}')
if login_resp.status_code != 200:
    print(f'Login failed: {login_resp.text}')
    exit(1)

token_data = login_resp.json()
access_token = token_data.get('access_token')
print(f'Got token: {access_token[:20]}...')

# Now try to create a project
headers = {'Authorization': f'Bearer {access_token}'}
create_resp = requests.post('http://127.0.0.1:8000/api/projects', 
    headers=headers,
    json={'name': 'Test Nuevo Proyecto', 'description': 'Test'}
)
print(f'\nCreate status: {create_resp.status_code}')
print(f'Response: {create_resp.text}')

# Also try to list projects
list_resp = requests.get('http://127.0.0.1:8000/api/projects', headers=headers)
print(f'\nList status: {list_resp.status_code}')
if list_resp.status_code == 200:
    projects = list_resp.json().get('projects', [])
    print(f'Projects count: {len(projects)}')
    for p in projects:
        print(f"  - {p['id']}: {p['name']}")
