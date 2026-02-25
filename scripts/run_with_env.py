import os, sys, subprocess

root = os.path.dirname(os.path.dirname(__file__))
logpath = os.path.join(root, 'scripts', 'gui_run.log')
env = os.environ.copy()
env['VFXPLAYER_ALLOW_EXR'] = '1'
env['VFXPLAYER_DEBUG'] = '1'
env['VFXPLAYER_OIIO_BIN'] = r'D:\exrtojpg\VFXPlayer\bin\oiio\windows'

with open(logpath, 'wb') as f:
    p = subprocess.Popen([sys.executable, os.path.join(root, 'main.py')], cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out, _ = p.communicate()
    if out:
        try:
            f.write(out)
        except Exception:
            f.write(out.encode('utf-8', errors='replace'))
    print('Process exited with code', p.returncode)
    print('Log written to', logpath)
