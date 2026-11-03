# Bundled FFmpeg provenance

The imageio-ffmpeg wheel's Windows executable reports FFmpeg 7.1 with GPL and version3 enabled. Its actual `-L` and `-buildconf` output is collected during each build.

COPYING.GPLv3 is copied verbatim from the FFmpeg n7.1 source tree:
https://raw.githubusercontent.com/FFmpeg/FFmpeg/n7.1/COPYING.GPLv3
SHA-256: 8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903

Upstream source: https://github.com/FFmpeg/FFmpeg/tree/n7.1
Binary vendor/build reference: https://www.gyan.dev/ffmpeg/builds/

The separately bundled Qt multimedia backend reports another FFmpeg version and retains its own LGPL notices. This file does not certify that all corresponding-source and redistribution obligations are closed. Formal release remains blocked on the complete rights and component review recorded in RELEASE_GATE.
