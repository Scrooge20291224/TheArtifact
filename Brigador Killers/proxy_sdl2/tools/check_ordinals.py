import pefile

orig_path = r'C:\Program Files (x86)\Steam\steamapps\common\Brigador Killers\SDL2_orig.dll'
proxy_path = r'C:\Program Files (x86)\Steam\steamapps\common\Brigador Killers\SDL2.dll'

orig = pefile.PE(orig_path)
proxy = pefile.PE(proxy_path)

print('=== SDL2_orig.dll ===')
print(f'  exports: {len(orig.DIRECTORY_ENTRY_EXPORT.symbols)}')
print()

print('=== proxy SDL2.dll ===')
print(f'  exports: {len(proxy.DIRECTORY_ENTRY_EXPORT.symbols)}')
print()

orig_exp = {e.ordinal: e.name.decode() if e.name else f'noname_{e.ordinal}' for e in orig.DIRECTORY_ENTRY_EXPORT.symbols}
proxy_exp = {e.ordinal: e.name.decode() if e.name else f'noname_{e.ordinal}' for e in proxy.DIRECTORY_ENTRY_EXPORT.symbols}

missing = set(orig_exp.keys()) - set(proxy_exp.keys())
extra = set(proxy_exp.keys()) - set(orig_exp.keys())

if missing:
    print(f'MISSING in proxy: {len(missing)} ordinals')
    for ord in sorted(missing):
        print(f'  @{ord}: {orig_exp[ord]}')
else:
    print('OK: proxy covers all original ordinals')

if extra:
    print(f'Extra in proxy (our hooks): {len(extra)}')
    for ord in sorted(extra):
        print(f'  @{ord}: {proxy_exp[ord]}')

print()
print('=== Key functions ordinal check ===')
for name in ['SDL_Init', 'SDL_PollEvent', 'SDL_Quit', 'SDL_CreateWindow', 'SDL_DestroyWindow']:
    o = next((e for e in orig.DIRECTORY_ENTRY_EXPORT.symbols if e.name and e.name.decode() == name), None)
    p = next((e for e in proxy.DIRECTORY_ENTRY_EXPORT.symbols if e.name and e.name.decode() == name), None)
    print(f'  {name}: orig=@{o.ordinal if o else "?"} proxy=@{p.ordinal if p else "MISSING"}')
