using YtDlpGui.Core;
using YtDlpGui.Infrastructure;

namespace YtDlpGui.Core.Tests;

public sealed class LiveIntegrationTests
{
    private static bool LiveTestsEnabled =>
        Environment.GetEnvironmentVariable("YTDLP_GUI_LIVE_TEST") == "1";

    [Fact]
    [Trait("Category", "Live")]
    public async Task PublicYouTubeVideo_SniffsThroughNativeService()
    {
        if (!LiveTestsEnabled)
        {
            return;
        }

        var repositoryRoot = FindRepositoryRoot();
        using var service = new YtDlpService(new(
            Path.Combine(repositoryRoot, "yt-dlp.exe"),
            Path.Combine(repositoryRoot, "ffmpeg.exe")));

        var result = await service.SniffAsync(new(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            TryBrowserCookies: false));

        Assert.True(result.IsSuccess, result.Message);
        Assert.Contains(result.Formats, format => format.Kind == MediaKind.Video);
        Assert.Contains(result.Formats, format => format.Kind == MediaKind.Audio);
        Assert.Equal(CookieSource.None, result.CookieSource);
    }

    [Fact]
    [Trait("Category", "Live")]
    public async Task PublicBilibiliPage_UsesDirectFallbackWhenToolFails()
    {
        if (!LiveTestsEnabled)
        {
            return;
        }

        var failingTool = Path.Combine(Environment.SystemDirectory, "where.exe");
        using var service = new YtDlpService(new(failingTool, null));

        var result = await service.SniffAsync(new(
            "https://www.bilibili.com/video/BV1xx411c7mD",
            TryBrowserCookies: false));

        Assert.True(result.IsSuccess, result.Message);
        Assert.Contains(result.Formats, format => format.Kind == MediaKind.Video && format.DirectPayload is not null);
        Assert.Contains(result.Formats, format => format.Kind == MediaKind.Audio && format.DirectPayload is not null);
        Assert.Equal(CookieSource.None, result.CookieSource);
    }

    private static string FindRepositoryRoot()
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null)
        {
            if (File.Exists(Path.Combine(directory.FullName, "yt-dlp.exe")))
            {
                return directory.FullName;
            }

            directory = directory.Parent;
        }

        throw new DirectoryNotFoundException("无法从测试目录定位仓库根目录。");
    }
}
