"""Start the local research workbench; no API key or network call required."""
import argparse
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'src'))
temp=ROOT/'.runtime/tmp'; temp.mkdir(parents=True,exist_ok=True)
os.environ['TEMP']=str(temp); os.environ['TMP']=str(temp)


def main():
    parser=argparse.ArgumentParser(description='Local event forecasting research workbench')
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    if not 1024<=args.port<=65535: parser.error('Port must be between 1024 and 65535')
    from dynamic_retrieval.web_server import create_server
    server=create_server(ROOT,args.port)
    print(f'Local workbench: http://127.0.0.1:{server.server_port}',flush=True)
    print('Frozen replay is offline. New-event extraction uses configured model credentials. Ctrl+C to stop.',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.jobs.close(); server.server_close()


if __name__=='__main__': main()
