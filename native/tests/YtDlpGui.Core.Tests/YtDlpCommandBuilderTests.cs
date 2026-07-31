using YtDlpGui.Core;

namespace YtDlpGui.Core.Tests;

public sealed class YtDlpCommandBuilderTests
{
    [Fact]
    public void BuildSniff_UsesFlatPlaylistAndManualCookies()
    {
        var arguments = YtDlpCommandBuilder.BuildSniff(
            "https://youtube.com/playlist?list=PL1",
            CookieSource.ManualFile,
            "cookies.txt",
            isPlaylist: true);

        Assert.Contains("--flat-playlist", arguments);
        Assert.Contains("--yes-playlist", arguments);
        AssertPair(arguments, "--cookies", "cookies.txt");
        Assert.DoesNotContain("--no-playlist", arguments);
    }

    [Fact]
    public void BuildDownload_MergesVideoOnlyFormatWithM4aAudio()
    {
        var format = new MediaFormat("137", "1080p/H.264/30fps", MediaKind.Video);
        var request = new DownloadRequest("https://example.com/video", format, "D:\\Downloads", CookieSource.Firefox);

        var arguments = YtDlpCommandBuilder.BuildDownload(request);

        AssertPair(arguments, "-f", "137+bestaudio[ext=m4a]");
        AssertPair(arguments, "--merge-output-format", "mp4");
        AssertPair(arguments, "--cookies-from-browser", "firefox");
        AssertPair(arguments, "-P", "D:\\Downloads");
    }

    [Fact]
    public void BuildDownload_DoesNotMergeProgressiveVideo()
    {
        var format = new MediaFormat("22", "720p/H.264/30fps", MediaKind.Video, HasAudio: true);
        var request = new DownloadRequest("https://example.com/video", format, "D:\\Downloads", CookieSource.None);

        var arguments = YtDlpCommandBuilder.BuildDownload(request);

        AssertPair(arguments, "-f", "22");
        Assert.DoesNotContain("--merge-output-format", arguments);
        Assert.False(YtDlpCommandBuilder.NeedsFfmpeg(format));
    }

    [Fact]
    public void BuildDownload_ConfiguresAutomaticSubtitleConversion()
    {
        var format = new MediaFormat("subtitle:zh-Hans:auto", "自动字幕/zh-Hans/vtt", MediaKind.Subtitle);
        var request = new DownloadRequest("https://example.com/video", format, "D:\\Downloads", CookieSource.None);

        var arguments = YtDlpCommandBuilder.BuildDownload(request);

        Assert.Contains("--write-auto-sub", arguments);
        AssertPair(arguments, "--sub-lang", "zh-Hans");
        AssertPair(arguments, "--convert-subs", "srt");
        Assert.Contains("--skip-download", arguments);
        Assert.True(YtDlpCommandBuilder.NeedsFfmpeg(format));
    }

    [Fact]
    public void BuildDownload_UsesCompatiblePlaylistMode()
    {
        var format = new MediaFormat(
            "youtube-playlist:compatible",
            "列表批量下载/最佳兼容/3个视频",
            MediaKind.Playlist,
            PlaylistMode: "compatible",
            PlaylistTitle: "A:B",
            PlaylistCount: 3);
        var request = new DownloadRequest("https://youtube.com/playlist?list=PL1", format, "D:\\Downloads", CookieSource.None);

        var arguments = YtDlpCommandBuilder.BuildDownload(request);

        AssertPair(arguments, "-f", YtDlpCommandBuilder.CompatiblePlaylistFormat);
        AssertPair(arguments, "-o", "A_B/%(playlist_index)03d - %(title)s.%(ext)s");
    }

    private static void AssertPair(IReadOnlyList<string> arguments, string option, string expectedValue)
    {
        var index = arguments.IndexOf(option);
        Assert.True(index >= 0, $"Missing option {option}");
        Assert.True(index + 1 < arguments.Count, $"Missing value for {option}");
        Assert.Equal(expectedValue, arguments[index + 1]);
    }
}

internal static class ReadOnlyListExtensions
{
    public static int IndexOf<T>(this IReadOnlyList<T> values, T value)
    {
        for (var index = 0; index < values.Count; index++)
        {
            if (EqualityComparer<T>.Default.Equals(values[index], value))
            {
                return index;
            }
        }

        return -1;
    }
}
