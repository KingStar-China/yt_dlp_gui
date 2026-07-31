using System.Net;
using System.Net.Http.Headers;
using YtDlpGui.Core;

namespace YtDlpGui.Infrastructure;

public sealed class YtDlpService : IYtDlpService, IDisposable
{
    private const string DownloadUrl = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe";
    private readonly ProcessRunner _processRunner = new();
    private readonly FormatCatalogParser _formatParser = new();
    private readonly HttpClient _httpClient;
    private readonly BilibiliWebFallback _bilibiliFallback;
    private readonly bool _ownsHttpClient;
    private ToolPaths _tools;
    private bool _disposed;

    public YtDlpService(ToolPaths? tools = null, HttpClient? httpClient = null)
    {
        _tools = tools ?? ToolLocator.Locate();
        if (httpClient is null)
        {
            _httpClient = new(new HttpClientHandler
            {
                AutomaticDecompression = DecompressionMethods.All,
            });
            _ownsHttpClient = true;
        }
        else
        {
            _httpClient = httpClient;
        }

        _httpClient.DefaultRequestHeaders.UserAgent.Add(new ProductInfoHeaderValue("YtDlpGui.Native", "2.0"));
        _bilibiliFallback = new(_httpClient);
    }

    public ToolPaths Tools => _tools;

    public async Task<SniffResult> SniffAsync(
        SniffRequest request,
        IProgress<string>? progress = null,
        CancellationToken cancellationToken = default)
    {
        ThrowIfDisposed();
        if (!File.Exists(_tools.YtDlpPath))
        {
            return SniffResult.Failure("未找到 yt-dlp，请先点击“更新 yt-dlp”。");
        }

        if (!UrlInspector.TryCreateHttpUri(request.Url, out _))
        {
            return SniffResult.Failure("请输入有效的视频 URL（需包含 http:// 或 https://）。");
        }

        var knownPageMessage = UrlInspector.GetKnownNonVideoMessage(request.Url);
        if (knownPageMessage is not null)
        {
            return SniffResult.Failure(knownPageMessage);
        }

        var site = UrlInspector.DetectSite(request.Url);
        var isPlaylist = UrlInspector.IsYouTubePlaylist(request.Url);
        var cookieSources = BuildCookieSources(request);
        var lastMessage = "嗅探失败";

        foreach (var cookieSource in cookieSources)
        {
            cancellationToken.ThrowIfCancellationRequested();
            progress?.Report(GetSniffProgress(cookieSource));
            var arguments = YtDlpCommandBuilder.BuildSniff(request.Url, cookieSource, request.ManualCookiePath, isPlaylist);

            ProcessResult processResult;
            try
            {
                processResult = await _processRunner
                    .RunCaptureAsync(_tools.YtDlpPath, arguments, cancellationToken)
                    .ConfigureAwait(false);
            }
            catch (Exception exception) when (exception is not OperationCanceledException)
            {
                lastMessage = $"调用 yt-dlp 失败：{exception.Message}";
                continue;
            }

            if (processResult.ExitCode == 0)
            {
                try
                {
                    var formats = _formatParser.Parse(processResult.StandardOutput, isPlaylist);
                    if (formats.Count > 0)
                    {
                        return new(true, "嗅探完成", formats, cookieSource);
                    }

                    lastMessage = isPlaylist
                        ? "未找到 YouTube 列表中的可下载视频"
                        : "未找到可用的视频格式或字幕";
                }
                catch (FormatException exception)
                {
                    lastMessage = exception.Message;
                }
            }
            else
            {
                lastMessage = NormalizeError(site, processResult.CombinedOutput, "嗅探失败");
            }
        }

        if (site == SiteKind.Bilibili)
        {
            var fallbackCookieSource = !string.IsNullOrWhiteSpace(request.ManualCookiePath) && File.Exists(request.ManualCookiePath)
                ? CookieSource.ManualFile
                : CookieSource.None;
            var fallbackResult = await _bilibiliFallback.SniffAsync(
                request.Url,
                fallbackCookieSource,
                request.ManualCookiePath,
                progress,
                cancellationToken).ConfigureAwait(false);
            if (fallbackResult.IsSuccess)
            {
                return fallbackResult;
            }

            lastMessage = fallbackResult.Message;
        }

        var shouldRequestCookies = site is SiteKind.YouTube or SiteKind.Bilibili
            && string.IsNullOrWhiteSpace(request.ManualCookiePath);
        if (shouldRequestCookies)
        {
            var cookieHint = request.TryBrowserCookies
                ? "浏览器登录态也未能完成嗅探，可在 Cookie 区域手动填写。"
                : "可展开 Cookie 区域，选择尝试浏览器登录态或手动填写。";
            lastMessage = $"{lastMessage}\n{cookieHint}";
        }

        return SniffResult.Failure(lastMessage, shouldRequestCookies);
    }

    public async Task<DownloadResult> DownloadAsync(
        DownloadRequest request,
        IProgress<string>? progress = null,
        CancellationToken cancellationToken = default)
    {
        ThrowIfDisposed();
        if (request.Format.DirectPayload is null && !File.Exists(_tools.YtDlpPath))
        {
            return new(false, false, "未找到 yt-dlp，请先更新。", null);
        }

        if (YtDlpCommandBuilder.NeedsFfmpeg(request.Format) && !_tools.HasFfmpeg)
        {
            return new(false, false, "当前格式需要 FFmpeg，请把 ffmpeg.exe 放到程序目录或加入 PATH。", null);
        }

        try
        {
            Directory.CreateDirectory(request.OutputDirectory);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            return new(false, false, $"无法使用输出目录：{exception.Message}", null);
        }

        if (request.Format.DirectPayload is not null)
        {
            return await DownloadDirectAsync(request, progress, cancellationToken).ConfigureAwait(false);
        }

        var arguments = YtDlpCommandBuilder.BuildDownload(request);
        var outputPath = string.Empty;
        var recentLines = new Queue<string>();

        try
        {
            var processResult = await _processRunner.RunStreamingAsync(
                _tools.YtDlpPath,
                arguments,
                line =>
                {
                    progress?.Report(CleanProgressLine(line));
                    outputPath = ExtractOutputPath(line) ?? outputPath;
                    recentLines.Enqueue(line);
                    while (recentLines.Count > 80)
                    {
                        recentLines.Dequeue();
                    }
                },
                cancellationToken).ConfigureAwait(false);

            if (processResult.ExitCode != 0)
            {
                var error = NormalizeError(
                    UrlInspector.DetectSite(request.Url),
                    string.Join(Environment.NewLine, recentLines),
                    request.Format.Kind == MediaKind.Playlist ? "列表下载失败" : "下载失败");
                return new(false, false, error, null);
            }

            if (request.Format.Kind == MediaKind.Playlist)
            {
                var playlistDirectory = Path.Combine(
                    request.OutputDirectory,
                    FileNameSanitizer.Sanitize(request.Format.PlaylistTitle, "YouTube 视频列表"));
                return new(true, false, $"列表下载完成：{playlistDirectory}", playlistDirectory);
            }

            var finalPath = FinalizeDownloadedFile(outputPath, request.Format);
            var label = request.Format.Kind == MediaKind.Subtitle ? "字幕下载完成" : "下载完成";
            return new(true, false, string.IsNullOrWhiteSpace(finalPath) ? label : $"{label}：{finalPath}", finalPath);
        }
        catch (OperationCanceledException)
        {
            CleanupPartialFiles(outputPath);
            return new(false, true, "下载已取消", null);
        }
        catch (Exception exception)
        {
            CleanupPartialFiles(outputPath);
            return new(false, false, $"下载失败：{exception.Message}", null);
        }
    }

    public async Task<UpdateResult> UpdateYtDlpAsync(
        IProgress<string>? progress = null,
        CancellationToken cancellationToken = default)
    {
        ThrowIfDisposed();
        var targetPath = _tools.YtDlpPath;
        var targetDirectory = Path.GetDirectoryName(targetPath)
            ?? throw new InvalidOperationException("yt-dlp 目标路径无效。");
        Directory.CreateDirectory(targetDirectory);
        var temporaryPath = Path.Combine(targetDirectory, $"yt-dlp-{Guid.NewGuid():N}.download");

        try
        {
            progress?.Report("正在连接 yt-dlp 发布服务器...");
            using var response = await _httpClient
                .GetAsync(DownloadUrl, HttpCompletionOption.ResponseHeadersRead, cancellationToken)
                .ConfigureAwait(false);
            response.EnsureSuccessStatusCode();
            var totalLength = response.Content.Headers.ContentLength;
            await using (var source = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false))
            await using (var destination = new FileStream(temporaryPath, FileMode.CreateNew, FileAccess.Write, FileShare.None, 1024 * 128, useAsync: true))
            {
                var buffer = new byte[1024 * 128];
                long downloaded = 0;
                while (true)
                {
                    var count = await source.ReadAsync(buffer, cancellationToken).ConfigureAwait(false);
                    if (count == 0)
                    {
                        break;
                    }

                    await destination.WriteAsync(buffer.AsMemory(0, count), cancellationToken).ConfigureAwait(false);
                    downloaded += count;
                    if (totalLength > 0)
                    {
                        progress?.Report($"正在更新 yt-dlp... {downloaded * 100 / totalLength}%");
                    }
                }
            }

            if (new FileInfo(temporaryPath).Length < 1024 * 1024)
            {
                throw new InvalidDataException("下载到的 yt-dlp 文件不完整。");
            }

            var validation = await _processRunner
                .RunCaptureAsync(temporaryPath, ["--version"], cancellationToken)
                .ConfigureAwait(false);
            if (validation.ExitCode != 0 || string.IsNullOrWhiteSpace(validation.StandardOutput))
            {
                throw new InvalidDataException("下载到的 yt-dlp 无法运行。");
            }

            File.Move(temporaryPath, targetPath, overwrite: true);
            _tools = ToolLocator.Locate(Path.GetDirectoryName(targetPath));
            var version = validation.StandardOutput.Trim().Split('\n')[0].Trim();
            return new(true, $"yt-dlp 更新完成：{version}", version);
        }
        catch (OperationCanceledException)
        {
            return new(false, "yt-dlp 更新已取消");
        }
        catch (Exception exception)
        {
            return new(false, $"yt-dlp 更新失败：{exception.Message}");
        }
        finally
        {
            if (File.Exists(temporaryPath))
            {
                try
                {
                    File.Delete(temporaryPath);
                }
                catch (IOException)
                {
                    // A failed cleanup must not hide the update result.
                }
            }
        }
    }

    public async Task<string?> GetYtDlpVersionAsync(CancellationToken cancellationToken = default)
    {
        ThrowIfDisposed();
        if (!File.Exists(_tools.YtDlpPath))
        {
            return null;
        }

        try
        {
            var result = await _processRunner
                .RunCaptureAsync(_tools.YtDlpPath, ["--version"], cancellationToken)
                .ConfigureAwait(false);
            return result.ExitCode == 0 ? result.StandardOutput.Trim().Split('\n')[0].Trim() : null;
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            return null;
        }
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        if (_ownsHttpClient)
        {
            _httpClient.Dispose();
        }
    }

    private static IReadOnlyList<CookieSource> BuildCookieSources(SniffRequest request)
    {
        var sources = new List<CookieSource>();
        if (!string.IsNullOrWhiteSpace(request.ManualCookiePath) && File.Exists(request.ManualCookiePath))
        {
            sources.Add(CookieSource.ManualFile);
        }

        sources.Add(CookieSource.None);

        if (request.TryBrowserCookies)
        {
            sources.AddRange([CookieSource.Firefox, CookieSource.Edge, CookieSource.Chrome]);
        }

        return sources.Distinct().ToArray();
    }

    private static string GetSniffProgress(CookieSource source) => source switch
    {
        CookieSource.ManualFile => "正在使用手动 Cookie 嗅探...",
        CookieSource.Firefox => "正在尝试 Firefox 登录态...",
        CookieSource.Edge => "正在尝试 Edge 登录态...",
        CookieSource.Chrome => "正在尝试 Chrome 登录态...",
        _ => "正在进行匿名嗅探...",
    };

    private static string NormalizeError(SiteKind site, string errorText, string fallback)
    {
        var lowered = errorText.ToLowerInvariant();
        if (site == SiteKind.Bilibili && (lowered.Contains("http error 412") || lowered.Contains("precondition failed")))
        {
            return "B站接口返回 412，请尝试浏览器登录态或手动 Cookie。";
        }

        if (lowered.Contains("unsupported url")
            || lowered.Contains("no suitable extractor")
            || lowered.Contains("unsupported site")
            || lowered.Contains("is not a valid url"))
        {
            return "该链接不是 yt-dlp 支持的网站或链接类型。";
        }

        if (lowered.Contains("sign in") || lowered.Contains("login required"))
        {
            return "目标站点需要登录态或 Cookie。";
        }

        var usefulLine = errorText
            .Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .LastOrDefault(line => line.Contains("ERROR:", StringComparison.OrdinalIgnoreCase))
            ?? errorText.Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).LastOrDefault();
        return string.IsNullOrWhiteSpace(usefulLine) ? fallback : usefulLine;
    }

    private static string CleanProgressLine(string line)
    {
        const string outputPrefix = "__YTDLP_FILE__:";
        if (line.StartsWith(outputPrefix, StringComparison.Ordinal))
        {
            return $"正在完成文件：{Path.GetFileName(line[outputPrefix.Length..])}";
        }

        return line;
    }

    private static string? ExtractOutputPath(string line)
    {
        const string outputPrefix = "__YTDLP_FILE__:";
        if (line.StartsWith(outputPrefix, StringComparison.Ordinal))
        {
            return line[outputPrefix.Length..].Trim().Trim('"');
        }

        foreach (var marker in new[] { "[download] Destination:", "[ExtractAudio] Destination:", "[info] Writing video subtitles to:" })
        {
            var index = line.IndexOf(marker, StringComparison.OrdinalIgnoreCase);
            if (index >= 0)
            {
                return line[(index + marker.Length)..].Trim().Trim('"');
            }
        }

        const string mergeMarker = "[Merger] Merging formats into ";
        var mergeIndex = line.IndexOf(mergeMarker, StringComparison.OrdinalIgnoreCase);
        return mergeIndex >= 0 ? line[(mergeIndex + mergeMarker.Length)..].Trim().Trim('"') : null;
    }

    private static string FinalizeDownloadedFile(string outputPath, MediaFormat format)
    {
        if (string.IsNullOrWhiteSpace(outputPath) || !File.Exists(outputPath))
        {
            return outputPath;
        }

        var extension = Path.GetExtension(outputPath);
        var suffix = string.Empty;
        if (format.Kind == MediaKind.Audio && extension is ".m4a" or ".aac")
        {
            suffix = $".{FileNameSanitizer.FormatSize(new FileInfo(outputPath).Length)}";
        }
        else if (format.Kind == MediaKind.Video && extension.Equals(".mp4", StringComparison.OrdinalIgnoreCase))
        {
            var resolution = format.Label.Split('/')[0];
            if (resolution.EndsWith('p') && resolution[..^1].All(char.IsDigit))
            {
                suffix = $".{resolution}";
            }
        }

        if (suffix.Length == 0)
        {
            return outputPath;
        }

        var basePath = Path.Combine(Path.GetDirectoryName(outputPath) ?? string.Empty, Path.GetFileNameWithoutExtension(outputPath));
        var candidate = $"{basePath}{suffix}{extension}";
        var index = 1;
        while (File.Exists(candidate))
        {
            candidate = $"{basePath}{suffix} ({index++}){extension}";
        }

        File.Move(outputPath, candidate);
        return candidate;
    }

    private async Task<DownloadResult> DownloadDirectAsync(
        DownloadRequest request,
        IProgress<string>? progress,
        CancellationToken cancellationToken)
    {
        var payload = request.Format.DirectPayload
            ?? throw new InvalidOperationException("直连下载数据不存在。");
        var title = FileNameSanitizer.Sanitize(payload.Title, "bilibili_video");
        var temporaryPaths = new List<string>();
        string? finalPath = null;
        var success = false;

        try
        {
            if (request.Format.Kind == MediaKind.Audio)
            {
                if (string.IsNullOrWhiteSpace(payload.AudioUrl))
                {
                    return new(false, false, "B站音频直链不存在。", null);
                }

                finalPath = GetUniquePath(Path.Combine(request.OutputDirectory, $"{title}.m4a"));
                var temporaryAudio = $"{finalPath}.part";
                temporaryPaths.Add(temporaryAudio);
                await DownloadUrlToFileAsync(
                    payload.AudioUrl,
                    temporaryAudio,
                    payload,
                    "正在下载 B站音频直链",
                    progress,
                    cancellationToken).ConfigureAwait(false);
                File.Move(temporaryAudio, finalPath);
                finalPath = FinalizeDownloadedFile(finalPath, request.Format);
                success = true;
                return new(true, false, $"下载完成：{finalPath}", finalPath);
            }

            if (string.IsNullOrWhiteSpace(payload.VideoUrl) || string.IsNullOrWhiteSpace(_tools.FfmpegPath))
            {
                return new(false, false, "B站视频直链或 FFmpeg 不可用。", null);
            }

            finalPath = GetUniquePath(Path.Combine(request.OutputDirectory, $"{title}.mp4"));
            var temporaryVideo = $"{finalPath}.video.m4s";
            var temporaryAudioTrack = $"{finalPath}.audio.m4a";
            temporaryPaths.Add(temporaryVideo);
            temporaryPaths.Add(temporaryAudioTrack);

            await DownloadUrlToFileAsync(
                payload.VideoUrl,
                temporaryVideo,
                payload,
                "正在下载 B站视频直链",
                progress,
                cancellationToken).ConfigureAwait(false);

            if (!string.IsNullOrWhiteSpace(payload.AudioUrl))
            {
                await DownloadUrlToFileAsync(
                    payload.AudioUrl,
                    temporaryAudioTrack,
                    payload,
                    "正在下载 B站音频直链",
                    progress,
                    cancellationToken).ConfigureAwait(false);
            }

            var ffmpegArguments = new List<string> { "-y", "-i", temporaryVideo };
            if (!string.IsNullOrWhiteSpace(payload.AudioUrl))
            {
                ffmpegArguments.AddRange(["-i", temporaryAudioTrack]);
            }

            ffmpegArguments.AddRange(["-c", "copy", finalPath]);
            progress?.Report("正在用 FFmpeg 合并 B站音视频...");
            var mergeResult = await _processRunner.RunStreamingAsync(
                _tools.FfmpegPath,
                ffmpegArguments,
                line => progress?.Report(line),
                cancellationToken).ConfigureAwait(false);
            if (mergeResult.ExitCode != 0)
            {
                throw new InvalidOperationException(NormalizeError(SiteKind.Bilibili, mergeResult.CombinedOutput, "FFmpeg 合并失败"));
            }

            finalPath = FinalizeDownloadedFile(finalPath, request.Format);
            success = true;
            return new(true, false, $"下载完成：{finalPath}", finalPath);
        }
        catch (OperationCanceledException)
        {
            return new(false, true, "下载已取消", null);
        }
        catch (Exception exception)
        {
            return new(false, false, $"B站直连下载失败：{exception.Message}", null);
        }
        finally
        {
            if (!success && !string.IsNullOrWhiteSpace(finalPath))
            {
                TryDeleteFile(finalPath);
            }

            foreach (var temporaryPath in temporaryPaths)
            {
                TryDeleteFile(temporaryPath);
            }
        }
    }

    private async Task DownloadUrlToFileAsync(
        string url,
        string targetPath,
        DirectMediaPayload payload,
        string progressPrefix,
        IProgress<string>? progress,
        CancellationToken cancellationToken)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, url);
        request.Headers.TryAddWithoutValidation("User-Agent", payload.UserAgent);
        request.Headers.Referrer = new Uri(payload.Referer);
        using var response = await _httpClient.SendAsync(
            request,
            HttpCompletionOption.ResponseHeadersRead,
            cancellationToken).ConfigureAwait(false);
        response.EnsureSuccessStatusCode();
        var totalLength = response.Content.Headers.ContentLength;
        await using var source = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
        await using var destination = new FileStream(
            targetPath,
            FileMode.CreateNew,
            FileAccess.Write,
            FileShare.None,
            1024 * 256,
            useAsync: true);
        var buffer = new byte[1024 * 256];
        long downloaded = 0;
        var lastProgressValue = -1L;

        while (true)
        {
            var count = await source.ReadAsync(buffer, cancellationToken).ConfigureAwait(false);
            if (count == 0)
            {
                break;
            }

            await destination.WriteAsync(buffer.AsMemory(0, count), cancellationToken).ConfigureAwait(false);
            downloaded += count;
            var progressValue = totalLength > 0 ? downloaded * 100 / totalLength.Value : downloaded / (1024 * 1024);
            if (progressValue == lastProgressValue)
            {
                continue;
            }

            lastProgressValue = progressValue;
            progress?.Report(totalLength > 0
                ? $"{progressPrefix}... {progressValue}%"
                : $"{progressPrefix}... {downloaded / (1024d * 1024):0.0}MB");
        }

        if (totalLength > 0 && downloaded != totalLength.Value)
        {
            throw new InvalidDataException("直连下载不完整，请重试。");
        }
    }

    private static string GetUniquePath(string path)
    {
        if (!File.Exists(path))
        {
            return path;
        }

        var directory = Path.GetDirectoryName(path) ?? string.Empty;
        var fileName = Path.GetFileNameWithoutExtension(path);
        var extension = Path.GetExtension(path);
        var index = 1;
        string candidate;
        do
        {
            candidate = Path.Combine(directory, $"{fileName} ({index++}){extension}");
        }
        while (File.Exists(candidate));

        return candidate;
    }

    private static void TryDeleteFile(string path)
    {
        try
        {
            if (File.Exists(path))
            {
                File.Delete(path);
            }
        }
        catch (IOException)
        {
            // Best-effort cleanup after a canceled or failed direct download.
        }
    }

    private static void CleanupPartialFiles(string outputPath)
    {
        if (string.IsNullOrWhiteSpace(outputPath))
        {
            return;
        }

        foreach (var path in new[] { $"{outputPath}.part", $"{outputPath}.ytdl" })
        {
            try
            {
                if (File.Exists(path))
                {
                    File.Delete(path);
                }
            }
            catch (IOException)
            {
                // Best-effort cleanup after cancellation or failure.
            }
        }
    }

    private void ThrowIfDisposed() => ObjectDisposedException.ThrowIf(_disposed, this);
}
