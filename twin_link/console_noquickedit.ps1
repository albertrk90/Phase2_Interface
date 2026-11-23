# Switch off QuickEdit for THIS console window (20 Nov 2026). With QuickEdit on, a click or text selection inside the window pauses
# the program at its next output until a key is pressed -- a twin or host paused like that stops answering mid-sequence.
$sig = '[DllImport("kernel32.dll")] public static extern IntPtr GetStdHandle(int h);' +
       '[DllImport("kernel32.dll")] public static extern bool GetConsoleMode(IntPtr h, out int m);' +
       '[DllImport("kernel32.dll")] public static extern bool SetConsoleMode(IntPtr h, int m);'
try {
    $k = Add-Type -MemberDefinition $sig -Name ConsoleMode -Namespace Phase2 -PassThru
    $h = $k::GetStdHandle(-10); $m = 0
    if ($k::GetConsoleMode($h, [ref]$m)) { [void]$k::SetConsoleMode($h, (($m -band (-bnot 0x40)) -bor 0x80)) }
} catch { }
