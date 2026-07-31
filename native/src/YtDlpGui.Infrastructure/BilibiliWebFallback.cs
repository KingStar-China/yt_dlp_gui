using System.Globalization;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using YtDlpGui.Core;

namespace YtDlpGui.Infrastructure;

internal sealed class BilibiliWebFallback(HttpClient httpClient)
{
    public const string UserAgent =
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        + "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36";

    private static readonly int[] MixinKeyTable =
    [
        46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
        27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
        37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
        22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
    ];

    private readonly BilibiliDirectParser _parser = new();

    public async Task<SniffResult> SniffAsync(
        string url,
        CookieSource cookieSource,
        string? manualCookiePath,
        IProgress<string>? progress,
        CancellationToken cancellationToken)
    {
        progress?.Report("常规嗅探失败，正在尝试 B站网页直连嗅探...");
        var cookieHeader = cookieSource == CookieSource.ManualFile
            ? BuildCookieHeader(manualCookiePath, url)
            : string.Empty;

        try
        {
            var html = await GetStringAsync(url, url, cookieHeader, includeOrigin: false, cancellationToken).ConfigureAwait(false);
            var playInfoJson = ExtractEmbeddedJson(html, "window.__playinfo__");
            var initialStateJson = ExtractEmbeddedJson(html, "window.__INITIAL_STATE__");

            if (playInfoJson is null && initialStateJson is not null)
            {
                playInfoJson = await FetchPlayInfoFromApiAsync(
                    url,
                    initialStateJson,
                    cookieHeader,
                    cancellationToken).ConfigureAwait(false);
            }

            if (playInfoJson is null)
            {
                if (ContainsVerificationPage(html))
                {
                    return SniffResult.Failure("B站返回了风控/验证页面，请稍后重试或提供 Cookie。");
                }

                var title = ExtractHtmlTitle(html);
                return SniffResult.Failure(string.IsNullOrWhiteSpace(title)
                    ? "B站页面里没找到播放器数据。"
                    : $"B站返回的不是标准视频页：{title}");
            }

            var formats = _parser.Parse(playInfoJson, initialStateJson, url, UserAgent);
            return formats.Count == 0
                ? SniffResult.Failure("B站网页已打开，但没解析到可直连的视频或 AAC 音频格式。")
                : new(true, "B站网页直连嗅探完成", formats, cookieSource);
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (JsonException exception)
        {
            return SniffResult.Failure($"B站播放器数据格式异常：{exception.Message}");
        }
        catch (Exception exception) when (exception is HttpRequestException or IOException or InvalidOperationException)
        {
            return SniffResult.Failure($"B站网页直连嗅探失败：{exception.Message}");
        }
    }

    private async Task<string?> FetchPlayInfoFromApiAsync(
        string pageUrl,
        string initialStateJson,
        string cookieHeader,
        CancellationToken cancellationToken)
    {
        using var initialState = JsonDocument.Parse(initialStateJson);
        if (!initialState.RootElement.TryGetProperty("videoData", out var videoData))
        {
            return null;
        }

        var bvid = GetString(videoData, "bvid") ?? GetString(initialState.RootElement, "bvid");
        var cid = GetPageCid(videoData, pageUrl);
        if (string.IsNullOrWhiteSpace(bvid) || string.IsNullOrWhiteSpace(cid))
        {
            return null;
        }

        var mixinKey = GetDefaultMixinKey(initialState.RootElement);
        if (string.IsNullOrWhiteSpace(mixinKey))
        {
            var navJson = await GetStringAsync(
                "https://api.bilibili.com/x/web-interface/nav",
                pageUrl,
                cookieHeader,
                includeOrigin: false,
                cancellationToken).ConfigureAwait(false);
            using var nav = JsonDocument.Parse(navJson);
            if (nav.RootElement.TryGetProperty("data", out var navData)
                && navData.TryGetProperty("wbi_img", out var wbiImage))
            {
                mixinKey = BuildMixinKey(GetString(wbiImage, "img_url"), GetString(wbiImage, "sub_url"));
            }
        }

        if (string.IsNullOrWhiteSpace(mixinKey))
        {
            return null;
        }

        var parameters = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["bvid"] = bvid,
            ["cid"] = cid,
            ["fnval"] = "4048",
            ["qn"] = "127",
            ["fourk"] = "1",
            ["wts"] = DateTimeOffset.UtcNow.ToUnixTimeSeconds().ToString(CultureInfo.InvariantCulture),
        };
        var signedQuery = SignParameters(parameters, mixinKey);
        var apiUrl = $"https://api.bilibili.com/x/player/wbi/playurl?{signedQuery}";
        var payload = await GetStringAsync(apiUrl, pageUrl, cookieHeader, includeOrigin: true, cancellationToken).ConfigureAwait(false);
        using var document = JsonDocument.Parse(payload);
        var code = document.RootElement.TryGetProperty("code", out var codeElement) && codeElement.TryGetInt32(out var codeValue)
            ? codeValue
            : -1;
        if (code != 0)
        {
            var message = GetString(document.RootElement, "message") ?? code.ToString(CultureInfo.InvariantCulture);
            throw new InvalidOperationException($"B站播放接口返回异常：{message}");
        }

        return payload;
    }

    private async Task<string> GetStringAsync(
        string url,
        string referer,
        string cookieHeader,
        bool includeOrigin,
        CancellationToken cancellationToken)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, url);
        request.Headers.TryAddWithoutValidation("User-Agent", UserAgent);
        request.Headers.Referrer = new Uri(referer);
        if (includeOrigin)
        {
            request.Headers.TryAddWithoutValidation("Origin", "https://www.bilibili.com");
        }

        if (!string.IsNullOrWhiteSpace(cookieHeader))
        {
            request.Headers.TryAddWithoutValidation("Cookie", cookieHeader);
        }

        using var response = await httpClient.SendAsync(request, HttpCompletionOption.ResponseContentRead, cancellationToken).ConfigureAwait(false);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
    }

    private static string? ExtractEmbeddedJson(string html, string marker)
    {
        var markerIndex = html.IndexOf(marker, StringComparison.Ordinal);
        if (markerIndex < 0)
        {
            return null;
        }

        var start = html.IndexOf('{', markerIndex + marker.Length);
        if (start < 0)
        {
            return null;
        }

        var depth = 0;
        var inString = false;
        var escape = false;
        for (var index = start; index < html.Length; index++)
        {
            var character = html[index];
            if (inString)
            {
                if (escape)
                {
                    escape = false;
                }
                else if (character == '\\')
                {
                    escape = true;
                }
                else if (character == '"')
                {
                    inString = false;
                }

                continue;
            }

            if (character == '"')
            {
                inString = true;
            }
            else if (character == '{')
            {
                depth++;
            }
            else if (character == '}' && --depth == 0)
            {
                return html[start..(index + 1)];
            }
        }

        return null;
    }

    private static string GetPageCid(JsonElement videoData, string pageUrl)
    {
        var pageNumber = 1;
        if (Uri.TryCreate(pageUrl, UriKind.Absolute, out var uri))
        {
            foreach (var part in uri.Query.TrimStart('?').Split('&', StringSplitOptions.RemoveEmptyEntries))
            {
                var pair = part.Split('=', 2);
                if (pair.Length == 2 && pair[0].Equals("p", StringComparison.OrdinalIgnoreCase))
                {
                    _ = int.TryParse(Uri.UnescapeDataString(pair[1]), out pageNumber);
                    pageNumber = Math.Max(pageNumber, 1);
                }
            }
        }

        if (videoData.TryGetProperty("pages", out var pages)
            && pages.ValueKind == JsonValueKind.Array
            && pages.GetArrayLength() > 0)
        {
            var index = Math.Min(pageNumber - 1, pages.GetArrayLength() - 1);
            var page = pages[index];
            return GetScalarAsString(page, "cid") ?? string.Empty;
        }

        return GetScalarAsString(videoData, "cid") ?? string.Empty;
    }

    private static string? GetDefaultMixinKey(JsonElement initialState)
    {
        if (!initialState.TryGetProperty("defaultWbiKey", out var defaultKey))
        {
            return null;
        }

        return BuildMixinKey(GetString(defaultKey, "wbiImgKey"), GetString(defaultKey, "wbiSubKey"));
    }

    private static string? BuildMixinKey(string? imageUrl, string? subUrl)
    {
        var lookup = GetFileStem(imageUrl) + GetFileStem(subUrl);
        if (lookup.Length < 64)
        {
            return null;
        }

        return string.Concat(MixinKeyTable.Select(index => lookup[index])).Substring(0, 32);
    }

    private static string GetFileStem(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return string.Empty;
        }

        var slash = value.LastIndexOf('/');
        var fileName = slash >= 0 ? value[(slash + 1)..] : value;
        var dot = fileName.IndexOf('.');
        return dot >= 0 ? fileName[..dot] : fileName;
    }

    private static string SignParameters(IReadOnlyDictionary<string, string> parameters, string mixinKey)
    {
        var query = string.Join('&', parameters
            .OrderBy(pair => pair.Key, StringComparer.Ordinal)
            .Select(pair => $"{Uri.EscapeDataString(pair.Key)}={Uri.EscapeDataString(RemoveWbiCharacters(pair.Value))}"));
        var hash = Convert.ToHexString(MD5.HashData(Encoding.UTF8.GetBytes(query + mixinKey))).ToLowerInvariant();
        return $"{query}&w_rid={hash}";
    }

    private static string RemoveWbiCharacters(string value) =>
        new(value.Where(character => character is not ('!' or '\'' or '(' or ')' or '*')).ToArray());

    private static string BuildCookieHeader(string? cookiePath, string url)
    {
        if (string.IsNullOrWhiteSpace(cookiePath)
            || !File.Exists(cookiePath)
            || !Uri.TryCreate(url, UriKind.Absolute, out var uri))
        {
            return string.Empty;
        }

        var now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        var cookies = new List<(string Name, string Value, string Path)>();
        foreach (var rawLine in File.ReadLines(cookiePath))
        {
            var line = rawLine.Trim();
            if (line.StartsWith("#HttpOnly_", StringComparison.OrdinalIgnoreCase))
            {
                line = line[10..];
            }
            else if (line.Length == 0 || line.StartsWith('#'))
            {
                continue;
            }

            var fields = line.Split('\t');
            if (fields.Length < 7)
            {
                continue;
            }

            var domain = fields[0].TrimStart('.');
            var path = string.IsNullOrWhiteSpace(fields[2]) ? "/" : fields[2];
            var secure = fields[3].Equals("TRUE", StringComparison.OrdinalIgnoreCase);
            _ = long.TryParse(fields[4], NumberStyles.Integer, CultureInfo.InvariantCulture, out var expires);
            if ((expires > 0 && expires < now)
                || (secure && uri.Scheme != Uri.UriSchemeHttps)
                || !UrlInspector.HostMatches(uri.Host, domain)
                || !uri.AbsolutePath.StartsWith(path, StringComparison.Ordinal))
            {
                continue;
            }

            cookies.Add((fields[5], fields[6], path));
        }

        return string.Join("; ", cookies
            .OrderByDescending(cookie => cookie.Path.Length)
            .Select(cookie => $"{cookie.Name}={cookie.Value}"));
    }

    private static bool ContainsVerificationPage(string html) =>
        new[] { "验证码", "安全验证", "风控", "请完成验证", "geetest" }
            .Any(keyword => html.Contains(keyword, StringComparison.OrdinalIgnoreCase));

    private static string? ExtractHtmlTitle(string html)
    {
        var start = html.IndexOf("<title", StringComparison.OrdinalIgnoreCase);
        if (start < 0 || (start = html.IndexOf('>', start)) < 0)
        {
            return null;
        }

        var end = html.IndexOf("</title>", start, StringComparison.OrdinalIgnoreCase);
        if (end < 0)
        {
            return null;
        }

        return WebUtility.HtmlDecode(html[(start + 1)..end]).Trim();
    }

    private static string? GetString(JsonElement element, string name) =>
        element.TryGetProperty(name, out var property) && property.ValueKind == JsonValueKind.String
            ? property.GetString()
            : null;

    private static string? GetScalarAsString(JsonElement element, string name)
    {
        if (!element.TryGetProperty(name, out var property))
        {
            return null;
        }

        return property.ValueKind switch
        {
            JsonValueKind.String => property.GetString(),
            JsonValueKind.Number => property.GetRawText(),
            _ => null,
        };
    }
}
