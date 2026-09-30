import pathlib, subprocess, json
root=pathlib.Path('runs/forkrsi/sandbox-probe'); root.mkdir(exist_ok=True)
source=root/'verifier.py'
source.write_text("""import os, socket
assert os.getuid() == 65534
assert not os.path.exists('/root/autodl-tmp/ForkRSI')
for name, fn in [
 ('network', lambda: socket.socket().connect(('127.0.0.1', 8000))),
 ('udp', lambda: socket.socket(type=socket.SOCK_DGRAM).sendto(b'x', ('127.0.0.1', 8000))),
 ('spawn', lambda: os.fork()),
 ('readonly', lambda: open('/verifier.py', 'w')),
 ('host', lambda: open('/root/autodl-tmp/ForkRSI/ForkRSI_目标文档.md')),
]:
 try:
  fn()
 except (PermissionError, FileNotFoundError, ConnectionRefusedError):
  print(name + ': denied')
 else:
  raise AssertionError(name + ' was not denied')
with open('/tmp/check', 'w') as handle: handle.write('allowed scratch')
print('PROBE_OK')
""")
guard=root/'guard.py'; guard.write_text("import runpy; runpy.run_path('/verifier.py', run_name='__main__')\n")
args=['/root/miniconda3/bin/python','src/forkmem/chroot_sandbox.py','--unshare-all','--die-with-parent','--new-session','--ro-bind',str(source.resolve()),'/verifier.py','--ro-bind',str(guard.resolve()),'/guard.py','--tmpfs','/tmp','--dir','/task','--chdir','/task','/usr/bin/python3','-B','/guard.py']
r=subprocess.run(args,capture_output=True,text=True,timeout=90)
print(r.stdout); print(r.stderr); print('EXIT',r.returncode)
(root/'result.json').write_text(json.dumps({'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2))
