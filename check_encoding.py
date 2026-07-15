import os

base = r'C:\Users\Repair SC\Desktop\bazspark\BAZspark\backend\routers'
for f in ['sync.py', 'exports.py', 'environment.py']:
    path = os.path.join(base, f)
    with open(path, 'rb') as fp:
        first_bytes = fp.read(100)
        print(f'{f}: raw first bytes: {first_bytes[:40]}')
        if first_bytes[:3] == b'\xef\xbb\xbf':
            print('  -> Has UTF-8 BOM!')
        print(f'  -> repr text: {repr(first_bytes.decode("utf-8", errors="replace")[:80])}')
