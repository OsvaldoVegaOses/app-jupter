#!/usr/bin/env python3
import json
import argparse
import sys

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True, help='ContainerApp full JSON exported with az containerapp show')
    p.add_argument('--vite_api_base', required=True)
    p.add_argument('--vite_neo4j', required=True)
    p.add_argument('--output', default='scripts/patch.json')
    args = p.parse_args()

    with open(args.input, 'r', encoding='utf-8') as f:
        data = json.load(f)

    containers = data.get('properties', {}).get('template', {}).get('containers', [])
    if not containers:
        print('No containers found in input JSON', file=sys.stderr)
        sys.exit(2)

    for c in containers:
        env = c.get('env', [])
        # Remove malformed entry created by earlier CLI misuse
        env = [e for e in env if e.get('name') != 'properties.configuration.environmentVariables']

        def upsert(name, val):
            for e in env:
                if e.get('name') == name:
                    e['value'] = val
                    return
            env.append({'name': name, 'value': val})

        upsert('VITE_API_BASE', args.vite_api_base)
        upsert('VITE_NEO4J_API_URL', args.vite_neo4j)

        c['env'] = env

    patch = {'properties': {'template': {'containers': containers}}}

    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(patch, f, indent=2, ensure_ascii=False)

    print('Wrote patch to', args.output)

if __name__ == '__main__':
    main()
#!/usr/bin/env python3
import json
import sys
import argparse

def load(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save(obj, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)

def sanitize_containers(containers, vite_base, vite_neo4j_url):
    for c in containers:
        env = c.get('env') or []
        # remove accidental entry
        env = [e for e in env if e.get('name') != 'properties.configuration.environmentVariables']

        # helper to check exists
        names = {e.get('name') for e in env}
        if 'VITE_API_BASE' not in names:
            env.append({'name': 'VITE_API_BASE', 'value': vite_base})
        if 'VITE_NEO4J_API_URL' not in names:
            env.append({'name': 'VITE_NEO4J_API_URL', 'value': vite_neo4j_url})

        c['env'] = env
    return containers

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--vite-base', required=True)
    p.add_argument('--vite-neo4j-url', required=True)
    args = p.parse_args()

    containers = load(args.input)
    containers = sanitize_containers(containers, args.vite_base, args.vite_neo4j_url)

    patch = {
        'properties': {
            'template': {
                'containers': containers
            }
        }
    }
    save(patch, args.output)
    print('Wrote patch to', args.output)

if __name__ == '__main__':
    main()
