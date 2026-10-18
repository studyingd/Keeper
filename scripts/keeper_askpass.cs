// Keeper SSH askpass helper.
// OpenSSH invokes this program (named by SSH_ASKPASS) when it needs a
// password. The helper prints the password passed via the
// KEEPER_SSH_PASSWORD environment variable to stdout and exits 0.
// Compiled with the .NET Framework csc.exe that ships with Windows:
//   csc /nologo /optimize /target:exe /out:keeper-askpass.exe keeper_askpass.cs
// The resulting binary is committed because it cannot be built on macOS or
// Linux, so its SHA-256 is recorded in scripts/keeper-askpass.sha256 and
// scripts/build-windows.ps1 refuses to package a binary that does not match.
// After rebuilding, refresh that file:
//   certutil -hashfile keeper-askpass.exe SHA256
using System;
using System.IO;
using System.Text;

static class KeeperAskpass
{
    static int Main()
    {
        string password = Environment.GetEnvironmentVariable("KEEPER_SSH_PASSWORD");
        if (!string.IsNullOrEmpty(password))
        {
            // Write raw UTF-8 bytes: stdout is a pipe here, so bypass any
            // console/codepage handling entirely.
            Stream stdout = Console.OpenStandardOutput();
            byte[] bytes = Encoding.UTF8.GetBytes(password);
            stdout.Write(bytes, 0, bytes.Length);
            stdout.Flush();
        }
        return 0;
    }
}
