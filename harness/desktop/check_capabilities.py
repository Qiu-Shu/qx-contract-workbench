"""Four-business regression entry. Start desktop/check_business_host.cjs first."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).with_name('check_business_ui.py')),run_name='__main__')
