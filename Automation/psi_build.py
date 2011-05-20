import subprocess

def build_client():
    with open('build.cmd', 'w') as file:
        file.write('call "C:\\Program Files\\Microsoft Visual Studio 10.0\\VC\\vcvarsall.bat" x86\n')
        file.write('msbuild psiclient.sln /t:Rebuild /p:Configuration=Release')
    return subprocess.call('build.cmd')

if 0 == build_client():
    print 'Python: SUCCESS'
else:
    print 'Python: FAIL'
