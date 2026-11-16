import pefile, sys

new = pefile.PE(r'c:\Users\Scrooge\Documents\GitHub\TheArtifact\Brigador Killers\proxy_sdl2\out\SDL2.dll')
print(f'=== NEW out\\SDL2.dll ({len(new.DIRECTORY_ENTRY_EXPORT.symbols)} exports) ===')
for e in new.DIRECTORY_ENTRY_EXPORT.symbols:
    name = e.name.decode() if e.name else '(noname)'
    print(f'  @{e.ordinal}: {name}')
