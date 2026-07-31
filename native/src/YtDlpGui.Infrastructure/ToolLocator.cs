using YtDlpGui.Core;

namespace YtDlpGui.Infrastructure;

public static class ToolLocator
{
    public static ToolPaths Locate(string? startDirectory = null)
    {
        var start = Path.GetFullPath(startDirectory ?? AppContext.BaseDirectory);
        var ytDlp = FindExecutable("yt-dlp.exe", start)
            ?? Path.Combine(start, "yt-dlp.exe");
        var ffmpeg = FindExecutable("ffmpeg.exe", start);
        return new(ytDlp, ffmpeg);
    }

    private static string? FindExecutable(string fileName, string startDirectory)
    {
        var checkedDirectories = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var origin in new[] { startDirectory, Environment.CurrentDirectory })
        {
            var directory = new DirectoryInfo(origin);
            while (directory is not null)
            {
                if (checkedDirectories.Add(directory.FullName))
                {
                    var candidate = Path.Combine(directory.FullName, fileName);
                    if (File.Exists(candidate))
                    {
                        return candidate;
                    }
                }

                directory = directory.Parent;
            }
        }

        var path = Environment.GetEnvironmentVariable("PATH") ?? string.Empty;
        foreach (var directory in path.Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        {
            try
            {
                var candidate = Path.Combine(directory.Trim('"'), fileName);
                if (File.Exists(candidate))
                {
                    return candidate;
                }
            }
            catch (Exception) when (directory.Length > 0)
            {
                // Ignore malformed PATH entries.
            }
        }

        return null;
    }
}
