using System.Globalization;
using System.Text.Json;

namespace YtDlpGui.Core;

public sealed class BilibiliDirectParser
{
    private static readonly (string Label, string[] Patterns)[] CodecPriority =
    [
        ("H.264", ["avc1", "avc3", "h264", "avc"]),
        ("H.265", ["hev1", "hvc1", "hevc", "h265"]),
        ("AV1", ["av01", "av1"]),
        ("VP9", ["vp09", "vp9"]),
        ("H.266", ["vvc1", "vvi1", "vvc", "h266"]),
    ];

    public IReadOnlyList<MediaFormat> Parse(
        string playInfoJson,
        string? initialStateJson,
        string pageUrl,
        string userAgent)
    {
        using var playInfo = JsonDocument.Parse(playInfoJson);
        using var initialState = string.IsNullOrWhiteSpace(initialStateJson)
            ? null
            : JsonDocument.Parse(initialStateJson);
        var data = playInfo.RootElement.TryGetProperty("data", out var dataElement)
            ? dataElement
            : playInfo.RootElement;
        if (!data.TryGetProperty("dash", out var dash) || dash.ValueKind != JsonValueKind.Object)
        {
            return [];
        }

        var title = GetTitle(initialState?.RootElement) ?? "bilibili_video";
        var audioCandidates = ParseAudioCandidates(dash).ToArray();
        var preferredAudio = audioCandidates
            .OrderByDescending(candidate => candidate.Bandwidth)
            .ThenByDescending(candidate => candidate.FileSize)
            .FirstOrDefault();
        var result = new List<MediaFormat>();

        if (preferredAudio is not null)
        {
            var size = FileNameSanitizer.FormatSize(preferredAudio.FileSize);
            result.Add(new(
                $"bili-direct-audio:{preferredAudio.Index}",
                $"音频/AAC{(size.Length > 0 ? $"/{size}" : string.Empty)}",
                MediaKind.Audio,
                DirectPayload: new(title, pageUrl, userAgent, AudioUrl: preferredAudio.Url)));
        }

        var videos = ParseVideoCandidates(dash).ToArray();
        var selectedVideos = videos
            .GroupBy(candidate => candidate.Height)
            .Select(group =>
            {
                var bestRank = group.Min(candidate => candidate.CodecRank);
                return group
                    .Where(candidate => candidate.CodecRank == bestRank)
                    .OrderByDescending(candidate => candidate.Fps)
                    .ThenByDescending(candidate => candidate.Bandwidth)
                    .ThenByDescending(candidate => candidate.FileSize)
                    .First();
            })
            .OrderByDescending(candidate => candidate.Height);

        foreach (var video in selectedVideos)
        {
            var labelParts = new List<string> { $"{video.Height}p", video.CodecLabel };
            if (video.Fps > 0)
            {
                labelParts.Add($"{Math.Round(video.Fps):0}fps");
            }

            var size = FileNameSanitizer.FormatSize(video.FileSize);
            if (size.Length > 0)
            {
                labelParts.Add(size);
            }

            result.Insert(result.Count > 0 ? result.Count - 1 : 0, new(
                $"bili-direct-video:{video.Index}",
                string.Join('/', labelParts),
                MediaKind.Video,
                DirectPayload: new(title, pageUrl, userAgent, video.Url, preferredAudio?.Url)));
        }

        return result
            .OrderByDescending(format => format.Kind == MediaKind.Video ? ParseHeight(format.Label) : -1)
            .ToArray();
    }

    private static IEnumerable<AudioCandidate> ParseAudioCandidates(JsonElement dash)
    {
        if (!dash.TryGetProperty("audio", out var audios) || audios.ValueKind != JsonValueKind.Array)
        {
            yield break;
        }

        var index = 0;
        foreach (var audio in audios.EnumerateArray())
        {
            var codec = (GetString(audio, "codecs") ?? string.Empty).ToLowerInvariant();
            var url = GetString(audio, "baseUrl", "base_url", "url");
            if (!string.IsNullOrWhiteSpace(url)
                && (codec.Contains("mp4a", StringComparison.Ordinal) || codec.Contains("aac", StringComparison.Ordinal)))
            {
                yield return new(index, url, GetDouble(audio, "bandwidth"), GetLong(audio, "size"));
            }

            index++;
        }
    }

    private static IEnumerable<VideoCandidate> ParseVideoCandidates(JsonElement dash)
    {
        if (!dash.TryGetProperty("video", out var videos) || videos.ValueKind != JsonValueKind.Array)
        {
            yield break;
        }

        var index = 0;
        foreach (var video in videos.EnumerateArray())
        {
            var codec = (GetString(video, "codecs") ?? string.Empty).ToLowerInvariant();
            var url = GetString(video, "baseUrl", "base_url", "url");
            var height = GetInt(video, "height");
            var (codecLabel, codecRank) = GetCodec(codec);
            if (!string.IsNullOrWhiteSpace(url) && height > 0 && codecLabel is not null)
            {
                yield return new(
                    index,
                    url,
                    height,
                    codecLabel,
                    codecRank,
                    GetDouble(video, "frameRate", "frame_rate"),
                    GetDouble(video, "bandwidth"),
                    GetLong(video, "size"));
            }

            index++;
        }
    }

    private static string? GetTitle(JsonElement? initialState)
    {
        if (initialState is null)
        {
            return null;
        }

        if (initialState.Value.TryGetProperty("videoData", out var videoData))
        {
            var videoTitle = GetString(videoData, "title");
            if (!string.IsNullOrWhiteSpace(videoTitle))
            {
                return videoTitle;
            }
        }

        return GetString(initialState.Value, "h1Title");
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

        if (string.IsNullOrWhiteSpace(codec))
        {
            return (null, CodecPriority.Length);
        }

        return (codec.Split('.')[0].ToUpperInvariant(), CodecPriority.Length);
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

    private static int GetInt(JsonElement element, string name)
    {
        if (!element.TryGetProperty(name, out var property))
        {
            return 0;
        }

        if (property.ValueKind == JsonValueKind.Number && property.TryGetInt32(out var value))
        {
            return value;
        }

        return property.ValueKind == JsonValueKind.String && int.TryParse(property.GetString(), out value) ? value : 0;
    }

    private static long GetLong(JsonElement element, string name)
    {
        if (!element.TryGetProperty(name, out var property))
        {
            return 0;
        }

        if (property.ValueKind == JsonValueKind.Number && property.TryGetInt64(out var value))
        {
            return value;
        }

        return property.ValueKind == JsonValueKind.String && long.TryParse(property.GetString(), out value) ? value : 0;
    }

    private static double GetDouble(JsonElement element, params string[] names)
    {
        foreach (var name in names)
        {
            if (!element.TryGetProperty(name, out var property))
            {
                continue;
            }

            if (property.ValueKind == JsonValueKind.Number && property.TryGetDouble(out var value))
            {
                return value;
            }

            if (property.ValueKind == JsonValueKind.String
                && double.TryParse(property.GetString(), NumberStyles.Float, CultureInfo.InvariantCulture, out value))
            {
                return value;
            }
        }

        return 0;
    }

    private static int ParseHeight(string label)
    {
        var firstPart = label.Split('/')[0];
        return firstPart.EndsWith('p') && int.TryParse(firstPart[..^1], out var height) ? height : 0;
    }

    private sealed record AudioCandidate(int Index, string Url, double Bandwidth, long FileSize);

    private sealed record VideoCandidate(
        int Index,
        string Url,
        int Height,
        string CodecLabel,
        int CodecRank,
        double Fps,
        double Bandwidth,
        long FileSize);
}
