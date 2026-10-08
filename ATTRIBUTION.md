# Source provenance and attribution

The native address maps, constants, and patch-block metadata macro conventions used by this modification are adapted from **John Glassmyer's UltimaHacks**:

- Repository: https://github.com/JohnGlassmyer/UltimaHacks
- Reference commit: `0f449c77fa7166e5b594b7459a87fdd979df9efd`
- Relevant upstream material: `u7bg/include/u7bg.asm`, `u7bg/include/u7bg-segments.asm`, shared assembly patch macros/constants, and UltimaPatcher's MZ/FBOV format work.
- Upstream copyright and MIT permission notice: `LICENSE-UPSTREAM.txt`.

The tactical command code, panel, native wrappers, bounded Python patcher, and patch-only installer were developed for this modification. This package does not apply the upstream project's other interface or gameplay patches. The license notice is retained for the upstream software copied or adapted here; it is not a license grant for Ultima VII or its assets.

`source/include/weapon_types.inc` contains generated numeric shape/category constants used to validate native equipment, with the source data's hash in its comment. `source/native_patcher.py` contains short expected-instruction guards and native format information. These implementation facts and patch substitutions are distinct from distributing an original executable or an original game-data file.


The v1.2 research also consulted the primary Exult source for native Usecode opcode meanings, intrinsic signatures, spellbook layout and LINKDEP format. The parser, insertion code and dependency-table implementation in this package are independently written. No Exult runtime or copied Exult implementation is bundled. Reference: https://github.com/exult/exult (tools/ucformat.txt, tools/mklink.cc and usecode).
