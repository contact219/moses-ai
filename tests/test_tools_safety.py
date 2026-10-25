"""The generated-code safety screen must catch Windows wipes, not just Linux ones."""

import unittest

from agent.tools import _looks_destructive

DANGEROUS = [
    "import shutil\nshutil.rmtree('C:\\\\')",
    "shutil.rmtree(r'C:\\')",
    "shutil.rmtree(\"D:/\")",
    "shutil.rmtree(Path.home())",
    "shutil.rmtree(os.path.expanduser('~'))",
    "shutil.rmtree(os.environ['USERPROFILE'])",
    "os.system('rmdir /s /q C:\\\\Users')",
    "subprocess.run('rd /S /Q C:\\\\Windows', shell=True)",
    "os.system('del /f /s /q C:\\\\Windows\\\\System32')",
    "subprocess.run(['powershell', 'Remove-Item -Recurse -Force C:\\\\Users '])",
    "subprocess.run(['powershell', 'Remove-Item $env:USERPROFILE -Recurse'])",
    "subprocess.run(['powershell', 'Format-Volume -DriveLetter D'])",
    "subprocess.run(['powershell', 'Clear-Disk -Number 0 -RemoveData'])",
    "os.system('diskpart /s wipe.txt')",
    "os.system('bcdedit /deletevalue {current} safeboot')",
    "os.system('cipher /w:C')",
    "os.system('vssadmin delete shadows /all')",
    "os.system('reg delete HKLM\\\\Software\\\\Foo /f')",
    "os.system('shutdown /s /t 0')",
    "subprocess.run(['powershell', 'Stop-Computer'])",
    "os.system('format c: /q')",
    "os.system('rm -rf ~')",
]

SAFE = [
    "print('hello')",
    "shutil.rmtree(Path.home() / 'Desktop' / 'old_build')",
    "shutil.rmtree(tmp_dir)",
    "os.remove(os.path.join(downloads, 'report.pdf'))",
    "subprocess.run(['powershell', 'Get-ChildItem C:\\\\Users'])",
    "subprocess.run(['powershell', 'Remove-Item .\\\\build -Recurse'])",
    "print('Ready to format the report')",
    "open(Path.home() / 'Documents' / 'notes.txt').read()",
]


class SafetyScreen(unittest.TestCase):
    def test_windows_and_linux_wipes_are_refused(self):
        for code in DANGEROUS:
            with self.subTest(code=code):
                self.assertIsNotNone(_looks_destructive(code))

    def test_everyday_code_still_runs(self):
        for code in SAFE:
            with self.subTest(code=code):
                self.assertIsNone(_looks_destructive(code))


if __name__ == "__main__":
    unittest.main()
