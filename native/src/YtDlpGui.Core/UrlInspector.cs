namespace YtDlpGui.Core;

public static class UrlInspector
{
    public static bool TryCreateHttpUri(string? value, out Uri? uri)
    {
        if (Uri.TryCreate(value?.Trim(), UriKind.Absolute, out var parsed)
            && (parsed.Scheme == Uri.UriSchemeHttp || parsed.Scheme == Uri.UriSchemeHttps)
            && !string.IsNullOrWhiteSpace(parsed.Host))
        {
            uri = parsed;
            return true;
        }

        uri = null;
        return false;
    }

    public static SiteKind DetectSite(string? value)
    {
        if (!TryCreateHttpUri(value, out var uri) || uri is null)
        {
            return SiteKind.Other;
        }

        if (HostMatches(uri.Host, "youtube.com") || HostMatches(uri.Host, "youtu.be"))
        {
            return SiteKind.YouTube;
        }

        if (HostMatches(uri.Host, "bilibili.com") || HostMatches(uri.Host, "b23.tv"))
        {
            return SiteKind.Bilibili;
        }

        return SiteKind.Other;
    }

    public static bool IsYouTubePlaylist(string? value)
    {
        if (!TryCreateHttpUri(value, out var uri) || uri is null || DetectSite(value) != SiteKind.YouTube)
        {
            return false;
        }

        return uri.AbsolutePath.Equals("/playlist", StringComparison.OrdinalIgnoreCase)
            || HasQueryParameter(uri.Query, "list");
    }

    public static string? GetKnownNonVideoMessage(string? value)
    {
        if (!TryCreateHttpUri(value, out var uri) || uri is null)
        {
            return null;
        }

        var host = uri.Host;
        var path = uri.AbsolutePath.ToLowerInvariant();

        if (HostMatches(host, "youtube.com"))
        {
            if (path == "/watch" && !HasQueryParameter(uri.Query, "v"))
            {
                return "该链接不是具体的 YouTube 视频页面";
            }

            if (path.StartsWith("/post/", StringComparison.Ordinal)
                || path.Contains("/community", StringComparison.Ordinal))
            {
                return "该链接是 YouTube 帖子或社区页面，不是视频页面";
            }

            if (path.StartsWith("/results", StringComparison.Ordinal)
                || path.StartsWith("/feed/", StringComparison.Ordinal)
                || path.StartsWith("/hashtag/", StringComparison.Ordinal))
            {
                return "该链接是 YouTube 搜索或导航页面，不是视频页面";
            }
        }

        if (HostMatches(host, "space.bilibili.com"))
        {
            return "该链接是 B站空间主页，不是视频页面";
        }

        if (HostMatches(host, "search.bilibili.com"))
        {
            return "该链接是 B站搜索结果页面，不是视频页面";
        }

        if (HostMatches(host, "t.bilibili.com") || (HostMatches(host, "bilibili.com") && path.StartsWith("/opus/", StringComparison.Ordinal)))
        {
            return "该链接是 B站动态页面，不是视频页面";
        }

        if (HostMatches(host, "bilibili.com") && path.StartsWith("/read/", StringComparison.Ordinal))
        {
            return "该链接是 B站专栏页面，不是视频页面";
        }

        if (HostMatches(host, "douyin.com"))
        {
            if (path.StartsWith("/user/", StringComparison.Ordinal))
            {
                return "该链接是抖音用户主页，不是具体视频页面";
            }

            if (path.StartsWith("/search/", StringComparison.Ordinal) || path == "/hot")
            {
                return "该链接是抖音搜索或导航页面，不是视频页面";
            }

            if (path.StartsWith("/note/", StringComparison.Ordinal))
            {
                return "该链接是抖音图文页面，不是视频页面";
            }
        }

        if (HostMatches(host, "xiaohongshu.com"))
        {
            if (path.StartsWith("/user/profile/", StringComparison.Ordinal))
            {
                return "该链接是小红书用户主页，不是具体视频页面";
            }

            if (path.StartsWith("/search", StringComparison.Ordinal))
            {
                return "该链接是小红书搜索结果页面，不是视频页面";
            }
        }

        if (HostMatches(host, "weibo.com"))
        {
            if (path.StartsWith("/u/", StringComparison.Ordinal))
            {
                return "该链接是微博用户主页，不是具体视频页面";
            }

            if (path.StartsWith("/search", StringComparison.Ordinal))
            {
                return "该链接是微博搜索结果页面，不是视频页面";
            }
        }

        return null;
    }

    public static bool HostMatches(string? host, string domain)
    {
        var normalizedHost = (host ?? string.Empty).Trim().Trim('.').ToLowerInvariant();
        var normalizedDomain = domain.Trim().Trim('.').ToLowerInvariant();
        return normalizedHost == normalizedDomain
            || normalizedHost.EndsWith($".{normalizedDomain}", StringComparison.Ordinal);
    }

    private static bool HasQueryParameter(string query, string key)
    {
        foreach (var part in query.TrimStart('?').Split('&', StringSplitOptions.RemoveEmptyEntries))
        {
            var separator = part.IndexOf('=');
            var encodedKey = separator >= 0 ? part[..separator] : part;
            var encodedValue = separator >= 0 ? part[(separator + 1)..] : string.Empty;
            if (Uri.UnescapeDataString(encodedKey).Equals(key, StringComparison.OrdinalIgnoreCase)
                && !string.IsNullOrWhiteSpace(Uri.UnescapeDataString(encodedValue)))
            {
                return true;
            }
        }

        return false;
    }
}
