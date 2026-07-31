using System.Globalization;
using System.Text.RegularExpressions;

namespace YtDlpGui.Core;

public static partial class FileNameSanitizer
{
    private static readonly HashSet<string> ReservedNames = new(StringComparer.OrdinalIgnoreCase)
    {
        "con", "prn", "aux", "nul",
        "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
        "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
    };

    public static string Sanitize(string? value, string fallback = "video")
    {
        var sanitized = InvalidFileNameCharacters().Replace((value ?? string.Empty).Trim(), "_").TrimEnd(' ', '.');
        if (string.IsNullOrWhiteSpace(sanitized))
        {
            return fallback;
        }

        return ReservedNames.Contains(sanitized) ? $"_{sanitized}" : sanitized;
    }

    public static string FormatSize(long size)
    {
        if (size <= 0)
        {
            return string.Empty;
        }

        if (size >= 1024L * 1024 * 1024)
        {
            return $"{(size / (1024d * 1024 * 1024)).ToString("0.##", CultureInfo.InvariantCulture)}GB";
        }

        if (size >= 1024L * 1024)
        {
            return $"{(size / (1024d * 1024)).ToString("0.#", CultureInfo.InvariantCulture)}MB";
        }

        if (size >= 1024)
        {
            return $"{(size / 1024d).ToString("0.#", CultureInfo.InvariantCulture)}KB";
        }

        return $"{size}B";
    }

    [GeneratedRegex("[<>:\"/\\\\|?*]")]
    private static partial Regex InvalidFileNameCharacters();
}
