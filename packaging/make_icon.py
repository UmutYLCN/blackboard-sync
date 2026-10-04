"""Write the Windows app icon (the tray's idle icon) as a multi-size .ico."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from blackboard_sync.menubar.model import Icon  # noqa: E402
from blackboard_sync.windows.presentation import icon_image  # noqa: E402

out = Path(sys.argv[1])
out.parent.mkdir(parents=True, exist_ok=True)
icon_image(Icon.IDLE).resize((256, 256)).save(
    out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
)
