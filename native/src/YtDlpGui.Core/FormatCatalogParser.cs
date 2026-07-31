using System.Globalization;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace YtDlpGui.Core;

public sealed partial class FormatCatalogParser
{
    private static readonly (string Label, string[] Patterns)[] CodecPriority =
    [
        ("H.264", ["avc1", "avc3", "h264", "avc"]),
        ("H.265", ["hev1", "hvc1", "hevc", "h265"]),
        ("AV1", ["av01", "av1"]),
        ("VP9", ["vp09", "vp9"]),
        ("H.266", ["vvc1", "vvi1", "vvc", "h266"]),
    ];

    public IReadOnlyList<MediaFormat> Parse(string output, bool isPlaylist)
    {
        using var document = ParseDocument(output);
        return isPlaylist ? ParsePlaylist(document.RootElement) : ParseSingleVideo(document.RootElement);
    }

    private static JsonDocument ParseDocument(string output)
    {
        var text = output.Trim();
        if (string.IsNullOrWhiteSpace(text))
        {
            throw new FormatException("嗅探没有返回 JSON。");
        }

        try
        {
            return JsonDocument.Parse(text);
        }
        catch (JsonException)
        {
            foreach (var line in text.Split('\n', StringSplitOptions.RemoveEmptyEntries).Reverse())
            {
                var candidate = line.Trim();
                if (!candidate.StartsWith('{'))
                {
                    continue;
                }

                try
                {
                    return JsonDocument.Parse(candidate);
                }
                catch (JsonException)
                {
                    // Try the previous output line.
                }
            }
        }

        throw new FormatException("嗅探返回了无法解析的 JSON。");
    }

    private static IReadOnlyList<MediaFormat> ParsePlaylist(JsonElement root)
    {
        var count = 0;
        if (root.TryGetProperty("entries", out var entries) && entries.ValueKind == JsonValueKind.Array)
        {
            count = entries.EnumerateArray().Count(entry =>
                entry.ValueKind == JsonValueKind.Object
                && (!string.IsNullOrWhiteSpace(GetString(entry, "id")) || !string.IsNullOrWhiteSpace(GetString(entry, "url"))));
        }

        count = count > 0 ? count : GetInt(root, "playlist_count", "n_entries");
        if (count <= 0)
        {
            return [];
        }

        var title = GetString(root, "playlist_title", "title") ?? "YouTube 视频列表";
        return
        [
            new("youtube-playlist:h264", $"列表批量下载/H.264优先/{count}个视频", MediaKind.Playlist, PlaylistMode: "h264", PlaylistTitle: title, PlaylistCount: count),
            new("youtube-playlist:compatible", $"列表批量下载/最佳兼容/{count}个视频", MediaKind.Playlist, PlaylistMode: "compatible", PlaylistTitle: title, PlaylistCount: count),
        ];
    }

    private static IReadOnlyList<MediaFormat> ParseSingleVideo(JsonElement root)
    {
        var videos = new List<VideoCandidate>();
        var audios = new List<AudioCandidate>();

        if (root.TryGetProperty("formats", out var formats) && formats.ValueKind == JsonValueKind.Array)
        {
            foreach (var format in formats.EnumerateArray())
            {
                var id = GetString(format, "format_id");
                if (string.IsNullOrWhiteSpace(id))
                {
                    continue;
                }

                var videoCodec = (GetString(format, "vcodec") ?? string.Empty).ToLowerInvariant();
                var audioCodec = (GetString(format, "acodec") ?? string.Empty).ToLowerInvariant();
                var extension = (GetString(format, "ext") ?? string.Empty).ToLowerInvariant();
                var fileSize = GetLong(format, "filesize", "filesize_approx");
                var isAudio = videoCodec == "none" && audioCodec != "none";

                if (isAudio)
                {
                    var isAac = audioCodec.Contains("aac", StringComparison.Ordinal)
                        || audioCodec.Contains("mp4a", StringComparison.Ordinal)
                        || extension is "m4a" or "aac";
                    if (isAac)
                    {
                        audios.Add(new(id, GetDouble(format, "tbr"), fileSize));
                    }

                    continue;
                }

                var resolution = GetResolution(format);
                var (codecLabel, codecRank) = GetCodec(videoCodec);
                if (resolution is null || codecLabel is null)
                {
                    continue;
                }

                videos.Add(new(
                    id,
                    resolution.Value,
                    codecLabel,
                    codecRank,
                    audioCodec != "none",
                    GetDouble(format, "fps"),
                    GetDouble(format, "tbr"),
                    fileSize));
            }
        }

        var result = videos
            .GroupBy(candidate => candidate.Height)
            .Select(SelectBestVideo)
            .OrderByDescending(candidate => candidate.Height)
            .Select(candidate => new MediaFormat(
                candidate.Id,
                BuildVideoLabel(candidate),
                MediaKind.Video,
                candidate.HasAudio))
            .ToList();

        if (audios.Count > 0)
        {
            var audio = audios
                .OrderByDescending(candidate => candidate.Bitrate)
                .ThenByDescending(candidate => candidate.FileSize)
                .ThenByDescending(candidate => candidate.Id, StringComparer.Ordinal)
                .First();
            var size = FileNameSanitizer.FormatSize(audio.FileSize);
            result.Add(new(audio.Id, $"音频/AAC{(size.Length > 0 ? $"/{size}" : string.Empty)}", MediaKind.Audio));
        }

        AddSubtitles(root, "subtitles", "manual", "字幕", result);
        AddSubtitles(root, "automatic_captions", "auto", "自动字幕", result);
        return result;
    }

    private static VideoCandidate SelectBestVideo(IGrouping<int, VideoCandidate> group)
    {
        var bestRank = group.Min(candidate => candidate.CodecRank);
        return group
            .Where(candidate => candidate.CodecRank == bestRank)
            .OrderByDescending(candidate => candidate.Fps)
            .ThenByDescending(candidate => candidate.Bitrate)
            .ThenByDescending(candidate => candidate.FileSize)
            .ThenByDescending(candidate => candidate.Id, StringComparer.Ordinal)
            .First();
    }

    private static string BuildVideoLabel(VideoCandidate candidate)
    {
        var parts = new List<string> { $"{candidate.Height}p", candidate.CodecLabel };
        if (candidate.Fps > 0)
        {
            parts.Add($"{Math.Round(candidate.Fps):0}fps");
        }

        var size = FileNameSanitizer.FormatSize(candidate.FileSize);
        if (size.Length > 0)
        {
            parts.Add(size);
        }

        return string.Join('/', parts);
    }

    private static void AddSubtitles(JsonElement root, string propertyName, string mode, string label, List<MediaFormat> result)
    {
        if (!root.TryGetProperty(propertyName, out var subtitles) || subtitles.ValueKind != JsonValueKind.Object)
        {
            return;
        }

        foreach (var language in subtitles.EnumerateObject())
        {
            if (language.Value.ValueKind != JsonValueKind.Array || language.Value.GetArrayLength() == 0)
            {
                continue;
            }

            var extensions = language.Value
                .EnumerateArray()
                .Select(entry => GetString(entry, "ext"))
                .Where(extension => !string.IsNullOrWhiteSpace(extension))
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToArray();
            var extensionLabel = extensions.Length > 0 ? $"/{string.Join(',', extensions)}" : string.Empty;
            result.Add(new($"subtitle:{language.Name}:{mode}", $"{label}/{language.Name}{extensionLabel}", MediaKind.Subtitle));
        }
    }

    private static (string? Label, int Rank) GetCodec(string codec)
    {
        for (var index = 0; index < CodecPriority.Length; index++)
        {
            if (CodecPriority[index].Patterns.Any(pattern => codec.Contains(pattern, StringComparison.Ordinal)))
            {
                return (CodecPriority[index].Label, index);
            }
        }

        if (string.IsNullOrWhiteSpace(codec) || codec == "none")
        {
            return (null, CodecPriority.Length);
        }

        var fallback = codec.Split('.')[0].Replace("-", string.Empty).Replace("_", string.Empty).ToUpperInvariant();
        return (fallback.Length > 0 ? fallback : "OTHER", CodecPriority.Length);
    }

    private static int? GetResolution(JsonElement format)
    {
        var height = GetInt(format, "height");
        if (height > 0)
        {
            return height;
        }

        var resolution = GetString(format, "resolution") ?? string.Empty;
        var match = ResolutionSuffix().Match(resolution);
        if (match.Success && int.TryParse(match.Groups[1].Value, out height))
        {
            return height;
        }

        match = ResolutionDimensions().Match(resolution);
        return match.Success && int.TryParse(match.Groups[2].Value, out height) ? height : null;
    }

    private static string? GetString(JsonElement element, params string[] names)
    {
        foreach (var name in names)
        {
            if (element.TryGetProperty(name, out var property) && property.ValueKind == JsonValueKind.String)
            {
                return property.GetString();
            }
        }

        return null;
    }

    private static int GetInt(JsonElement element, params string[] names)
    {
        foreach (var name in names)
        {
            if (!element.TryGetProperty(name, out var property))
            {
                continue;
            }

            if (property.ValueKind == JsonValueKind.Number && property.TryGetInt32(out var value))
            {
                return value;
            }

            if (property.ValueKind == JsonValueKind.String && int.TryParse(property.GetString(), out value))
            {
                return value;
            }
        }

        return 0;
    }

    private static long GetLong(JsonElement element, params string[] names)
    {
        foreach (var name in names)
        {
            if (!element.TryGetProperty(name, out var property))
            {
                continue;
            }

            if (property.ValueKind == JsonValueKind.Number && property.TryGetInt64(out var value))
            {
                return value;
            }

            if (property.ValueKind == JsonValueKind.Number && property.TryGetDouble(out var doubleValue))
            {
                return (long)doubleValue;
            }
        }

        return 0;
    }

    private static double GetDouble(JsonElement element, string name)
    {
        if (!element.TryGetProperty(name, out var property))
        {
            return 0;
        }

        if (property.ValueKind == JsonValueKind.Number && property.TryGetDouble(out var value))
        {
            return value;
        }

        return property.ValueKind == JsonValueKind.String
            && double.TryParse(property.GetString(), NumberStyles.Float, CultureInfo.InvariantCulture, out value)
                ? value
                : 0;
    }

    private sealed record VideoCandidate(
        string Id,
        int Height,
        string CodecLabel,
        int CodecRank,
        bool HasAudio,
        double Fps,
        double Bitrate,
        long FileSize);

    private sealed record AudioCandidate(string Id, double Bitrate, long FileSize);

    [GeneratedRegex(@"(\d{3,4})p", RegexOptions.IgnoreCase)]
    private static partial Regex ResolutionSuffix();

    [GeneratedRegex(@"(\d{3,4})x(\d{3,4})", RegexOptions.IgnoreCase)]
    private static partial Regex ResolutionDimensions();
}
