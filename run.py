"""No installation required: python run.py --help."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))
from dynamic_retrieval.cli import main
if __name__=='__main__':raise SystemExit(main())
