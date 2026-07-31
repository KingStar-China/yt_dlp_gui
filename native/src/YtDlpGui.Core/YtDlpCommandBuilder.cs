namespace YtDlpGui.Core;

public static class YtDlpCommandBuilder
{
    public const string H264PlaylistFormat = "bv*[ext=mp4][vcodec^=avc]+ba[ext=m4a]/b[ext=mp4][vcodec^=avc]";
    public const string CompatiblePlaylistFormat = "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b";

    public static IReadOnlyList<string> BuildSniff(
        string url,
        CookieSource cookieSource,
        string? manualCookiePath,
        bool isPlaylist)
    {
        var arguments = new List<string>
        {
            "--dump-single-json",
            "--no-warnings",
            "--no-color",
        };

        if (isPlaylist)
        {
            arguments.AddRange(["--flat-playlist", "--ignore-errors", "--yes-playlist"]);
        }
        else
        {
            arguments.Add("--no-playlist");
        }

        AddCookieArguments(arguments, cookieSource, manualCookiePath);
        arguments.Add(url);
        return arguments;
    }

    public static IReadOnlyList<string> BuildDownload(DownloadRequest request)
    {
        var format = request.Format;
        var arguments = new List<string> { "--no-color" };

        switch (format.Kind)
        {
            case MediaKind.Playlist:
                var playlistTitle = FileNameSanitizer.Sanitize(format.PlaylistTitle, "YouTube 视频列表");
                var playlistFormat = format.PlaylistMode == "compatible"
                    ? CompatiblePlaylistFormat
                    : H264PlaylistFormat;
                arguments.AddRange([
                    "--yes-playlist",
                    "--ignore-errors",
                    "-f", playlistFormat,
                    "--merge-output-format", "mp4",
                    "-o", $"{playlistTitle}/%(playlist_index)03d - %(title)s.%(ext)s",
                ]);
                break;

            case MediaKind.Subtitle:
                var subtitleParts = format.Id.Split(':', 3);
                if (subtitleParts.Length != 3)
                {
                    throw new ArgumentException("字幕格式标识无效。", nameof(request));
                }

                arguments.Add(subtitleParts[2] == "auto" ? "--write-auto-sub" : "--write-sub");
                arguments.AddRange(["--sub-lang", subtitleParts[1], "--convert-subs", "srt", "--skip-download"]);
                break;

            case MediaKind.Audio:
                arguments.AddRange(["-f", format.Id]);
                break;

            case MediaKind.Video when format.HasAudio:
                arguments.AddRange(["-f", format.Id]);
                break;

            case MediaKind.Video:
                arguments.AddRange(["-f", $"{format.Id}+bestaudio[ext=m4a]", "--merge-output-format", "mp4"]);
                break;

            default:
                throw new ArgumentOutOfRangeException(nameof(request), "未知的媒体格式类型。");
        }

        AddCookieArguments(arguments, request.CookieSource, request.ManualCookiePath);
        arguments.AddRange([
            "-P", request.OutputDirectory,
            "--newline",
            "--print", "after_move:__YTDLP_FILE__:%(filepath)s",
            request.Url,
        ]);
        return arguments;
    }

    public static bool NeedsFfmpeg(MediaFormat format) => format.Kind switch
    {
        MediaKind.Playlist => true,
        MediaKind.Subtitle => true,
        MediaKind.Video => !format.HasAudio,
        _ => false,
    };

    private static void AddCookieArguments(List<string> arguments, CookieSource source, string? manualCookiePath)
    {
        switch (source)
        {
            case CookieSource.ManualFile when !string.IsNullOrWhiteSpace(manualCookiePath):
                arguments.AddRange(["--cookies", manualCookiePath]);
                break;
            case CookieSource.Firefox:
                arguments.AddRange(["--cookies-from-browser", "firefox"]);
                break;
            case CookieSource.Edge:
                arguments.AddRange(["--cookies-from-browser", "edge"]);
                break;
            case CookieSource.Chrome:
                arguments.AddRange(["--cookies-from-browser", "chrome"]);
                break;
        }
    }
}
