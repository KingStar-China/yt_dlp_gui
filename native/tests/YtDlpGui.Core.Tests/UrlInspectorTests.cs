using YtDlpGui.Core;

namespace YtDlpGui.Core.Tests;

public sealed class UrlInspectorTests
{
    [Theory]
    [InlineData("https://www.youtube.com/watch?v=abc", SiteKind.YouTube)]
    [InlineData("https://youtu.be/abc", SiteKind.YouTube)]
    [InlineData("https://www.bilibili.com/video/BV1xx", SiteKind.Bilibili)]
    [InlineData("https://b23.tv/example", SiteKind.Bilibili)]
    [InlineData("https://example.com/video", SiteKind.Other)]
    public void DetectSite_ClassifiesKnownHosts(string url, SiteKind expected) =>
        Assert.Equal(expected, UrlInspector.DetectSite(url));

    [Theory]
    [InlineData("https://youtube.com.evil.example/watch?v=abc")]
    [InlineData("javascript:alert(1)")]
    [InlineData("not a url")]
    public void DetectSite_DoesNotTrustLookalikeOrInvalidUrls(string url) =>
        Assert.Equal(SiteKind.Other, UrlInspector.DetectSite(url));

    [Theory]
    [InlineData("https://www.youtube.com/playlist?list=PL123")]
    [InlineData("https://www.youtube.com/watch?v=abc&list=PL123")]
    [InlineData("https://youtu.be/abc?list=PL123")]
    public void IsYouTubePlaylist_DetectsPlaylistUrls(string url) =>
        Assert.True(UrlInspector.IsYouTubePlaylist(url));

    [Fact]
    public void IsYouTubePlaylist_RequiresNonEmptyListValue() =>
        Assert.False(UrlInspector.IsYouTubePlaylist("https://www.youtube.com/watch?v=abc&list="));

    [Theory]
    [InlineData("https://www.youtube.com/results?search_query=test")]
    [InlineData("https://space.bilibili.com/123")]
    [InlineData("https://www.douyin.com/user/example")]
    public void GetKnownNonVideoMessage_RejectsKnownNavigationPages(string url) =>
        Assert.False(string.IsNullOrWhiteSpace(UrlInspector.GetKnownNonVideoMessage(url)));

    [Fact]
    public void HostMatches_RequiresARealDomainBoundary()
    {
        Assert.True(UrlInspector.HostMatches("www.youtube.com", "youtube.com"));
        Assert.False(UrlInspector.HostMatches("youtube.com.evil.example", "youtube.com"));
    }
}
